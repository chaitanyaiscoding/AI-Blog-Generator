from django.conf import settings
from django.db import models


class Blog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blogs')
    url = models.URLField(max_length=500)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # id breaks ties when two blogs share the same timestamp.
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.user.username}: {self.url}'
