import os
from celery import Celery

# Point Celery at your Django settings module.
# Adjust "config.settings" if your settings file lives elsewhere
# (e.g. "config.settings.dev").
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# The name here should match your project package.
app = Celery("config")

# Load any CELERY_* settings from Django settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-find tasks.py in each installed app.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
