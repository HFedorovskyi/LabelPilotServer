from celery import shared_task
from label_stations.models import LabelsStations
import requests

@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def send_barcodes_to_stations(self, station_uuid, json, app_name):
    try:
        station = LabelsStations.objects.get(station_uuid=station_uuid)
        station_ip = station.station_ip
        if station_ip:
            url = f'http://{station_ip}:5005/'
            response = requests.post(url, json={'labels': labels}, timeout=10)
            if response.status_code == 200:
                print(f"Данные успешно отправлены на станцию {station_uuid} ({station_ip}) для {app_name}.")
                return {'status': 'success'}
            else:
                print(f"Ошибка при отправке данных на станцию {station_uuid} ({station_ip}) для {app_name}.")
                raise self.retry(exc=Exception(f"HTTP {response.status_code}"))
        else:
            print(f"Не удалось найти IP для станции {station_uuid} в {app_name}.")
            return {'status': 'failed', 'reason': 'No station IP found'}
    except LabelsStations.DoesNotExist:
        print(f"Станция с UUID {station_uuid} не существует в {app_name}.")
        return {'status': 'failed', 'reason': 'Station does not exist'}
    except requests.exceptions.RequestException as exc:
        print(f"Исключение при отправке данных на станцию {station_uuid} для {app_name}: {exc}")
        raise self.retry(exc=exc)
    except Exception as exc:
        print(f"Неизвестная ошибка при отправке данных на станцию {station_uuid} для {app_name}: {exc}")
        raise self.retry(exc=exc)