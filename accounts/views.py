"""Sign up, log in (with "keep me logged in"), profile."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, ProfileForm, SignUpForm, UserEditForm
from .models import Profile

TWO_WEEKS = 14 * 24 * 3600


class RememberMeLoginView(LoginView):
    """Unticked "keep me logged in" = the session ends when the browser closes (Unit VI)."""

    form_class = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(TWO_WEEKS if form.cleaned_data.get("remember") else 0)
        return response


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                if user.profile.role == Profile.Role.STUDENT:
                    group, _ = Group.objects.get_or_create(name="Student")
                    user.groups.add(group)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, f"Welcome, {user.first_name}. Your account is ready.")
            response = redirect("dashboard:home")
            response.set_cookie("se_lang", user.profile.language, max_age=365 * 24 * 3600, samesite="Lax")
            return response
    else:
        form = SignUpForm(initial={"role": Profile.Role.STUDENT})
    return render(request, "accounts/signup.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    prof, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        user_form = UserEditForm(request.POST, instance=request.user)
        profile_form = ProfileForm(request.POST, instance=prof)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            prof = profile_form.save()
            messages.success(request, "Profile saved.")
            response = redirect("accounts:profile")
            response.set_cookie("se_lang", prof.language, max_age=365 * 24 * 3600, samesite="Lax")
            return response
    else:
        user_form = UserEditForm(instance=request.user)
        profile_form = ProfileForm(instance=prof)
    return render(request, "accounts/profile.html", {"user_form": user_form, "profile_form": profile_form, "prof": prof})
