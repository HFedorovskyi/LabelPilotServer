import json
import socket
import requests
from django.views.generic import View
from .servises import BaserowApiExchange
from django.shortcuts import render
from django.http import JsonResponse
from common.tasks import send_barcodes_to_stations
from label_stations.models import LabelsStations
from LabelTemplates.servises import BaserowApiExchangeLabelTemplate
from Packs.servises import BaserowExchangePacks
from common.utils import send_notification


class NomenclatureListView(View):
    baserow_api_exchange = BaserowApiExchange()
    template_name = 'Nomenclature/nomenclature.html'
    labels_api = BaserowApiExchangeLabelTemplate()
    packs_api = BaserowExchangePacks()
    def get(self, request, *args, **kwargs):

        response_data_fields = self.baserow_api_exchange.get_fields()
        response_data_rows = self.baserow_api_exchange.get_rows()

        nomenclatures_rows = response_data_rows.get('results', [])
        filtred_nomenclature_fields = self.get_filtred_nomenclature_fields(response_data_fields)
        filtred_nomenclature_rows = self.get_filtred_nomenclature_rows(response_data_fields)

        labels = self.labels_api.get_rows_label()
        packs = self.packs_api.get_rows_packs()
        stations = LabelsStations.objects.all()
        return render(request, template_name=self.template_name, context={'products': nomenclatures_rows,
                                                                          'fields':response_data_fields,
                                                                          'filtred_rows':filtred_nomenclature_rows,
                                                                          'filtred_nomenclature_fields':filtred_nomenclature_fields,
                                                                          'stations':stations,
                                                                          'labels': labels.get('results', []),
                                                                          'packs':packs.get('results', []),

                                                                          })


    def get_filtred_nomenclature_rows(self, list_of_nomenclatures_rows):
        filtred_fields = ['name', 'article', 'exp_date', 'close_box_counter',
                          'created', 'edited', 'order', 'id', 'portion_container_id', 'box_container_id', 'templates_pack_label', 'templates_box_label']

        result = []
        for item in list_of_nomenclatures_rows:
            if item['name'] not in filtred_fields:
                result.append(item['name'])
        return result


    def get_filtred_nomenclature_fields(self, nomenclatures_fields):

        filtred_fields = ['name', 'article', 'exp_date', 'close_box_counter',
                          'created', 'edited', 'order', 'id', 'portion_container_id', 'box_container_id', 'templates_pack_label', 'templates_box_label']

        result = []
        for item in nomenclatures_fields:
            if item['name'] not in filtred_fields:
                result.append(item)
        return result



    def post(self, request):
        if request.headers.get('X-Action') == 'new_nomenclature':
            return self.post_new_nomenclature(request)

        elif request.headers.get('X-Action') == 'new_row_nomenclature':
            return self.post_new_row_nomenclature(request)

        elif request.headers.get('X-Action') == 'sendNomenclatureToStations':
            return self.send_nomenclatures_to_stations(request)

        elif request.headers.get('X-Action') == 'edit_nomenclature':
            return self.patch_edit_nomenclature(request)


    def post_new_nomenclature(self, request):
        byte_data = request.body.decode('utf-8')
        data = json.loads(byte_data)
        add_baserow_row = self.baserow_api_exchange.new_row(data)

        if isinstance(add_baserow_row, dict):
            return JsonResponse({'success': True, 'nomenclature': add_baserow_row})
        return JsonResponse({'success': False, 'error': add_baserow_row})


    def post_new_row_nomenclature(self, request):
        field_name = request.POST.get('newRowName', None)
        add_baserow_field = self.baserow_api_exchange.new_field(field_name)
        if isinstance(add_baserow_field, dict):
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': add_baserow_field})

    def patch_edit_nomenclature(self, request):
        byte_data = request.body.decode('utf-8')
        data = json.loads(byte_data)
        nomenclature_row_response = self.baserow_api_exchange.update_field(data)
        if isinstance(nomenclature_row_response, dict):
            print(nomenclature_row_response)
            return JsonResponse({'success': True, 'nomenclature': nomenclature_row_response})
        return JsonResponse({'success': False, 'error': nomenclature_row_response})

    def delete(self, request):
        if request.headers.get('X-Action') == 'delete_field_nomenclature':
            return self.delete_field_nomenclature(request)
        elif request.headers.get('X-Action') == 'delete_row_nomenclature':
            return self.delete_row_nomenclature(request)


    def delete_row_nomenclature(self, request):
        id_nomenclature = json.loads(request.body.decode('utf-8'))
        if id_nomenclature is None:
            return JsonResponse({'error': 'Поле не существует!'}, status=400)


        response = self.baserow_api_exchange.delete_row_nomnenclature(id_nomenclature)

        if isinstance(response, dict):
            return JsonResponse({'success': False, 'error': response.get('error')}, status=500)


        return JsonResponse({'success': True})



    def delete_field_nomenclature(self, request):

        body_unicode = request.body.decode('utf-8')
        body_data = json.loads(body_unicode)
        field_id = body_data.get('field_id', None)

        if field_id is None:
            return JsonResponse({'error': 'Поле не существует!'}, status=400)


        response = self.baserow_api_exchange.delete_field_nomenclature_api(field_id)



        if response.get('error', False):
            return JsonResponse({'success': False, 'error': response.get('error')}, status=500)

        send_notification('Реквизит успешно удалён!')
        return JsonResponse({'success': True})


    def send_nomenclatures_to_stations(self, request):
        nomenclatures_field = self.baserow_api_exchange.get_fields()
        nomenclatures_data = self.baserow_api_exchange.get_rows()
        nomenclatures = nomenclatures_data.get('results', None)

        json_string = request.body.decode('utf-8')
        data_dict = json.loads(json_string)
        dispatched_stations = data_dict.get('stations', None)
        if nomenclatures is not None:
            try:
                for item in dispatched_stations:

                    station_ip = LabelsStations.objects.get(station_uuid=item).station_ip
                    if station_ip:
                        url = f'http://{station_ip}:5005/'
                        response = requests.post(url, json={'nomenclatures': nomenclatures,
                                                            'nomenclatures_field': nomenclatures_field})
                        if response.status_code == 200:
                            print("Данные успешно отправлены на станцию.")
                        else:
                            print("Ошибка при отправке данных на станцию.")
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'error': str(e)})