from django.conf import settings
from django.db import models


class Notification(models.Model):
    """One open problem or event for the admin UI. Text is NOT stored: `code` + `params`
    are rendered by the frontend in the viewer's language. `key` identifies the cause, so
    a repeat updates the same row (count, last_at) and a cleared cause resolves it."""

    SEVERITIES = (
        ('critical', 'Критично'),
        ('error', 'Ошибка'),
        ('warning', 'Предупреждение'),
        ('info', 'Информация'),
    )

    key = models.CharField(max_length=191, db_index=True)
    code = models.CharField(max_length=64)
    severity = models.CharField(max_length=10, choices=SEVERITIES)
    params = models.JSONField(default=dict, blank=True)
    # Where the "Open" button leads in the admin UI (a menu key) and to what.
    link_tab = models.CharField(max_length=32, blank=True, default='')
    link_id = models.CharField(max_length=64, blank=True, default='')
    count = models.PositiveIntegerField(default=1)
    first_at = models.DateTimeField()
    last_at = models.DateTimeField(db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-last_at']
        indexes = [models.Index(fields=['key', 'resolved_at'])]

    def __str__(self):
        return f"[{self.severity}] {self.code} {self.key}"


class NotificationSeen(models.Model):
    """Per user: everything raised or repeated up to `seen_at` counts as read."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications_seen')
    seen_at = models.DateTimeField()
