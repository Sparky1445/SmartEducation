from django import forms

from .models import GRADES, Topic


class QuizForm(forms.Form):
    """Built at runtime from the quiz's questions: one radio group per question (Unit IV)."""

    def __init__(self, quiz, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.quiz = quiz
        for i, q in enumerate(quiz.questions):
            self.fields[f"q{i}"] = forms.TypedChoiceField(
                label=q["q"],
                choices=[(j, opt) for j, opt in enumerate(q["options"])],
                coerce=int,
                widget=forms.RadioSelect,
                error_messages={"required": "Choose an answer for this question."},
            )

    def answers(self) -> list[int]:
        return [self.cleaned_data[f"q{i}"] for i in range(len(self.quiz.questions))]

    def score(self) -> int:
        return sum(1 for chosen, q in zip(self.answers(), self.quiz.questions) if chosen == q["answer"])


class SyllabusPickForm(forms.Form):
    grade = forms.TypedChoiceField(choices=GRADES, coerce=int, widget=forms.Select(attrs={"class": "field-input"}))


class QuizFromKitForm(forms.Form):
    topic = forms.ModelChoiceField(
        Topic.objects.select_related("unit__subject"), required=False, empty_label="No topic (stand-alone quiz)",
        widget=forms.Select(attrs={"class": "field-input"}),
    )
