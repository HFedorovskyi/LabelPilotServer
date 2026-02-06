from django.db import models
from Packs.models import Pack
from LabelTemplates.models import LabelTemplates

class Nomenclature(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название номенклатуры")
    article = models.CharField(max_length=100, verbose_name="Артикул", unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, verbose_name="URL")
    
    # Характеристики
    exp_date = models.IntegerField(verbose_name="Срок годности (суток)")
    close_box_counter = models.IntegerField(verbose_name="Количество вложений в коробе")
    
    # Связи
    portion_container = models.ForeignKey(
        Pack, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='nomenclatures_portion',
        verbose_name="Тип упаковки (вложение)"
    )
    box_container = models.ForeignKey(
        Pack, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='nomenclatures_box',
        verbose_name="Тип упаковки (короб)"
    )
    templates_pack_label = models.ForeignKey(
        LabelTemplates, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='nomenclatures_pack_label',
        verbose_name="Шаблон единичной этикетки"
    )
    templates_box_label = models.ForeignKey(
        LabelTemplates, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='nomenclatures_box_label',
        verbose_name="Шаблон этикетки короб"
    )
    
    # Динамические поля
    extra_data = models.JSONField(default=dict, blank=True, verbose_name="Дополнительные реквизиты")
    
    created = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    edited = models.DateTimeField(auto_now=True, verbose_name="Дата изменения")
    order = models.IntegerField(default=0, verbose_name="Порядок сортировки")

    def __str__(self):
        return f"{self.article} - {self.name}"

    class Meta:
        verbose_name = "Номенклатура"
        verbose_name_plural = "Номенклатуры"

class ProductPackLink(models.Model):
    product = models.ForeignKey(Nomenclature, on_delete=models.CASCADE, related_name='pack_links', verbose_name="Номенклатура")
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name='product_links', verbose_name="Упаковка")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return f"{self.product} - {self.pack}"

    class Meta:
        verbose_name = "Связь товар-упаковка"
        verbose_name_plural = "Связи товар-упаковка"
        unique_together = ('product', 'pack')

class GlobalProductAttribute(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Название атрибута")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Глобальный атрибут товара"
        verbose_name_plural = "Глобальные атрибуты товаров"
