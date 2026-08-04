"""
WSGI config for aiesec_tool.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aiesec_tool.settings")
application = get_wsgi_application()
