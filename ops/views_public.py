from django.shortcuts import render, redirect
from django.contrib import messages
from .forms_public import PublicEPForm, PublicTestimonialForm
from .models import Campaign, Lead

def public_intake(request):
    """
    Public landing page for external EPs or ancient EPs to submit their info.
    If a campaign_id GET parameter is provided, submissions are logged as Leads linked to that Campaign.
    """
    campaign_id = request.GET.get('campaign') or request.GET.get('campaign_id')
    campaign = Campaign.objects.filter(id=campaign_id).first() if campaign_id else None

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'ep':
            form = PublicEPForm(request.POST)
            if form.is_valid():
                ep = form.save()
                
                # Also log as a Lead for BD Campaign tracking
                names = (ep.full_name or "").split(" ", 1)
                first_name = names[0]
                last_name = names[1] if len(names) > 1 else ""
                
                Lead.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    email=ep.email,
                    phone=ep.phone,
                    university=ep.university,
                    interest_track=ep.track,
                    source_campaign=campaign,
                    converted_to_ep=ep,
                    status='New'
                )
                if campaign:
                    campaign.leads_generated = campaign.leads.count()
                    campaign.save(update_fields=['leads_generated'])

                messages.success(request, "Your details have been submitted successfully! We will contact you soon.")
                return redirect('public_intake_success')
        elif form_type == 'testimonial':
            form = PublicTestimonialForm(request.POST)
            if form.is_valid():
                testimonial = form.save(commit=False)
                testimonial.status = 'raw'
                testimonial.save()
                messages.success(request, "Thank you for sharing your experience!")
                return redirect('public_intake_success')
    else:
        ep_form = PublicEPForm()
        test_form = PublicTestimonialForm()

    context = {
        'ep_form': ep_form if request.method != 'POST' or form_type != 'ep' else form,
        'test_form': test_form if request.method != 'POST' or form_type != 'testimonial' else form,
        'campaign': campaign,
    }
    return render(request, 'public/intake_form.html', context)

def public_intake_success(request):
    return render(request, 'public/intake_success.html')
