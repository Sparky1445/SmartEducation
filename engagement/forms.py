"""Engagement forms (Unit IV): ModelForms with field and cross-field validation, plus a honeypot."""

import re

from django import forms

from .models import Comment, Feedback, NewsletterSubscriber

INPUT = {"class": "field-input"}
LINKS = re.compile(r"https?://|www\.", re.I)


class HoneypotMixin(forms.Form):
    """A hidden field real people never fill. Bots usually do."""

    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam check failed.")
        return ""


class CommentForm(forms.ModelForm):
    parent_id = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={**INPUT, "rows": 3, "placeholder": "Ask a doubt or share a tip with other students…"})}
        labels = {"body": "Your comment"}

    def clean_body(self):
        body = " ".join(self.cleaned_data["body"].split())
        if len(body) < 3:
            raise forms.ValidationError("Write a little more.")
        if len(LINKS.findall(body)) > 1:
            raise forms.ValidationError("Comments can contain at most one link.")
        return body


class RatingForm(forms.Form):
    stars = forms.TypedChoiceField(choices=[(i, i) for i in range(1, 6)], coerce=int)


class FeedbackForm(HoneypotMixin, forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ["name", "email", "category", "message", "page_url"]
        widgets = {
            "name": forms.TextInput(attrs=INPUT),
            "email": forms.EmailInput(attrs=INPUT),
            "category": forms.Select(attrs=INPUT),
            "message": forms.Textarea(attrs={**INPUT, "rows": 6}),
            "page_url": forms.HiddenInput,
        }
        labels = {"category": "What is it about?", "message": "Your message"}

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if len(message.split()) < 4:
            raise forms.ValidationError("Please write at least a short sentence so we can help.")
        return message

    def clean(self):
        data = super().clean()
        # Cross-field rule: a problem report must say what went wrong, not just "broken".
        if data.get("category") == Feedback.Category.PROBLEM and len(data.get("message", "").split()) < 8:
            self.add_error("message", "For a problem, tell us what you did and what happened (at least 8 words).")
        return data


class NewsletterForm(HoneypotMixin, forms.ModelForm):
    consent = forms.BooleanField(label="Send me a short email when new lessons are published.")

    class Meta:
        model = NewsletterSubscriber
        fields = ["email", "name", "language"]
        widgets = {
            "email": forms.EmailInput(attrs={**INPUT, "placeholder": "you@example.com"}),
            "name": forms.TextInput(attrs={**INPUT, "placeholder": "First name (optional)"}),
            "language": forms.Select(attrs=INPUT),
        }

    def validate_unique(self):
        # Re-subscribing with a known email is allowed: the view reactivates it.
        pass

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
