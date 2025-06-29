from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import LabelsStations

@shared_task
def update_client_status():
    print('Start celery task "update_client_status"')
    timeout = timezone.now() - timedelta(minutes=2)  # Тайм-аут 2 минуты
    clients = LabelsStations.objects.all()
    for client in clients:
        if client.changed_at < timeout:
            if client.is_online is True:
                client.is_online = False
                client.save()
        else:
            if client.is_online is False:
                client.is_online = True
                client.save()

