# Scaling the AI Blog Generator

This document covers how blog generation works today, the problem with it once more than two people use the app at the same time, and the plan to fix it with **Celery + RabbitMQ**.

---

## 1. How it works today

### Deployment

```
Browser ──► nginx :80 ──┬── /api/*  ──► backend (Gunicorn, 2 sync workers) ──► Postgres
                        └── /*      ──► frontend (React)
```

- `docker-compose.yml` runs four containers: `db` (Postgres 16), `backend` (Django + DRF), `frontend` (React on Bun), and `nginx`.
- The backend runs this command (`ai_blog_app/Dockerfile`):

  ```
  gunicorn ai_blog_app.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 600
  ```

  That's **2 sync workers**. Each one is a separate OS process that handles **one HTTP request at a time**.
- nginx gives each `/api/` request up to `proxy_read_timeout 600s` to respond (`nginx/default.conf`).

### The "Create Blog" flow

1. **Frontend** (`frontend/src/pages/HomePage.tsx`) calls `api.post("/blogs/", { url })` and **awaits the response**. The spinner shows "Creating..." until the request returns.
2. **Backend** (`blog_generator/views.py`, `BlogListCreateView.perform_create`) does all the work **inside the HTTP request**:

   ```python
   def perform_create(self, serializer):
       content = generate_blog_content(serializer.validated_data['url'])
       serializer.save(user=self.request.user, content=content)
   ```

   `generate_blog_content` runs these steps one after another:

   | Step | Function | Kind of work | Rough time |
   |---|---|---|---|
   | Download audio | `download_audio` (yt-dlp) | Network I/O | seconds to a minute |
   | Transcribe | `get_transcript` (Whisper `base`, CPU) | CPU-heavy | most of the total |
   | Write article | `generate_article` (OpenAI `gpt-4o-mini`) | Network I/O | a few seconds |
   | Save | `serializer.save(...)` | DB write | milliseconds |

3. The `Blog` row is only written **after** generation succeeds. If anything fails partway, nothing is saved, and the user just gets an error message.

> Note: `get_whisper_model()` and `get_openai_client()` are wrapped in `@cache`, so each Gunicorn worker process loads the Whisper model **once** and reuses it. But every worker has **its own copy** of the model in RAM.

---

## 2. The problem

Assume one full generation takes **~2 minutes**.

### What happens to the third user

| Time | Event | Worker 1 | Worker 2 |
|---|---|---|---|
| 0:00 | Friend 1 submits a URL | busy (friend 1) | idle |
| 0:30 | Friend 2 submits a URL | busy (friend 1) | busy (friend 2) |
| 1:00 | **Friend 3 submits a URL** | busy | busy |
| 2:00 | Friend 1 done. Worker 1 picks up friend 3 | busy (friend 3) | busy (friend 2) |
| ~4:00 | Friend 3 finally gets their article | | |

Friend 3 **isn't rejected**. Their request waits:

1. The React page loads fine, because it's served by the `frontend` container.
2. nginx connects to `backend:8000`. The **Linux kernel** finishes the TCP handshake and puts the connection in Gunicorn's **listen backlog** (a kernel queue, 2048 slots by default). nginx sends the request and starts its 600s timer.
3. Neither worker calls `accept()`, because both are stuck inside `perform_create`.
4. When a worker frees up, it takes the next connection from the backlog.

### Why: sync workers block on everything

A sync worker runs the view top to bottom and can't do anything else until it returns. That includes the time it spends **waiting** on YouTube and OpenAI, when it's doing no work at all.

> **Max concurrent requests = number of workers = 2.**

### Consequences

1. **The whole API freezes, not just generation.** Login, `/me/`, the blog list, and the public feed all share those 2 workers. A 50 ms login waits behind 2-minute jobs.
2. **504s when demand grows.** With 2 workers and 2-minute jobs, the queue moves at about 1 job per minute. Around 10 or more people submitting at once pushes the last ones past nginx's 600s limit, and they get **504 Gateway Timeout**.
3. **Wasted work.** After nginx gives up, Gunicorn doesn't know the client is gone. It still spends 2 minutes of CPU and OpenAI credits on a result nobody receives. The user retries, which adds yet another job to the queue.
4. **No progress or history for failed jobs.** The `Blog` row only exists on success, so the user can't see "pending" or "failed", and a refresh loses everything.
5. **Adding workers doesn't fix it.** Each worker holds its own Whisper model in RAM, and Whisper uses every CPU core. More workers means more memory (OOM kills on a small EC2 instance), and parallel transcriptions just slow each other down. Web capacity and transcription capacity are **tied together**, so we can't tune them separately.

