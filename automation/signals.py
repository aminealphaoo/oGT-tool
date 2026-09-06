"""
Stage-change emails.

Sending is handled on EP.current_stage change in ops.signals (synchronous,
or Celery if USE_CELERY=True). This module stays imported from AppConfig.ready()
so existing deployments keep loading automation signals without double-sending.
"""
