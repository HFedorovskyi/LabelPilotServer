import os
import sys

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'

    def ready(self):
        # Development server only (production starts the worker from serve.py). With the
        # autoreloader the parent process just watches files; the child sets RUN_MAIN.
        if 'runserver' in sys.argv and (os.environ.get('RUN_MAIN') == 'true' or '--noreload' in sys.argv):
            from .worker import start_worker
            start_worker()
