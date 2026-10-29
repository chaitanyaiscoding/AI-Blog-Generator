from django.conf import settings
from django.db import models


class Blog(models.Model):
    # The row is created as soon as the user submits a URL; the Celery worker
    # moves it through these states while it generates the content.
    class Status(models.TextChoices):
        PENDING = 'pending'
        PROCESSING = 'processing'
        COMPLETED = 'completed'
        FAILED = 'failed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blogs')
    url = models.URLField(max_length=500)
    # Empty until the worker finishes.
    content = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Why generation failed, shown to the user when status is FAILED.
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # id breaks ties when two blogs share the same timestamp.
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.user.username}: {self.url}'
