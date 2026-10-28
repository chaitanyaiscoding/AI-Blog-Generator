import os
import tempfile
from functools import cache
from pathlib import Path

import whisper
import yt_dlp
from openai import OpenAI
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Blog
from .serializers import BlogSerializer, LoginSerializer, SignupSerializer, UserSerializer

# Index and logout take no input, so they use plain APIView: GenericAPIView
# requires a serializer_class (the browsable API crashes without one).
class IndexView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'message': 'AI Blog Generator API'})


# The frontend calls this on page load to find out who is logged in (403 means
# nobody). It also sets the csrftoken cookie that later POSTs must echo back in X-CSRFToken.
@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        auth_login(self.request, user)


class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        auth_login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    def post(self, request):
        # Deletes the session row, so the cookie stops working.
        auth_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)



# OPENAI_API_KEY comes from .env, which settings.py loads into os.environ at startup.
@cache
def get_openai_client():
    return OpenAI(api_key=os.environ['OPENAI_API_KEY'])


def generate_article(transcript):
    response = get_openai_client().chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {
                'role': 'system',
                'content': 'You are a writer who turns video transcripts into clear, engaging blog articles.',
            },
            {
                'role': 'user',
                'content': (
                    'Write a blog article of about 200 words based on the following YouTube video transcript. '
                    'Write it as a standalone article, not as a description of a video.\n\n'
                    f'Transcript:\n{transcript}'
                ),
            },
        ],
    )
    return response.choices[0].message.content

# Loading the model takes a few seconds, so load it on first use and reuse it after that.
# "base" is a good speed/accuracy tradeoff on CPU; try "small" for better accuracy.
@cache
def get_whisper_model():
    return whisper.load_model("base")


# Downloads only the audio track into out_dir and returns (video title, path to the audio file).
def download_audio(url, out_dir):
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(Path(out_dir) / '%(id)s.%(ext)s'),
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info['title'], ydl.prepare_filename(info)


def get_transcript(audio_path):
    # fp16=False avoids the "FP16 is not supported on CPU" warning.
    result = get_whisper_model().transcribe(audio_path, fp16=False)
    return result['text']


def generate_blog_content(url):
    # The temp dir (and the audio file in it) is deleted when the block exits.
    with tempfile.TemporaryDirectory() as tmp:
        title, audio_path = download_audio(url, tmp)
        transcript = get_transcript(audio_path)

    return generate_article(transcript)


# GET: the logged-in user's blogs. POST {"url": "..."}: generate and save a new one.
class BlogListCreateView(generics.ListCreateAPIView):
    serializer_class = BlogSerializer

    def get_queryset(self):
        return Blog.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        content = generate_blog_content(serializer.validated_data['url'])
        serializer.save(user=self.request.user, content=content)


# GET: every user's blogs, newest first, as a read-only feed.
class AllBlogsListView(generics.ListAPIView):
    serializer_class = BlogSerializer
    queryset = Blog.objects.select_related('user')
