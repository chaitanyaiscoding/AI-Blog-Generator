from django.urls import path
from . import views


urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('me/', views.MeView.as_view(), name='me'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('signup/', views.SignupView.as_view(), name='signup'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('blogs/', views.BlogListCreateView.as_view(), name='blogs'),
    path('blogs/all/', views.AllBlogsListView.as_view(), name='all_blogs'),
]
