import json

from django.shortcuts import render
from django.views.generic import ListView
from .servises import BaserowExchangePacks
from django.http import JsonResponse
from label_stations.models import LabelsStations



class PacksTemplateListView(ListView):
    baserow_api_exchange_packs = BaserowExchangePacks()
    template_name = 'Packs/packs.html'

    def get(self, request, *args, **kwargs):
        try:
            stations = LabelsStations.objects.all()
            packs = self.baserow_api_exchange_packs.get_rows_packs()['results']
            return render(request, self.template_name, {'packs': packs,
                                                               'stations': stations,
                                                        })
        except Exception as e:
            return JsonResponse({'error': str(e)})


    def post(self, request, *args, **kwargs):
        if request.headers.get('X-Action') == 'savePack':
            return self.post_save_pack(request, *args, **kwargs)
        elif request.headers.get('X-Action') == 'sendToStations':
            return self.send_barcodes_to_stations(request)


    def post_save_pack(self, request, *args, **kwargs):
        data = json.loads(request.body.decode('utf-8'))
        response = self.baserow_api_exchange_packs.save_row_pack(data['pack'])
        print(response)
        if isinstance(response, dict):
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': response})


    def delete(self, request, *args, **kwargs):
        if request.headers.get('X-Action') == 'deletePack':
            return self.delete_pack(request, *args, **kwargs)


    def delete_pack(self, request, *args, **kwargs):
        data = json.loads(request.body.decode('utf-8'))
        print(data)
        response = self.baserow_api_exchange_packs.delete_row_barcode(data['id'])
        if isinstance(response, dict):
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': response})
