from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase

from .models import Blog
from .tasks import generate_blog


class AuthTests(APITestCase):
    def signup(self, **overrides):
        data = {'username': 'alice', 'email': 'alice@example.com', 'password': 'S3cure-pass-123'}
        data.update(overrides)
        return self.client.post('/signup/', data, format='json')

    def test_signup_creates_user_and_logs_in(self):
        res = self.signup()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data, {'id': res.data['id'], 'username': 'alice', 'email': 'alice@example.com'})
        user = User.objects.get(username='alice')
        self.assertTrue(user.check_password('S3cure-pass-123'))
        self.assertEqual(self.client.get('/me/').data['username'], 'alice')

    def test_signup_rejects_duplicate_username(self):
        self.signup()
        res = self.signup(email='other@example.com')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['username'], ['Username is already taken'])

    def test_signup_rejects_duplicate_email_case_insensitive(self):
        self.signup()
        res = self.signup(username='bob', email='ALICE@example.com')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['email'], ['An account with this email already exists'])

    def test_signup_rejects_invalid_email(self):
        res = self.signup(email='abc.gmail.com')
        self.assertEqual(res.status_code, 400)
        self.assertIn('email', res.data)

    def test_signup_requires_email(self):
        res = self.signup(email='')
        self.assertEqual(res.status_code, 400)
        self.assertIn('email', res.data)

    def test_signup_rejects_weak_password(self):
        res = self.signup(password='123')
        self.assertEqual(res.status_code, 400)
        self.assertIn('password', res.data)
        self.assertFalse(User.objects.filter(username='alice').exists())

    def test_login_starts_session(self):
        self.signup()
        self.client.logout()
        res = self.client.post('/login/', {'username': 'alice', 'password': 'S3cure-pass-123'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['username'], 'alice')
        self.assertIn('sessionid', res.cookies)

    def test_login_rejects_wrong_password(self):
        self.signup()
        self.client.logout()
        res = self.client.post('/login/', {'username': 'alice', 'password': 'wrong'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['non_field_errors'], ['Invalid username or password'])

    def test_me_without_session_is_forbidden_but_sets_csrf_cookie(self):
        res = self.client.get('/me/')
        self.assertEqual(res.status_code, 403)
        self.assertIn('csrftoken', res.cookies)

    def test_logout_ends_session(self):
        self.signup()
        self.assertEqual(self.client.post('/logout/').status_code, 204)
        self.assertEqual(self.client.get('/me/').status_code, 403)

    def test_logged_in_post_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get('/me/')
        client.post('/signup/', {'username': 'alice', 'email': 'alice@example.com', 'password': 'S3cure-pass-123'},
                    format='json')
        self.assertEqual(client.post('/logout/').status_code, 403)
        # Login rotates the CSRF token, so use the fresh cookie.
        csrf = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/logout/', HTTP_X_CSRFTOKEN=csrf).status_code, 204)

    def test_cors_allows_frontend_origin_with_credentials(self):
        res = self.client.options('/login/', HTTP_ORIGIN='http://localhost:3000',
                                  HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
        self.assertEqual(res['Access-Control-Allow-Origin'], 'http://localhost:3000')
        self.assertEqual(res['Access-Control-Allow-Credentials'], 'true')


class BlogTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'alice@example.com', 'S3cure-pass-123')
        self.bob = User.objects.create_user('bob', 'bob@example.com', 'S3cure-pass-123')
        Blog.objects.create(user=self.alice, url='https://a.com', content='Alice blog')
        Blog.objects.create(user=self.bob, url='https://b.com', content='Bob blog')

    def test_blogs_require_auth(self):
        self.assertEqual(self.client.get('/blogs/').status_code, 403)
        self.assertEqual(self.client.get('/blogs/all/').status_code, 403)

    def test_list_returns_only_my_blogs(self):
        self.client.force_authenticate(self.alice)
        res = self.client.get('/blogs/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([b['content'] for b in res.data], ['Alice blog'])
        self.assertEqual(res.data[0]['author'], 'alice')

    def test_all_blogs_lists_everyone_newest_first(self):
        self.client.force_authenticate(self.alice)
        res = self.client.get('/blogs/all/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([b['author'] for b in res.data], ['bob', 'alice'])

    def test_create_validates_url(self):
        self.client.force_authenticate(self.alice)
        res = self.client.post('/blogs/', {'url': 'not a url'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('url', res.data)

    @patch('blog_generator.views.generate_blog.delay')
    def test_create_saves_pending_blog_and_queues_it_after_commit(self, delay):
        self.client.force_authenticate(self.alice)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            res = self.client.post('/blogs/', {'url': 'https://example.com'}, format='json')
        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.data['status'], 'pending')
        self.assertEqual(res.data['content'], '')
        # Nothing is published until the transaction commits.
        delay.assert_not_called()
        for callback in callbacks:
            callback()
        delay.assert_called_once_with(res.data['id'])

    def test_detail_returns_my_blog(self):
        self.client.force_authenticate(self.alice)
        blog = Blog.objects.get(user=self.alice)
        res = self.client.get(f'/blogs/{blog.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['content'], 'Alice blog')

    def test_detail_hides_other_users_blogs(self):
        self.client.force_authenticate(self.alice)
        blog = Blog.objects.get(user=self.bob)
        self.assertEqual(self.client.get(f'/blogs/{blog.id}/').status_code, 404)

    def test_all_blogs_is_read_only(self):
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.post('/blogs/all/', {'url': 'https://x.com'}, format='json').status_code, 405)


class GenerateBlogTaskTests(APITestCase):
    def setUp(self):
        user = User.objects.create_user('alice', 'alice@example.com', 'S3cure-pass-123')
        self.blog = Blog.objects.create(user=user, url='https://youtu.be/x')

    @patch('blog_generator.generation.generate_blog_content', return_value='An article')
    def test_saves_content_on_success(self, generate_content):
        generate_blog(self.blog.id)
        self.blog.refresh_from_db()
        generate_content.assert_called_once_with('https://youtu.be/x')
        self.assertEqual(self.blog.status, Blog.Status.COMPLETED)
        self.assertEqual(self.blog.content, 'An article')

    @patch('blog_generator.generation.generate_blog_content', side_effect=RuntimeError('Video unavailable'))
    def test_records_error_on_failure(self, generate_content):
        with self.assertLogs('blog_generator.tasks', 'ERROR'):
            generate_blog(self.blog.id)
        self.blog.refresh_from_db()
        self.assertEqual(self.blog.status, Blog.Status.FAILED)
        self.assertEqual(self.blog.error, 'Video unavailable')
