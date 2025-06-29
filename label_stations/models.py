from django.db import models


class LabelsStations(models.Model):
    station_name = models.CharField(max_length=100, default='Станция маркировки')
    station_uuid = models.UUIDField(editable=False, unique=True)
    station_ip = models.GenericIPAddressField(null=True, blank=True)
    is_online = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return self.station_name
