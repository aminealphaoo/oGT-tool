from django import forms

from .models import IR, Opportunity


class IRForm(forms.ModelForm):
    class Meta:
        model = IR
        fields = [
            "entity_name",
            "country",
            "status",
            "tier",
            "contract_start",
            "contract_end",
            "testimonials_link",
            "opportunities_page_link",
            "whatsapp_group_link",
            "vp_contact",
            "assigned_to",
        ]
        widgets = {
            "contract_start": forms.DateInput(attrs={"type": "date"}),
            "contract_end": forms.DateInput(attrs={"type": "date"}),
        }


class OpportunityForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["title", "type", "description", "is_open", "expires_at", "track"]
