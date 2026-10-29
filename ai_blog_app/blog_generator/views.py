from django.contrib.auth import login as auth_login, logout as auth_logout
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Blog
from .serializers import BlogSerializer, LoginSerializer, SignupSerializer, UserSerializer
from .tasks import generate_blog

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



# GET: the logged-in user's blogs. POST {"url": "..."}: queue a new one for generation.
class BlogListCreateView(generics.ListCreateAPIView):
    serializer_class = BlogSerializer

    def get_queryset(self):
        return Blog.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # 202: accepted, but the content isn't ready yet; poll /blogs/<id>/ for it.
        response.status_code = status.HTTP_202_ACCEPTED
        return response

    def perform_create(self, serializer):
        with transaction.atomic():
            blog = serializer.save(user=self.request.user)
            # Publish only once the row is committed; otherwise a fast worker could
            # look the id up before it exists, or get a job for a rolled-back row.
            transaction.on_commit(lambda: generate_blog.delay(blog.id))


# GET: one of the logged-in user's blogs. The frontend polls this until the
# status is completed or failed.
class BlogDetailView(generics.RetrieveAPIView):
    serializer_class = BlogSerializer

    def get_queryset(self):
        return Blog.objects.filter(user=self.request.user)


# GET: every user's blogs, newest first, as a read-only feed.
class AllBlogsListView(generics.ListAPIView):
    serializer_class = BlogSerializer
    queryset = Blog.objects.select_related('user')
