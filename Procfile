web: gunicorn aiesec_tool.wsgi --log-file -
worker: celery -A aiesec_tool worker -l info --concurrency=1
beat: celery -A aiesec_tool beat -l info
