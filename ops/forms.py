from django import forms

from .models import EP, Attachment, Task


class EPForm(forms.ModelForm):
    """EP create/edit form — includes new profile fields for intelligent matching."""

    # JSON fields as simple text inputs
    skills_text = forms.CharField(
        required=False,
        label="Skills",
        widget=forms.TextInput(attrs={"placeholder": "Python, Marketing, Design (comma-separated)"}),
        help_text="Comma-separated list of skills",
    )
    preferred_countries_text = forms.CharField(
        required=False,
        label="Preferred Countries",
        widget=forms.TextInput(attrs={"placeholder": "Germany, France, Spain (comma-separated)"}),
        help_text="Comma-separated list of preferred countries",
    )
    languages_text = forms.CharField(
        required=False,
        label="Languages (JSON)",
        widget=forms.TextInput(attrs={"placeholder": '{"English": "B2", "French": "C1"}'}),
        help_text='JSON object: {"Language": "Level (A1-C2)"}',
    )

    class Meta:
        model = EP
        fields = [
            "full_name", "phone", "email", "socials",
            "university", "major", "year_of_study",
            "track", "current_stage", "assigned_to", "term",
            # Profile fields for matching
            "study_field", "study_level", "experience_level",
            "availability_date", "duration_preference", "keywords",
        ]
        widgets = {
            "socials": forms.Textarea(attrs={"rows": 2}),
            "keywords": forms.Textarea(attrs={"rows": 2, "placeholder": "Free keywords separated by commas..."}),
            "availability_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Pre-populate JSON fields
            skills = self.instance.skills or []
            self.fields["skills_text"].initial = ", ".join(skills)
            countries = self.instance.preferred_countries or []
            self.fields["preferred_countries_text"].initial = ", ".join(countries)
            import json
            langs = self.instance.languages or {}
            self.fields["languages_text"].initial = json.dumps(langs, ensure_ascii=False) if langs else ""

    def save(self, commit=True):
        import json
        instance = super().save(commit=False)
        # Parse skills
        skills_raw = self.cleaned_data.get("skills_text", "")
        instance.skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
        # Parse preferred countries
        countries_raw = self.cleaned_data.get("preferred_countries_text", "")
        instance.preferred_countries = [c.strip() for c in countries_raw.split(",") if c.strip()]
        # Parse languages JSON
        langs_raw = self.cleaned_data.get("languages_text", "").strip()
        try:
            instance.languages = json.loads(langs_raw) if langs_raw else {}
        except (json.JSONDecodeError, ValueError):
            instance.languages = {}
        if commit:
            instance.save()
        return instance


class StageAdvanceForm(forms.Form):
    """Advance EP to a new stage."""

    new_stage = forms.ChoiceField(choices=EP.Stage.choices)
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional note..."}),
        required=False,
    )


class ProblemFlagForm(forms.Form):
    """Set problem flag on an EP."""

    flag = forms.ChoiceField(choices=EP.ProblemFlag.choices)
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "What's the problem?"}),
        required=False,
    )


class InteractionForm(forms.Form):
    """Log an interaction with an EP."""

    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "What happened?"}),
    )


class AttachmentForm(forms.ModelForm):
    """Upload an attachment to an EP."""

    class Meta:
        model = Attachment
        fields = ["file", "label"]


class TaskForm(forms.ModelForm):
    """Create/edit a task."""

    class Meta:
        model = Task
        fields = ["title", "description", "due_date", "priority", "status", "assigned_to", "related_ep", "related_partner"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Task details..."}),
            "due_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

