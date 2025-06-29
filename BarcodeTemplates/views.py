from django.db.models.expressions import result
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import ListView
from .servises import BaserowExchangeBarcode
from Nomenclature.servises import BaserowApiExchange
from label_stations.models import LabelsStations
import json
import requests


class BarcodeTemplateListView(ListView):
    baserow_api_exchange_nomenclatures = BaserowApiExchange()
    template_name = 'BarcodeTemplates/barcode_templates_list.html'
    baserow_api_exchange_barcodes = BaserowExchangeBarcode()


    def get(self, request, *args, **kwargs):
        try:
            nomenclatures_count = len(self.baserow_api_exchange_nomenclatures.get_rows()['results'])
            barcodes = self.baserow_api_exchange_barcodes.get_rows_barcode()
            stations = LabelsStations.objects.all()
            return render(request, self.template_name, {'nomenclatures_count': nomenclatures_count,
                                                        'barcodes': barcodes['results'],
                                                        'stations':stations,})
        except Exception as e:
            return JsonResponse({'error': str(e)})


    def post(self, request, *args, **kwargs):
        if request.headers.get('X-Action') == 'saveStructure':
            return self.save_structure(request, *args, **kwargs)
        elif request.headers.get('X-Action') == 'sendToStations':
            return self.send_barcodes_to_stations(request)
        elif request.headers.get('X-Action') == 'deleteBarcode':
            return


    def send_barcodes_to_stations(self, request):
        barcodes_data = self.baserow_api_exchange_barcodes.get_rows_barcode()
        barcodes = barcodes_data.get('results', None)

        json_string = request.body.decode('utf-8')
        data_dict = json.loads(json_string)
        dispatched_stations = data_dict.get('stations', None)
        if barcodes is not None:
            try:
                for item in dispatched_stations:

                    station_ip = LabelsStations.objects.get(station_uuid=item).station_ip
                    if station_ip:
                        url = f'http://{station_ip}:5005/'
                        response = requests.post(url, json={'barcodes': barcodes})
                        if response.status_code == 200:
                            print("Данные успешно отправлены на станцию.")
                        else:
                            print("Ошибка при отправке данных на станцию.")
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'error': str(e)})
        else:
            return JsonResponse({'success': False, 'messages':'Нету сохранённых шаблонов штрихкодов!'})


    def save_structure(self, request, *args, **kwargs):
        data = json.loads(request.body.decode('utf-8'))
        result = self.baserow_api_exchange_barcodes.new_row_barcode(data['barcode_structure']['barcode_name'], data)
        if isinstance(result, dict):
            return JsonResponse({'success': True})
        return JsonResponse({'error': str(result)})

    def delete_barcode(self, request, *args, **kwargs):
        barcode_id = request.body.decode('utf-8')
