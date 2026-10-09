from django.db import models


class ServerEvent(models.Model):
    ACTION_CHOICES = (
        ('job_created', 'Задание создано'),
        ('job_sent', 'Задание отправлено'),
        ('template_updated', 'Шаблон обновлён'),
        ('product_added', 'Товар добавлен'),
        ('report_imported', 'Отчёт импортирован'),
        ('station_synced', 'Станция синхронизирована'),
        ('other', 'Прочее'),
    )

    action = models.CharField(max_length=30, choices=ACTION_CHOICES, verbose_name='Действие')
    description = models.TextField(verbose_name='Описание')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')

    def __str__(self):
        return f"[{self.get_action_display()}] {self.description[:80]}"

    class Meta:
        verbose_name = 'Серверное событие'
        verbose_name_plural = 'Серверные события'
        ordering = ['-created_at']


class LoginThrottle(models.Model):
    """Wrong passwords per computer (IP) and login, and the lock that follows too many.
    `username` is lower-cased; "" holds the computer's total over all logins. Kept in the
    database (not memory) so the password-reset tool on the server can lift a lock."""
    ip = models.CharField(max_length=64)
    username = models.CharField(max_length=150, blank=True, default='')
    failures = models.PositiveIntegerField(default=0)
    last_failure_at = models.DateTimeField()
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Неверные входы'
        verbose_name_plural = 'Неверные входы'
        constraints = [models.UniqueConstraint(fields=['ip', 'username'], name='login_throttle_ip_username')]
