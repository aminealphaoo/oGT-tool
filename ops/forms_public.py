from django import forms
from ops.models import EP, Testimonial

class PublicEPForm(forms.ModelForm):
    class Meta:
        model = EP
        fields = ['full_name', 'email', 'phone', 'university', 'track']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'required': True}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'university': forms.TextInput(attrs={'class': 'form-control'}),
            'track': forms.Select(attrs={'class': 'form-select'}),
        }

class PublicTestimonialForm(forms.ModelForm):
    class Meta:
        model = Testimonial
        fields = ['ancient_ep_name', 'ancient_ep_email', 'content', 'video_url']
        widgets = {
            'ancient_ep_name': forms.TextInput(attrs={'class': 'form-control', 'required': True, 'placeholder': 'Your Full Name'}),
            'ancient_ep_email': forms.EmailInput(attrs={'class': 'form-control', 'required': True, 'placeholder': 'Your Email'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'required': True, 'rows': 4, 'placeholder': 'Share your experience...'}),
            'video_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Link to video (optional)'}),
        }
