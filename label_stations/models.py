import uuid
from django.db import models


class LabelsStations(models.Model):
    MODE_CHOICES = (
        ('online', 'Онлайн'),
        ('offline', 'Оффлайн'),
        ('hybrid', 'Гибрид'),
    )

    station_name = models.CharField(max_length=100, default='Станция маркировки')
    station_number = models.IntegerField(
        unique=True, null=True, blank=True,
        help_text='Уникальный двухзначный номер станции (01-99)'
    )
    station_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    station_ip = models.GenericIPAddressField(null=True, blank=True)
    station_port = models.IntegerField(default=5000)
    is_online = models.BooleanField(default=False)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='online', verbose_name='Режим работы')
    last_sync_at = models.DateTimeField(null=True, blank=True, verbose_name='Последняя синхронизация')
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True, null=True)

    def save(self, *args, **kwargs):
        if self.station_number is None:
            # Find the smallest available number from 1 to 99
            used = set(
                LabelsStations.objects.exclude(pk=self.pk)
                .values_list('station_number', flat=True)
            )
            for n in range(1, 100):
                if n not in used:
                    self.station_number = n
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.station_number:02d}] {self.station_name}" if self.station_number else self.station_name
