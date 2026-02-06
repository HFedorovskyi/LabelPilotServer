from django.db import models

class Pack(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название упаковки")
    weight = models.FloatField(verbose_name="Вес (г)", default=0)
    created = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    edited = models.DateTimeField(auto_now=True, verbose_name="Дата изменения")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Упаковка"
        verbose_name_plural = "Упаковки"