**Root cause:** slow, heavy work runs **inside the HTTP request/response cycle**.

---

## 3. The solution: background jobs with Celery + RabbitMQ

Move generation out of the request. The web server only **records the job and puts it on a queue**, which takes milliseconds. A separate **Celery worker** container takes jobs from **RabbitMQ** and does the slow work. The frontend **polls every 5 seconds** for the result.

### Architecture

```
                                   ┌──────────────┐
Browser ──► nginx ──► backend ────►│   RabbitMQ   │────► celery worker ──► yt-dlp / Whisper / OpenAI
   ▲                (Gunicorn)     │ (queue:      │       (concurrency 1–2)
   │                   │           │  "celery")   │             │
   │                   ▼           └──────────────┘             ▼
   └── poll every 5s ─ Postgres ◄────────────────────────── update Blog row
```

- **Gunicorn workers** now only handle fast requests, so login and browsing stay fast however many videos are in the queue.
- **RabbitMQ** holds pending jobs. If 50 people submit at once, 50 messages wait in the queue, not 50 open HTTP connections.
- **Celery worker** concurrency is set to match the machine's RAM and CPU (e.g. 1 transcription at a time), separately from web capacity. To handle more, add more worker containers or machines.

### Request flow

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as Django (Gunicorn)
    participant DB as Postgres
    participant MQ as RabbitMQ
    participant W as Celery worker

    FE->>API: POST /blogs/ {url}
    API->>DB: BEGIN; INSERT Blog(status=PENDING)
    API->>DB: COMMIT
    Note over API: transaction.on_commit fires
    API->>MQ: publish {task: "generate_blog", args: [blog_id]}
    API-->>FE: 202 {id, status: "pending"}

    loop every 5s
        FE->>API: GET /blogs/<id>/
        API->>DB: SELECT
        API-->>FE: {status: "pending" | "processing"}
    end

    MQ->>W: deliver message
    W->>DB: status=PROCESSING
    W->>W: download → transcribe → OpenAI
    W->>DB: status=COMPLETED, content=...
    W->>MQ: ack

    FE->>API: GET /blogs/<id>/
    API-->>FE: {status: "completed", content: "..."}
    Note over FE: stop polling, show article
```

### How the pieces fit together

#### a) The model tracks job state

Add a status (and an error message) to `Blog` so the row exists from the moment the user clicks:

```python
class Blog(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending'
        PROCESSING = 'processing'
        COMPLETED = 'completed'
        FAILED = 'failed'

    user = ...
    url = ...
    content = models.TextField(blank=True)          # empty until the worker finishes
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True)
    created_at = ...
    updated_at = models.DateTimeField(auto_now=True)
```

#### b) The task: a function marked with a decorator

The worker's function is a normal Python function with the `@shared_task` decorator (in `blog_generator/tasks.py`):

```python
@shared_task
def generate_blog(blog_id):
    blog = Blog.objects.get(pk=blog_id)
    blog.status = Blog.Status.PROCESSING
    blog.save(update_fields=['status', 'updated_at'])

    # Imported here so the web process never loads Whisper/torch.
    from .generation import generate_blog_content

    try:
        blog.content = generate_blog_content(blog.url)
        blog.status = Blog.Status.COMPLETED
    except Exception as e:
        logger.exception('Generating blog %s failed', blog_id)
        blog.status = Blog.Status.FAILED
        blog.error = str(e)
    blog.save(update_fields=['content', 'status', 'error', 'updated_at'])
