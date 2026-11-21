from django import forms


class AskForm(forms.Form):
    question = forms.CharField(
        max_length=500,
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "placeholder": "What is the difference between weather and climate?",
                "autocomplete": "off",
                "autofocus": True,
            }
        ),
    )

    def clean_question(self):
        text = " ".join(self.cleaned_data["question"].split())
        if len(text.split()) < 2:
            raise forms.ValidationError("Ask a full question, at least two words.")
        if not any(ch.isalpha() for ch in text):
            raise forms.ValidationError("The question needs some words, not only numbers or symbols.")
        return text


class FeedbackForm(forms.Form):
    helpful = forms.TypedChoiceField(choices=[("yes", "yes"), ("no", "no")], coerce=lambda v: v == "yes")
