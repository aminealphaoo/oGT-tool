# Render free tier: a single web process. No Celery worker / beat (no Redis).
# Scheduled tasks: cron-job.org → GET/POST https://<app>.onrender.com/api/cron/<task>/
#   ping         every 10 min (keep-alive, no secret required)
#   stale        daily (header X-Cron-Secret)
#   digest       weekly
#   stage_emails hourly (drain pending EmailLog if sync SMTP failed)
web: gunicorn aiesec_tool.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120
