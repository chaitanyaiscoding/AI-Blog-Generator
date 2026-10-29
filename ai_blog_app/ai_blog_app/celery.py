import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_blog_app.settings')

app = Celery('ai_blog_app')
# Read every CELERY_* setting from settings.py (CELERY_BROKER_URL -> broker_url, ...).
app.config_from_object('django.conf:settings', namespace='CELERY')
# Import tasks.py from every installed app, so @shared_task functions get registered.
app.autodiscover_tasks()
