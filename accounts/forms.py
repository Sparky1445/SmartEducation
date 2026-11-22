from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Profile

INPUT = {"class": "field-input"}


class LoginForm(AuthenticationForm):
    remember = forms.BooleanField(required=False, initial=True, label="Keep me logged in on this device")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({**INPUT, "autofocus": True})
        self.fields["password"].widget.attrs.update(INPUT)


class SignUpForm(UserCreationForm):
    """Students and parents sign up themselves; teachers are added by the school."""

    first_name = forms.CharField(max_length=40, label="First name", widget=forms.TextInput(attrs=INPUT))
    last_name = forms.CharField(max_length=40, required=False, label="Last name", widget=forms.TextInput(attrs=INPUT))
    email = forms.EmailField(widget=forms.EmailInput(attrs=INPUT), help_text="Used only to reset your password and, if you want, for the newsletter.")
    role = forms.ChoiceField(
        choices=[(Profile.Role.STUDENT, "Student"), (Profile.Role.PARENT, "Parent or guardian"), (Profile.Role.VISITOR, "Visitor")],
        widget=forms.RadioSelect,
        label="I am a",
    )
    grade = forms.TypedChoiceField(choices=[("", "Choose your class")] + Profile.GRADES, coerce=int, empty_value=None, required=False, label="Class", widget=forms.Select(attrs=INPUT))

    field_order = ["role", "grade", "first_name", "last_name", "username", "email", "password1", "password2"]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        widgets = {"username": forms.TextInput(attrs=INPUT)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("password1", "password2"):
            self.fields[name].widget.attrs.update(INPUT)
        self.fields["username"].help_text = "You log in with this. Letters, numbers and . _ - only."
        self.fields["password2"].help_text = ""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try logging in or resetting your password.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("role") == Profile.Role.STUDENT and not data.get("grade"):
            self.add_error("grade", "Students need to choose their class.")
        if data.get("role") != Profile.Role.STUDENT:
            data["grade"] = None
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()  # the signal creates the profile
            profile = user.profile
            profile.role = self.cleaned_data["role"]
            profile.grade = self.cleaned_data["grade"]
            profile.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {f: forms.TextInput(attrs=INPUT) for f in ("first_name", "last_name")} | {"email": forms.EmailInput(attrs=INPUT)}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["grade", "school", "language", "bio"]
        widgets = {
            "grade": forms.Select(attrs=INPUT),
            "school": forms.TextInput(attrs=INPUT),
            "language": forms.Select(attrs=INPUT),
            "bio": forms.TextInput(attrs={**INPUT, "placeholder": "One line about you (optional)"}),
        }
        labels = {"grade": "Class", "language": "Preferred language", "bio": "About you"}

    def clean(self):
        data = super().clean()
        if self.instance.role == Profile.Role.STUDENT and not data.get("grade"):
            self.add_error("grade", "Students need a class so we can suggest the right lessons.")
        return data
