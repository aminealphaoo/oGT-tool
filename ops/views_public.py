from django.shortcuts import render, redirect
from django.contrib import messages
from .forms_public import PublicEPForm, PublicTestimonialForm

def public_intake(request):
    """
    Public landing page for external EPs or ancient EPs to submit their info.
    """
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'ep':
            form = PublicEPForm(request.POST)
            if form.is_valid():
                form.save()
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
    }
    return render(request, 'public/intake_form.html', context)

def public_intake_success(request):
    return render(request, 'public/intake_success.html')
