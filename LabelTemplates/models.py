from django.db import models


class LabelTemplates(models.Model):
    name = models.CharField(max_length=100)
    scheme = models.JSONField()

    def __str__(self):
        return self.name