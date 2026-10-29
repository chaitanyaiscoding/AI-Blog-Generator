# Load the Celery app whenever Django starts, so @shared_task binds to it and
# .delay() calls from views publish to our broker.
from .celery import app as celery_app

__all__ = ('celery_app',)
