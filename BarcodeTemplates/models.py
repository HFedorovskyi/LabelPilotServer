from django.db import models

class BarcodeTemplate(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название шаблона", unique=True)
    structure = models.JSONField(verbose_name="Структура штрихкода")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    edited = models.DateTimeField(auto_now=True, verbose_name="Дата изменения")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Шаблон штрихкода"
        verbose_name_plural = "Шаблоны штрихкодов"
