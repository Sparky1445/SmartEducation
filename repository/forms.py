from pathlib import Path

from django import forms
from django.utils.text import slugify

from .models import Resource, Subject, Tag

INPUT = {"class": "field-input"}
MAX_MB = 20
ALLOWED = {".pdf", ".pptx", ".txt", ".md", ".docx", ".jpg", ".jpeg", ".png", ".mp4"}


class SearchForm(forms.Form):
    """GET form for browsing (Unit IV: GET vs POST)."""

    q = forms.CharField(required=False, max_length=100, widget=forms.TextInput(attrs={**INPUT, "placeholder": "Search lessons: photosynthesis, fractions, the water cycle…"}))
    subject = forms.ModelChoiceField(Subject.objects.all(), required=False, to_field_name="slug", empty_label="All subjects", widget=forms.Select(attrs=INPUT))
    grade = forms.TypedChoiceField(choices=[("", "All classes")] + Resource.GRADES, required=False, coerce=int, empty_value=None, widget=forms.Select(attrs=INPUT))
    kind = forms.ChoiceField(choices=[("", "All types")] + Resource.Kind.choices, required=False, widget=forms.Select(attrs=INPUT))
    sort = forms.ChoiceField(choices=[("new", "Newest"), ("popular", "Most viewed"), ("title", "A–Z")], required=False, widget=forms.Select(attrs=INPUT))


class ResourceForm(forms.ModelForm):
    tag_names = forms.CharField(
        required=False,
        label="Tags",
        help_text="Comma-separated, e.g. water cycle, evaporation, clouds",
        widget=forms.TextInput(attrs=INPUT),
    )

    class Meta:
        model = Resource
        fields = ["title", "subject", "grade", "kind", "description", "file", "url", "status"]
        widgets = {
            "title": forms.TextInput(attrs=INPUT),
            "subject": forms.Select(attrs=INPUT),
            "grade": forms.Select(attrs=INPUT),
            "kind": forms.Select(attrs=INPUT),
            "description": forms.Textarea(attrs={**INPUT, "rows": 4}),
            "file": forms.ClearableFileInput(attrs={"class": "field-file"}),
            "url": forms.URLInput(attrs={**INPUT, "placeholder": "https://www.youtube.com/watch?v=…"}),
            "status": forms.Select(attrs=INPUT),
        }
        labels = {"kind": "Type", "grade": "Class", "url": "Link"}
        help_texts = {"file": f"PDF, PowerPoint, Word, text, image or MP4, up to {MAX_MB} MB. PDF and PowerPoint lessons can be asked about."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["tag_names"].initial = ", ".join(t.name for t in self.instance.tags.all())

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if f and hasattr(f, "size"):
            ext = Path(f.name).suffix.lower()
            if ext not in ALLOWED:
                raise forms.ValidationError(f"{ext or 'This'} files are not allowed. Use one of: {', '.join(sorted(ALLOWED))}.")
            if f.size > MAX_MB * 1024 * 1024:
                raise forms.ValidationError(f"The file is {f.size // (1024 * 1024)} MB. The limit is {MAX_MB} MB.")
        return f

    def clean_tag_names(self):
        names = [" ".join(n.split()).lower() for n in self.cleaned_data["tag_names"].split(",")]
        names = list(dict.fromkeys(n for n in names if n))
        if len(names) > 8:
            raise forms.ValidationError("Use at most 8 tags.")
        return names

    def clean(self):
        data = super().clean()
        has_file = bool(data.get("file")) and data.get("file") is not False
        kind, url = data.get("kind"), data.get("url")
        if not has_file and not url:
            raise forms.ValidationError("Add a file or a link, otherwise there is nothing to open.")
        if kind in {Resource.Kind.VIDEO, Resource.Kind.LINK} and not url and not has_file:
            self.add_error("url", "Videos and web links need a link.")
        if kind in {Resource.Kind.DOCUMENT, Resource.Kind.SLIDES} and not has_file:
            self.add_error("file", "Notes and slides need a file.")
        return data

    def save(self, commit=True):
        resource = super().save(commit=commit)
        if commit:
            tags = [Tag.objects.get_or_create(slug=slugify(n)[:50] or n[:50], defaults={"name": n})[0] for n in self.cleaned_data["tag_names"]]
            resource.tags.set(tags)
        return resource
