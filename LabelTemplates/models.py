from django.db import models


class LabelTemplates(models.Model):
    name = models.CharField(max_length=100)
    scheme = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return self.name