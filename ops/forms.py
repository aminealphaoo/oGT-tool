from django import forms

from .models import EP, Attachment


class EPForm(forms.ModelForm):
    """EP create/edit form."""

    class Meta:
        model = EP
        fields = [
            "full_name",
            "phone",
            "email",
            "socials",
            "university",
            "major",
            "year_of_study",
            "track",
            "current_stage",
            "assigned_to",
            "matched_opportunity",
            "term",
        ]
        widgets = {
            "socials": forms.Textarea(attrs={"rows": 2}),
        }


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
