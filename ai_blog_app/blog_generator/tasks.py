import logging

from celery import shared_task

from .models import Blog

logger = logging.getLogger(__name__)


# Runs in the Celery worker, not in Gunicorn. The view calls generate_blog.delay(id),
# which only publishes a message naming this task ("blog_generator.tasks.generate_blog")
# with args [blog_id]; the worker looks the name up and calls this function.
@shared_task
def generate_blog(blog_id):
    blog = Blog.objects.get(pk=blog_id)
    blog.status = Blog.Status.PROCESSING
    blog.save(update_fields=['status', 'updated_at'])

    # Imported here so the web process never loads Whisper/torch: only workers
    # that actually run this task pay for that memory.
    from .generation import generate_blog_content

    try:
        blog.content = generate_blog_content(blog.url)
        blog.status = Blog.Status.COMPLETED
    except Exception as e:
        # Bad URL, private video, OpenAI error, ... The user sees the message;
        # the full traceback goes to the worker log.
        logger.exception('Generating blog %s failed', blog_id)
        blog.status = Blog.Status.FAILED
        blog.error = str(e)
    blog.save(update_fields=['content', 'status', 'error', 'updated_at'])
