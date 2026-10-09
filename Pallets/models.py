from django.db import models


class Pallet(models.Model):
    """Физическая паллета: шапка листа + состав позиций (PalletItem)."""
    pallet_number = models.CharField(max_length=100, verbose_name="Номер паллеты")
    shipping_date = models.DateField(null=True, blank=True, verbose_name="Дата отгрузки")
    production_date = models.DateField(null=True, blank=True, verbose_name="Дата производства")
    note = models.CharField(max_length=255, blank=True, default="", verbose_name="Примечание")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    edited = models.DateTimeField(auto_now=True, verbose_name="Дата изменения")

    def __str__(self):
        return f"Паллета {self.pallet_number}"

    class Meta:
        verbose_name = "Паллета"
        verbose_name_plural = "Паллеты"
        ordering = ['-created']


class PalletItem(models.Model):
    """Одна позиция (SKU/партия) на паллете."""
    pallet = models.ForeignKey(
        Pallet,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Паллета",
    )
    # Строковый FK, чтобы не плодить циклический импорт (Nomenclature импортирует Packs).
    nomenclature = models.ForeignKey(
        'Nomenclature.Nomenclature',
        on_delete=models.CASCADE,
        related_name='pallet_items',
        verbose_name="Номенклатура",
    )
    quantity = models.FloatField(default=0, verbose_name="Количество")
    batch_number = models.CharField(max_length=100, blank=True, default="", verbose_name="Номер партии")
    weight_netto = models.FloatField(default=0, verbose_name="Вес нетто (кг)")
    weight_brutto = models.FloatField(default=0, verbose_name="Вес брутто (кг)")
    order = models.IntegerField(default=0, verbose_name="Порядок")

    def __str__(self):
        return f"{self.nomenclature} × {self.quantity}"

    class Meta:
        verbose_name = "Позиция паллеты"
        verbose_name_plural = "Позиции паллеты"
        ordering = ['order', 'id']
