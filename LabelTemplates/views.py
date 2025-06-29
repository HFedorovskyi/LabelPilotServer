import json
import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import ListView, View
from BarcodeTemplates.servises import BaserowExchangeBarcode
from .models import LabelTemplates
from Nomenclature.servises import BaserowApiExchange
from .servises import BaserowApiExchangeLabelTemplate
from label_stations.models import LabelsStations
from django.http import Http404
from BarcodeTemplates.servises import BarcodeGenerator

app_name = 'labelTemplates'

class LabelTemplatesView(ListView):
    model = LabelTemplates
    template_name = 'LabelTemplates/label_templates_list.html'
    context_name = 'label_templates'
    baserow_api_exchange_labeltemplates = BaserowApiExchangeLabelTemplate()



    def get(self, request, *args, **kwargs):
        stations = LabelsStations.objects.all()
        labels_data = self.baserow_api_exchange_labeltemplates.get_rows_label()
        labels = labels_data.get("results", None)
        return render(request, self.template_name, {'labels': labels,
                                                    'stations': stations})

    def post(self, request, *args, **kwargs):
        if request.headers.get('X-Action') == 'sendToStations':
            return self.send_barcodes_to_stations(request)

    def send_barcodes_to_stations(self, request):
        labels = self.baserow_api_exchange_labeltemplates.get_rows_label().get('results', None)
        json_string = request.body.decode('utf-8')
        data_dict = json.loads(json_string)
        print(labels)
        dispatched_stations = data_dict.get('stations', None)
        if labels is not None:
            try:
                for item in dispatched_stations:
                    station_ip = LabelsStations.objects.get(station_uuid=item).station_ip
                    if station_ip:
                        url = f'http://{station_ip}:5005/'
                        response = requests.post(url, json={'labels': labels})
                        if response.status_code == 200:
                            print("Данные успешно отправлены на станцию.")
                        else:
                            print("Ошибка при отправке данных на станцию.")
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'error': str(e)})
        else:
            return JsonResponse({'success': False, 'messages': 'Нету сохранённых шаблонов штрихкодов!'})

    def delete(self, request):
        if request.headers.get('X-Action') == 'deleteLabel':
            return self.delete_label(request)

    def delete_label(self, request):
        body_unicode = request.body.decode('utf-8')
        body_data = json.loads(body_unicode)
        label_id = body_data.get('field_id', None)

        if label_id is None:
            return JsonResponse({'error': 'Поле не существует!'}, status=400)

        response = self.baserow_api_exchange_labeltemplates.del_row_label(label_id)

        if response in [400, 404]:
            return JsonResponse({'success': False, 'error': response.get('error')}, status=500)

        return JsonResponse({'success': True})


class LabelTemplatesCreateView(View):
    baserow_exchange = BaserowApiExchange()
    template_name = 'LabelTemplates/create_label_templates.html'
    baserow_api_exchange_barcodes = BaserowExchangeBarcode()
    baserow_api_exchange_labeltemplates = BaserowApiExchangeLabelTemplate()
    barcode_generator = BarcodeGenerator()

    def get(self, request, *args, **kwargs):
        return self.get_nomenclatures_attrs(request)

    def get_nomenclatures_attrs(self, request):
        nomenclatures_rows = self.baserow_exchange.get_rows()
        barcodes = self.baserow_api_exchange_barcodes.get_rows_barcode()

        return render(request, self.template_name, context={'nomenclatures': nomenclatures_rows['results'],
                                                            'barcodes': barcodes['results']})


    def post(self, request, *args, **kwargs):
        if request.headers.get('X-Action') == 'saveLabel':
            return self.post_save_label(request, *args, **kwargs)
        elif request.headers.get('X-Action') == 'generateBarcode':
            return self.barcode_generator.generate_barcode(request, *args, **kwargs)


    def post_save_label(self, request, *args, **kwargs):
        data_not_cleaned = request.body.decode('utf-8')
        data = json.loads(data_not_cleaned)
        try:
            self.baserow_api_exchange_labeltemplates.new_row_label(data)
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})



class LabelTemplatesUpdateView(View):


    baserow_exchange = BaserowApiExchange()
    template_name = 'LabelTemplates/update_label_templates.html'
    baserow_api_exchange_barcodes = BaserowExchangeBarcode()
    baserow_api_exchange_label_templates = BaserowApiExchangeLabelTemplate()
    barcode_generator = BarcodeGenerator()

    def get(self, request, *args, **kwargs):
        return self.get_nomenclatures_attrs(request, *args, **kwargs)

    def get_nomenclatures_attrs(self, request, *args, **kwargs):
        label_id = kwargs.get('label_id')
        try:
            label_data = self.baserow_api_exchange_label_templates.get_row_label(label_id)

            nomenclatures_rows = self.baserow_exchange.get_rows()

            barcodes = self.baserow_api_exchange_barcodes.get_rows_barcode()



            return render(request, self.template_name, context={'nomenclatures': nomenclatures_rows['results'],
                                                                'barcodes': barcodes['results'],
                                                                'label_data': label_data})
        except Exception as e:
            raise Http404(e)


    def patch(self, request, *args, **kwargs):
        if request.headers.get('X-Action') == 'updateLabel':
            return self.patch_label(request, *args, **kwargs)

    def patch_label(self, request, *args, **kwargs):
        data_not_cleaned = request.body.decode('utf-8')
        data = json.loads(data_not_cleaned)
        try:
            self.baserow_api_exchange_label_templates.update_row(data['id'], data['name'], data['structure'])
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


    def post(self, request, *args, **kwargs):
        if request.headers.get('X-Action') == 'generateBarcode':
            return self.barcode_generator.generate_barcode(request, *args, **kwargs)
