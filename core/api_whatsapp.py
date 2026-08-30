import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from ops.models import EP
import hmac
import hashlib

def send_whatsapp_message(phone_number, message_body):
    """
    Placeholder function for integrating with a WhatsApp Business API provider
    (e.g., Twilio, Wati, Meta Graph API).
    """
    # Example for Twilio:
    # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    # message = client.messages.create(
    #     body=message_body,
    #     from_='whatsapp:+14155238886',
    #     to=f'whatsapp:{phone_number}'
    # )
    
    # For now, just log it.
    print(f"[WhatsApp] Sending to {phone_number}: {message_body}")
    return True

@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookView(View):
    """
    Generic webhook to receive incoming WhatsApp messages.
    """
    def get(self, request, *args, **kwargs):
        # Verification for Meta Graph API or Twilio
        verify_token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        # In a real app, verify `verify_token` against settings
        if challenge:
            return JsonResponse({'hub.challenge': challenge}, status=200)
            
        return JsonResponse({"status": "ok"})

    def post(self, request, *args, **kwargs):
        # HMAC Signature Validation
        signature = request.headers.get("X-Hub-Signature-256", "")
        secret = getattr(settings, "WHATSAPP_WEBHOOK_SECRET", "")
        
        if secret:
            expected_signature = "sha256=" + hmac.new(
                secret.encode("utf-8"),
                request.body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                return JsonResponse({"status": "error", "message": "Invalid signature"}, status=403)
                
        try:
            # Try parsing JSON (Meta API style)
            data = json.loads(request.body)
            # This parsing logic depends heavily on the provider.
            # We'll write generic pseudo-parsing here.
            
            # Basic fallback for form-encoded (Twilio style)
            if not data:
                data = request.POST.dict()
                
            sender = data.get("From", "").replace("whatsapp:", "")
            body = data.get("Body", "").strip().lower()

            # Simple keyword router
            if body == "status":
                self.handle_status_request(sender)
            elif body == "help":
                send_whatsapp_message(sender, "Available commands: 'status' to check your EP process.")
            else:
                send_whatsapp_message(sender, "Sorry, I didn't understand that. Type 'help'.")
                
            return JsonResponse({"status": "received"})
            
        except Exception as e:
            print(f"Webhook Error: {e}")
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    def handle_status_request(self, sender_phone):
        # Remove country code approximations for naive matching (in production, use standard E.164 parsing)
        if sender_phone.startswith("+"):
            sender_phone = sender_phone[1:]
            
        # Try to find EP by phone
        ep = EP.objects.filter(phone__icontains=sender_phone).order_by('-created_at').first()
        
        if ep:
            msg = f"Hi {ep.full_name}, your current stage is *{ep.get_current_stage_display()}*."
            if ep.matched_opportunity:
                msg += f" You are matched with {ep.matched_opportunity.ir.entity_name}."
            send_whatsapp_message(sender_phone, msg)
        else:
            send_whatsapp_message(sender_phone, "We couldn't find an EP profile linked to this number.")
