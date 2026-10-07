import uuid
from django.db import models
from django.contrib.auth.hashers import make_password


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
    # When the station last got the data set (push, USB file or its own pull). last_sync_at
    # also moves when a report arrives, so it cannot tell whether product changes reached it.
    data_pushed_at = models.DateTimeField(null=True, blank=True, verbose_name='Данные переданы станции')
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True, null=True)

    # Named-seat licensing (licensing/seats.py). Existing stations keep their seat.
    SEAT_CHOICES = (
        ('active', 'Место выдано'),
        ('pending', 'Ожидает места'),
        ('released', 'Место освобождено'),
    )
    seat_state = models.CharField(
        max_length=16, choices=SEAT_CHOICES, default='active', db_index=True,
        verbose_name='Лицензионное место',
    )
    seat_changed_at = models.DateTimeField(null=True, blank=True)
    # Hardware fingerprint the station reported first (32 hex), and the last
    # different device that announced the same identity.
    station_fingerprint = models.CharField(max_length=32, blank=True, default='')
    conflict_fingerprint = models.CharField(max_length=32, blank=True, default='')

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


class SeatEvent(models.Model):
    """Audit trail of seat assignments, releases and hardware changes. Releases
    within the last 30 days are rate limited (licensing/seats.py)."""
    station = models.ForeignKey(
        'LabelsStations', null=True, blank=True, on_delete=models.SET_NULL, related_name='seat_events',
    )
    station_uuid = models.UUIDField(null=True, blank=True)
    station_name = models.CharField(max_length=100, blank=True, default='')
    event = models.CharField(max_length=32, db_index=True)
    actor = models.CharField(max_length=150, blank=True, default='')
    detail = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.event} {self.station_name}"


class Operator(models.Model):
    """Factory-floor worker. Server-managed master data, synced to client stations and
    used for print attribution. NOT a Django auth User. PIN is stored hashed; the hash
    is synced so the client can validate the PIN locally/offline (workflow + audit, not
    a security boundary). station=null -> available on ALL stations (shared pool)."""
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    full_name = models.CharField(max_length=200, verbose_name='ФИО')
    short_code = models.CharField(max_length=50, blank=True, default='', verbose_name='Код/таб. номер')
    pin_hash = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    station = models.ForeignKey(
        'LabelsStations', null=True, blank=True, on_delete=models.CASCADE,
        related_name='operators', verbose_name='Станция',
        help_text='Пусто = доступен на всех станциях',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def set_pin(self, pin):
        self.pin_hash = make_password(str(pin)) if pin not in (None, '') else ''

    def __str__(self):
        return self.full_name
