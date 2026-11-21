"""Edit forms for kit items. Each turns the item's JSON into plain fields a teacher can edit."""

from django import forms

TEXTAREA = {"class": "field-input field-input--area", "rows": 6}


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]


class SummaryForm(forms.Form):
    title = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"class": "field-input"}))
    points = forms.CharField(widget=forms.Textarea(attrs=TEXTAREA), help_text="One key point per line.")

    @classmethod
    def initial_from(cls, content):
        return {"title": content.get("title", ""), "points": "\n".join(content.get("points", []))}

    def clean_points(self):
        points = _lines(self.cleaned_data["points"])
        if not 2 <= len(points) <= 8:
            raise forms.ValidationError("Write between 2 and 8 points, one per line.")
        return points

    def to_content(self, old):
        return {"title": self.cleaned_data["title"], "points": self.cleaned_data["points"]}


class ArticleForm(forms.Form):
    headline = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"class": "field-input"}))
    standfirst = forms.CharField(max_length=300, widget=forms.TextInput(attrs={"class": "field-input"}))
    body = forms.CharField(widget=forms.Textarea(attrs={**TEXTAREA, "rows": 10}), help_text="Leave a blank line between paragraphs.")

    @classmethod
    def initial_from(cls, content):
        return {"headline": content.get("headline", ""), "standfirst": content.get("standfirst", ""), "body": "\n\n".join(content.get("body", []))}

    def clean_body(self):
        paragraphs = _paragraphs(self.cleaned_data["body"])
        if not paragraphs:
            raise forms.ValidationError("The article needs at least one paragraph.")
        if sum(len(p.split()) for p in paragraphs) > 600:
            raise forms.ValidationError("Keep the article under 600 words.")
        return paragraphs

    def to_content(self, old):
        return dict(self.cleaned_data)


class SocialForm(forms.Form):
    posts = forms.CharField(widget=forms.Textarea(attrs=TEXTAREA), help_text="One post per line, as  Platform: text")
    poster_headline = forms.CharField(max_length=60, required=False, widget=forms.TextInput(attrs={"class": "field-input"}))
    poster_subline = forms.CharField(max_length=140, required=False, widget=forms.TextInput(attrs={"class": "field-input"}))
    poster_cta = forms.CharField(label="Poster call to action", max_length=60, required=False, widget=forms.TextInput(attrs={"class": "field-input"}))

    @classmethod
    def initial_from(cls, content):
        poster = content.get("poster", {})
        return {
            "posts": "\n".join(f"{p['platform']}: {p['text']}" for p in content.get("posts", [])),
            "poster_headline": poster.get("headline", ""),
            "poster_subline": poster.get("subline", ""),
            "poster_cta": poster.get("call_to_action", ""),
        }

    def clean_posts(self):
        posts = []
        for line in _lines(self.cleaned_data["posts"]):
            platform, sep, text = line.partition(":")
            if not sep or not text.strip():
                raise forms.ValidationError(f"Write each post as  Platform: text  (problem in “{line[:40]}”).")
            if platform.strip().lower() in {"x", "twitter"} and len(text.strip()) > 280:
                raise forms.ValidationError("The X post must be 280 characters or fewer.")
            posts.append({"platform": platform.strip(), "text": text.strip()})
        return posts

    def to_content(self, old):
        d = self.cleaned_data
        return {
            "posts": d["posts"],
            "poster": {"headline": d["poster_headline"], "subline": d["poster_subline"], "call_to_action": d["poster_cta"]},
        }


class TranslationForm(forms.Form):
    text = forms.CharField(widget=forms.Textarea(attrs=TEXTAREA))

    @classmethod
    def initial_from(cls, content):
        return {"text": content.get("text", "")}

    def to_content(self, old):
        return {"text": self.cleaned_data["text"].strip()}


FORMS = {"summary": SummaryForm, "article": ArticleForm, "social": SocialForm, "translation": TranslationForm}


def form_for(item, data=None):
    cls = FORMS.get(item.kind)
    if cls is None:
        return None
    return cls(data=data, initial=cls.initial_from(item.content), prefix=f"item{item.pk}")
