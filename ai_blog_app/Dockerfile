FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Whisper and yt-dlp need ffmpeg to decode the downloaded audio.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the CPU-only build of torch first; otherwise openai-whisper pulls the
# CUDA build, which adds several GB to the image.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Apply migrations, then serve. Generating a blog (download + transcribe + LLM)
# can take minutes, so give workers a long timeout.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn ai_blog_app.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 600"]