```

The download/Whisper/OpenAI helpers moved from `views.py` to `blog_generator/generation.py`. Acks, prefetch and results are configured once in `settings.py` (`CELERY_*`) instead of on each task.

The same decorator is used **on both sides**:

- **Producer (Django):** `generate_blog.delay(blog_id)` doesn't run the function. It **serializes a message** and publishes it to RabbitMQ.
- **Consumer (Celery worker):** at startup the worker imports `tasks.py`, and the decorator **registers** `generate_blog` under its name, `blog_generator.tasks.generate_blog`. When a message arrives, the worker uses that name to find the registered function and calls it with the args from the message.

#### c) What the message in RabbitMQ contains

Celery sends a message like this (simplified):

```json
headers: {
  "task": "blog_generator.tasks.generate_blog",   // which function to call
  "id":   "6f1c...e2",                            // task id
  "retries": 0
}
body: [[42], {}, {...}]                           // args=[blog_id], kwargs={}
```

It contains **only the blog's id**, not the URL or content. The worker reads the up-to-date row from Postgres. That keeps messages small and makes Postgres the single source of truth.

#### d) Enqueue only after the transaction commits

```python
from django.db import transaction

def perform_create(self, serializer):
    with transaction.atomic():
        blog = serializer.save(user=self.request.user, status=Blog.Status.PENDING)
        transaction.on_commit(lambda: generate_blog.delay(blog.id))
```

Why `on_commit`: if we published **inside** the transaction, a fast worker could receive the message before Postgres commits the row. `Blog.objects.get(pk=42)` would then raise `DoesNotExist`. Or the transaction could roll back after the message was already sent, leaving a job for a row that never existed. `on_commit` publishes **only once the row is actually saved**, and never if the transaction rolls back.

The view returns **202 Accepted** with `{id, status: "pending"}` right away.

#### e) Polling endpoint

Add `GET /blogs/<id>/` (a `RetrieveAPIView` limited to the logged-in user's blogs) that returns `id, url, status, content, error, created_at`.

#### f) Frontend polling

`HomePage.tsx`:

1. `POST /blogs/` → receives `{id, status: "pending"}`.
2. Every **5 seconds**, `GET /blogs/<id>/` and display the latest status ("Queued...", "Transcribing...").
3. Stop polling on `completed` (show `content`) or `failed` (show `error`).
4. Clear the interval when the component unmounts.

Because the job lives in the DB, a page refresh doesn't lose it. The blog list can show pending and failed blogs and resume polling.

### Docker Compose changes

```yaml
  rabbitmq:
    image: rabbitmq:4-management        # creates its user from RABBITMQ_DEFAULT_USER/PASS in .env
    env_file: ./ai_blog_app/.env
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]

  backend:
    environment: &service_env           # settings.py builds the amqp:// URL from these + .env
      DB_HOST: db
      RABBITMQ_HOST: rabbitmq
    depends_on: [db, rabbitmq]          # both with condition: service_healthy

  worker:
    build: ./ai_blog_app                # same image as backend
    command: celery -A ai_blog_app worker --loglevel=info --concurrency=1
    env_file: ./ai_blog_app/.env
    environment: *service_env
    volumes:
      - whisper_cache:/root/.cache/whisper   # moved here from backend
    depends_on: [db, rabbitmq]
```

### Settings that matter for long jobs

| Setting | Value | Why |
|---|---|---|
| `CELERY_TASK_ACKS_LATE = True` (+ `REJECT_ON_WORKER_LOST`) | settings.py | Ack the message **after** the task finishes. If the worker crashes mid-transcription, RabbitMQ redelivers the job instead of losing it. |
| `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` | settings.py | Each worker process reserves only one message at a time, so a busy worker doesn't hold jobs that another free worker could run. |
| `--concurrency=1` (or 2) | worker command | How many transcriptions run at once. Size it to RAM/CPU. Scale out with `docker compose up -d --scale worker=2`. |
| `CELERY_TASK_IGNORE_RESULT = True` | settings.py | The result is stored in the `Blog` row, so no Celery result backend is needed. |
| Gunicorn `--timeout` / nginx `proxy_read_timeout` | back to defaults (30s / 60s) | Requests are fast again, so a long timeout only hides bugs. |
| RabbitMQ `consumer_timeout` | default 30 min | An unacked message held longer than this closes the channel. 2-minute jobs are fine, but keep it in mind for long videos. |

### What we get

| Before | After |
|---|---|
| 2 jobs at a time, and everything else waits | Unlimited jobs **queued**, and the API stays fast |
| Login blocked behind transcriptions | Login and browsing are unaffected |
| 504 after 10 min in line | No long HTTP requests, so no 504s |
| Failed job = lost, nothing saved | Row shows `failed` with an error, and can be retried |
| Refresh = lost result | Result lives in the DB, so polling can resume |
| Web and transcription capacity tied together | Scale `backend` and `worker` independently |
