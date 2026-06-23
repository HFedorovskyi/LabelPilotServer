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
