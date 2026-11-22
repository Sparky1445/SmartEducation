"""Sign up, remember-me login, profile editing, password reset, admin inline."""

from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from repository.models import Resource, Subject

from .forms import SignUpForm
from .models import Profile


def signup_data(**extra):
    data = {
        "username": "sana", "first_name": "Sana", "last_name": "K", "email": "Sana@Example.com",
        "role": "student", "grade": "7", "password1": "monsoon-river-42", "password2": "monsoon-river-42",
    }
    data.update(extra)
    return data


class SignUpTests(TestCase):
    def test_student_signup_logs_in_with_profile_and_group(self):
        response = self.client.post(reverse("accounts:signup"), signup_data())
        self.assertRedirects(response, reverse("dashboard:home"), fetch_redirect_response=False)
        user = User.objects.get(username="sana")
        self.assertEqual(user.email, "sana@example.com")
        self.assertEqual((user.profile.role, user.profile.grade), ("student", 7))
        self.assertTrue(user.groups.filter(name="Student").exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_student_needs_class_parent_does_not(self):
        self.assertIn("grade", SignUpForm(signup_data(grade="")).errors)
        form = SignUpForm(signup_data(role="parent", grade=""))
        self.assertTrue(form.is_valid(), form.errors)

    def test_duplicate_email_and_weak_password(self):
        User.objects.create_user("x", email="sana@example.com", password="pass12345")
        form = SignUpForm(signup_data(password1="12345678", password2="12345678"))
        self.assertIn("email", form.errors)
        self.assertIn("password2", form.errors)

    def test_cannot_sign_up_as_teacher(self):
        self.assertIn("role", SignUpForm(signup_data(role="teacher")).errors)


class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_user("sana", password="monsoon-river-42", email="sana@example.com", first_name="Sana")

    def test_remember_me_controls_session_length(self):
        self.client.post(reverse("login"), {"username": "sana", "password": "monsoon-river-42", "remember": "on"})
        self.assertEqual(self.client.session.get_expiry_age(), 14 * 24 * 3600)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.client.logout()
        self.client.post(reverse("login"), {"username": "sana", "password": "monsoon-river-42"})
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_wrong_password_message(self):
        page = self.client.post(reverse("login"), {"username": "sana", "password": "nope"})
        self.assertContains(page, "didn't match")

    def test_password_reset_email(self):
        self.client.post(reverse("password_reset"), {"email": "sana@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Reset your Smart Education password")
        self.assertIn("/accounts/reset/", mail.outbox[0].body)

    def test_logout_is_post_only(self):
        self.client.login(username="sana", password="monsoon-river-42")
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sana", password="monsoon-river-42", first_name="Sana")
        self.user.profile.role = Profile.Role.STUDENT
        self.user.profile.grade = 7
        self.user.profile.save()
        self.client.login(username="sana", password="monsoon-river-42")

    def test_profile_created_automatically(self):
        self.assertTrue(Profile.objects.filter(user__username="sana").exists())

    def test_edit_profile_sets_language_cookie(self):
        response = self.client.post(reverse("accounts:profile"), {
            "first_name": "Sana", "last_name": "Kamat", "email": "sana@example.com",
            "grade": "8", "school": "PM SHRI HBGDM GHS", "language": "kok", "bio": "",
        })
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual((self.user.last_name, self.user.profile.grade), ("Kamat", 8))
        self.assertEqual(response.cookies["se_lang"].value, "kok")

    def test_student_dashboard_shows_lessons_for_class(self):
        sci = Subject.objects.get(slug="science")
        Resource.objects.create(title="Light and shadows", subject=sci, grade=7, kind="link", url="https://example.com")
        Resource.objects.create(title="Algebra basics", subject=sci, grade=9, kind="link", url="https://example.com")
        page = self.client.get(reverse("dashboard:student"))
        self.assertContains(page, "For class 7")
        self.assertContains(page, "Light and shadows")
        self.assertNotContains(page, "Algebra basics")

    def test_admin_shows_profile_inline(self):
        User.objects.create_superuser("admin", "a@example.com", "pass12345")
        self.client.login(username="admin", password="pass12345")
        page = self.client.get(reverse("admin:auth_user_change", args=[self.user.pk]))
        self.assertContains(page, "profile-0-grade")
