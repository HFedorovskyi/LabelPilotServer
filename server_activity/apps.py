from django.apps import AppConfig


class ServerActivityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'server_activity'
    verbose_name = 'Серверная лента действий'
