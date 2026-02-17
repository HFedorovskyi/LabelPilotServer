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
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время получения сервером")

    def __str__(self):
        return f"{self.unique_id} ({self.product_name_snapshot})"

    class Meta:
        verbose_name = "Напечатанная этикетка"
        verbose_name_plural = "Напечатанные этикетки"
        ordering = ['-printed_at']


class StationLog(models.Model):
    LOG_LEVELS = (
        ('INFO', 'Информация'),
        ('WARNING', 'Предупреждение'),
        ('ERROR', 'Ошибка'),
    )
    
    station = models.ForeignKey(LabelsStations, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Станция")
    level = models.CharField(max_length=20, choices=LOG_LEVELS, default='INFO', verbose_name="Уровень")
    message = models.TextField(verbose_name="Сообщение")
    timestamp = models.DateTimeField(verbose_name="Время события")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время получения сервером")

    def __str__(self):
        return f"[{self.level}] {self.station} - {self.timestamp}"

    class Meta:
        verbose_name = "Лог станции"
        verbose_name_plural = "Логи станций"
        ordering = ['-timestamp']
