from django.db import models
from label_stations.models import LabelsStations
from Nomenclature.models import Nomenclature


class PrintJob(models.Model):
    UNIT_CHOICES = (
        ('kg', 'Килограммы'),
        ('pcs', 'Штуки'),
    )

    STATUS_CHOICES = (
        ('pending', 'Ожидает'),
        ('sent', 'Отправлено'),
        ('completed', 'Выполнено'),
        ('error', 'Ошибка'),
    )

    station = models.ForeignKey(
        LabelsStations,
        on_delete=models.CASCADE,
        related_name='print_jobs',
        verbose_name='Станция'
    )
    nomenclature = models.ForeignKey(
        Nomenclature,
        on_delete=models.CASCADE,
        related_name='print_jobs',
        verbose_name='Номенклатура'
    )
    quantity = models.FloatField(verbose_name='Количество')
    quantity_unit = models.CharField(
        max_length=3,
        choices=UNIT_CHOICES,
        default='pcs',
        verbose_name='Единица измерения'
    )
    batch_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='Номер партии'
    )
    marking_date = models.DateField(
        verbose_name='Дата маркировки'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    def __str__(self):
        return f"Задание #{self.pk} — {self.nomenclature.name} ({self.quantity} {self.get_quantity_unit_display()})"

    class Meta:
        verbose_name = 'Задание на печать'
        verbose_name_plural = 'Задания на печать'
        ordering = ['-created_at']
