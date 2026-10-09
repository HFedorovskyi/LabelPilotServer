from django.db import models
from label_stations.models import LabelsStations
from Nomenclature.models import Nomenclature
from Packs.models import Pack

class PrintedLabel(models.Model):
    station = models.ForeignKey(LabelsStations, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Станция")
    station_user_name = models.CharField(max_length=100, blank=True, verbose_name="Имя пользователя на станции")
    
    product = models.ForeignKey(Nomenclature, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Номенклатура")
    product_name_snapshot = models.CharField(max_length=255, blank=True, verbose_name="Название продукта (копия)")
    
    pack = models.ForeignKey(Pack, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Упаковка")
    pack_name_snapshot = models.CharField(max_length=255, blank=True, verbose_name="Название упаковки (копия)")
    
    unique_id = models.CharField(max_length=100, unique=True, verbose_name="Уникальный ID этикетки")
    printed_at = models.DateTimeField(verbose_name="Время печати")

    # Actual weighed net weight (grams) reported by the station. Used for VARIABLE-weight
    # products in the dashboard total (fixed-weight products use Nomenclature.fixed_weight_grams).
    # Nullable: legacy rows reported before this field existed have None.
    weight_netto_grams = models.FloatField(null=True, blank=True, verbose_name="Фактический вес нетто (г)")
    # A deleted weighing ("отвес"): the operator removed this pack from an open box. Excluded
    # from good-production counts/weight; surfaced separately on the dashboard.
    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="Отвес удалён")
    # When the station deleted it (NOT printed_at). The dashboard buckets "deleted today" by this,
    # so a pack printed yesterday but deleted today counts on the correct day. Null until deleted.
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Время удаления отвеса")

    # Audit / traceability passport fields, reported by the station per pack. Stored as the station
    # holds them (strings); blank/None for legacy rows reported before these fields existed.
    weight_brutto_grams = models.FloatField(null=True, blank=True, verbose_name="Вес брутто (г)")
    batch = models.CharField(max_length=100, blank=True, default='', verbose_name="Партия")
    production_date = models.CharField(max_length=32, blank=True, default='', verbose_name="Дата производства")
    expiration_date = models.CharField(max_length=32, blank=True, default='', verbose_name="Срок годности")
    barcode = models.CharField(max_length=128, blank=True, default='', verbose_name="Штрихкод/код маркировки")
    # Number of the box the pack went into (stations from 2.0.9 report it).
    box_number = models.CharField(max_length=64, blank=True, default='', verbose_name="Номер короба")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время получения сервером")

    def __str__(self):
        return f"{self.unique_id} ({self.product_name_snapshot})"

    class Meta:
        verbose_name = "Напечатанная этикетка"
        verbose_name_plural = "Напечатанные этикетки"
        ordering = ['-printed_at']


class PrintedContainer(models.Model):
    """A box or a pallet of a station: its number, what it holds and its weight. Stations from
    2.0.9 report them; a row is upserted by unique_id because an open box keeps growing and is
    closed (or deleted) later."""
    LEVELS = (('box', 'Короб'), ('pallet', 'Паллета'))

    station = models.ForeignKey(LabelsStations, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Станция")
    level = models.CharField(max_length=8, choices=LEVELS, db_index=True, verbose_name="Уровень")
    unique_id = models.CharField(max_length=100, unique=True, verbose_name="Уникальный ID")
    number = models.CharField(max_length=64, verbose_name="Номер")
    product = models.ForeignKey(Nomenclature, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Номенклатура")
    # The product of a box; a pallet may hold several («Ветчина, Колбаса»).
    product_name_snapshot = models.CharField(max_length=255, blank=True, default='', verbose_name="Товар (копия)")
    parent_number = models.CharField(max_length=64, blank=True, default='', verbose_name="Номер паллеты")
    packs_count = models.PositiveIntegerField(default=0, verbose_name="Упаковок")
    boxes_count = models.PositiveIntegerField(default=0, verbose_name="Коробов")
    capacity = models.PositiveIntegerField(null=True, blank=True, verbose_name="Вместимость")
    weight_netto_grams = models.FloatField(null=True, blank=True, verbose_name="Вес нетто (г)")
    weight_brutto_grams = models.FloatField(null=True, blank=True, verbose_name="Вес брутто (г)")
    is_closed = models.BooleanField(default=False, verbose_name="Закрыт")
    opened_at = models.DateTimeField(verbose_name="Открыт")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Закрыт в")
    is_deleted = models.BooleanField(default=False, verbose_name="Удалён")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Удалён в")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Короб или паллета"
        verbose_name_plural = "Короба и паллеты"
        ordering = ['-opened_at']
        indexes = [models.Index(fields=['station', 'level', 'opened_at'])]


class StationLog(models.Model):
    LOG_LEVELS = (
        ('INFO', 'Информация'),
        ('WARNING', 'Предупреждение'),
        ('ERROR', 'Ошибка'),
    )
    
    station = models.ForeignKey(LabelsStations, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Станция")
    level = models.CharField(max_length=20, choices=LOG_LEVELS, default='INFO', verbose_name="Уровень")
    message = models.TextField(verbose_name="Сообщение")
    # Station subsystem that reported it: print, printer, scale, sync, license, update,
    # database, app. Empty for reports from older clients.
    component = models.CharField(max_length=32, blank=True, default='', verbose_name="Подсистема")
    timestamp = models.DateTimeField(verbose_name="Время события")
    # Client-generated idempotency key so an online retry (or USB-then-online) of the same
    # log row is skipped instead of duplicated. Nullable for legacy/USB reports without it.
    event_uid = models.CharField(max_length=64, null=True, blank=True, unique=True, verbose_name="UID события")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время получения сервером")

    def __str__(self):
        return f"[{self.level}] {self.station} - {self.timestamp}"

    class Meta:
        verbose_name = "Лог станции"
        verbose_name_plural = "Логи станций"
        ordering = ['-timestamp']


class ProductionSettings(models.Model):
    """How much the server shows about people (one row). Output per operator is employee
    performance data: in the EU it needs a legal basis (GDPR art. 6/88) and in Germany the
    works council's consent (BetrVG § 87 (1) 6), so it stays off until an admin enables it."""
    operator_output = models.BooleanField(default=False, verbose_name="Выработка по операторам")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки производственных данных"

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]
