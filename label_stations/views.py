import json
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from .models import LabelsStations
import socket
from common.utils import send_notification

class DiscoverStationsView(View):


    def send_broadcast(self):
        UDP_PORT = 5005
        BROADCAST_IP = '255.255.255.255'
        MESSAGE = b'Check online status'

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.sendto(MESSAGE, (BROADCAST_IP, UDP_PORT))

        sock.settimeout(5)
        clients = []

        try:
            while True:
                data, address = sock.recvfrom(1024)
                client_uuid = data.decode().split()[1]
                hostname = data.decode().split()[0]
                clients.append({'uuid': client_uuid, 'address': address, 'hostname': hostname})
                print(f"Received response from {address}: {client_uuid}, {hostname}")
        except socket.timeout:
            print(f"Поиск закончен")
        finally:
            sock.close()

        return clients

    def get(self, request, *args, **kwargs):
        clients = self.send_broadcast()
        return JsonResponse(clients, safe=False)


class LabelStationsListView(ListView):
    model = LabelsStations
    template_name = 'label_stations/label_stations_list.html'
    context_object_name = 'label_stations'

    def get_queryset(self, *args, **kwargs):
        return LabelsStations.objects.all()


class LabelStationsDetailView(DetailView):
    pass


class LabelStationsAdding(View):

    def post(self, request, *args, **kwargs):

        try:
            data = json.loads(request.body)
            hostname = data['hostname']
            uuid = data['uuid']

            if LabelsStations.objects.filter(stations_uuid=uuid).exists():
                return JsonResponse({'status': 'error', 'message': 'Станция с таким UUID уже существует.'})

            station = LabelsStations.objects.create(stations_uuid=uuid, station_name=hostname)
            station.save()
            return JsonResponse({'status': 'success', 'message': 'Станция успешно сохранена.'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})



class LabelStationsDeleteView(View):

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            station_uuid = data['uuid']
            station = LabelsStations.objects.get(stations_uuid=station_uuid)
            station.delete()
            return JsonResponse({'status': 'success', 'message': 'Станция успешно удалена.'})
        except LabelsStations.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Станция не найдена.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})


class LabelStationsEditView(View):


    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            station_uuid = data['uuid']
            new_name = data['name']
            station = LabelsStations.objects.get(stations_uuid=station_uuid)
            station.station_name = new_name
            station.save()
            return JsonResponse({'status': 'success', 'message': 'Имя станции успешно обновлено.'})
        except LabelsStations.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Станция не найдена.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})



@method_decorator(csrf_exempt, name='dispatch')  # Отключаем проверку CSRF для этого представления
class UpdateStationStatusView(View):
    model = LabelsStations


    def post(self, request, *args, **kwargs):


        try:
            # Читаем и парсим JSON-данные из тела запроса
            data = json.loads(request.body)
            station_uuid = data.get('uuid')
            ip_address = data.get('ip')
            name_station = data.get('name')
            # Логика обновления статуса станции в базе данных
            try:
                try:
                    station = LabelsStations.objects.get(station_uuid=station_uuid)
                except LabelsStations.DoesNotExist:
                    station = LabelsStations(station_uuid=station_uuid, station_name=name_station, station_ip=ip_address)
                if station.is_online is True:
                    return JsonResponse({'status': 'success'})
                else:
                    station.station_ip = ip_address
                    station.is_online = True
                    send_notification(f'Станция {name_station} онлайн!')
                    station.save()
                    return JsonResponse({'status': 'success'})
            except LabelsStations.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Станция не найдена'}, status=404)

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Ошибка разбора JSON'}, status=400)
