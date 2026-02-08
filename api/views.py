from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from api.serializers import (
    NomenclatureSerializer, 
    PackSerializer, 
    LabelTemplatesSerializer, 
    BarcodeTemplateSerializer, 
    LabelsStationsSerializer,
    ProductPackLinkSerializer,
    GlobalProductAttributeSerializer
)

from Nomenclature.models import Nomenclature, ProductPackLink, GlobalProductAttribute

from Packs.models import Pack
from LabelTemplates.models import LabelTemplates
from BarcodeTemplates.models import BarcodeTemplate
from label_stations.models import LabelsStations
import socket
import treepoem
import io
import base64
import json
import requests

class ProductPackLinkViewSet(viewsets.ModelViewSet):
    queryset = ProductPackLink.objects.all().order_by('-created')
    serializer_class = ProductPackLinkSerializer

class GlobalProductAttributeViewSet(viewsets.ModelViewSet):
    queryset = GlobalProductAttribute.objects.all().order_by('-created')
    serializer_class = GlobalProductAttributeSerializer


class NomenclatureViewSet(viewsets.ModelViewSet):
    queryset = Nomenclature.objects.all().order_by('-created')
    serializer_class = NomenclatureSerializer

    @action(detail=False, methods=['post'])
    def send_to_stations(self, request):
        stations_uuids = request.data.get('stations', [])
        if not stations_uuids:
             return Response({'error': 'No stations provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        nomenclatures = self.get_queryset()
        data_to_send = NomenclatureSerializer(nomenclatures, many=True).data
        
        results = {}
        for uuid in stations_uuids:
            try:
                station = LabelsStations.objects.get(station_uuid=uuid)
                if station.station_ip:
                    try:
                        url = f'http://{station.station_ip}:5005/'
                        # Mimic legacy structure slightly to ensure compatibility if needed, 
                        # or just send 'nomenclatures' as the key.
                        payload = {
                            'nomenclatures': data_to_send,
                            # Sending empty fields def since we migrated away from Baserow dynamic fields
                            'nomenclatures_field': [] 
                        }
                        requests.post(url, json=payload, timeout=2)
                        results[uuid] = 'Sent'
                    except requests.RequestException as e:
                        results[uuid] = f'Failed: {str(e)}'
                else:
                    results[uuid] = 'No IP'
            except LabelsStations.DoesNotExist:
                results[uuid] = 'Not Found'
                
        return Response({'results': results})

class PacksViewSet(viewsets.ModelViewSet):
    queryset = Pack.objects.all().order_by('-created')
    serializer_class = PackSerializer

class LabelTemplatesViewSet(viewsets.ModelViewSet):
    queryset = LabelTemplates.objects.all()
    serializer_class = LabelTemplatesSerializer

class BarcodeTemplatesViewSet(viewsets.ModelViewSet):
    queryset = BarcodeTemplate.objects.all()
    serializer_class = BarcodeTemplateSerializer

    @action(detail=False, methods=['post'])
    def generate(self, request):
        from api.utils import BarcodeGenerator
        structure = request.data.get('barcode_structure')
        if not structure:
            # Fallback for checking how it was sent in original
            structure = request.data
            
        try:
            generator = BarcodeGenerator()
            image_base64 = generator.generate_image_base64(structure)
            return Response({'success': True, 'png': image_base64})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

from rest_framework.views import APIView

class FullSyncView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        barcodes = BarcodeTemplateSerializer(BarcodeTemplate.objects.all(), many=True).data
        labels = LabelTemplatesSerializer(LabelTemplates.objects.all(), many=True).data
        containers = PackSerializer(Pack.objects.all(), many=True).data
        nomenclature = NomenclatureSerializer(Nomenclature.objects.all().order_by('order'), many=True).data

        payload = {
            'barcodes': barcodes,
            'labels': labels,
            'containers': containers,
            'nomenclature': nomenclature,
            'packs': [] # Client expects packs key but empty is fine if we don't sync transaction data
        }
        return Response(payload)

class StationsViewSet(viewsets.ModelViewSet):
    queryset = LabelsStations.objects.all()
    serializer_class = LabelsStationsSerializer
    lookup_field = 'station_uuid'

    @action(detail=True, methods=['post'])
    def sync_data(self, request, station_uuid=None):
        """
        Pushes full data set to the station.
        """
        station = self.get_object()
        
        if not station.station_ip:
            return Response({'error': 'Station has no IP address'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Gather all data
        barcodes = BarcodeTemplateSerializer(BarcodeTemplate.objects.all(), many=True).data
        labels = LabelTemplatesSerializer(LabelTemplates.objects.all(), many=True).data
        containers = PackSerializer(Pack.objects.all(), many=True).data
        nomenclature = NomenclatureSerializer(Nomenclature.objects.all().order_by('order'), many=True).data

        payload = {
            'barcodes': barcodes,
            'labels': labels,
            'containers': containers,
            'nomenclature': nomenclature,
            'packs': [] 
        }

        # Use discovered port, default to 5556 (Client Sync Server Port)
        # Note: Discovery service finds station and records port. 
        # If client broadcasts port 5556, station.station_port should be 5556.
        # But `run_discovery.py` default was 5000.
        # I updated `discovery.ts` to broadcast 5556.
        # So newly discovered stations will have 5556.
        # Old stations might have 5000.
        target_port = station.station_port or 5556
        url = f'http://{station.station_ip}:{target_port}/api/full_sync'

        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            return Response({'status': 'success', 'message': f'Data synced to {station.station_name}'})
        except requests.RequestException as e:
            return Response({'error': f'Failed to connect to station: {str(e)}'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(detail=False, methods=['get'])
    def full_dump(self, request):
        """
        Endpoint for stations to pull data if they prefer pulling.
        """
        data = {
            'barcode_templates': BarcodeTemplateSerializer(BarcodeTemplate.objects.all(), many=True).data,
            'label_templates': LabelTemplatesSerializer(LabelTemplates.objects.all(), many=True).data,
            'packs': PackSerializer(Pack.objects.all(), many=True).data,
            'global_attributes': GlobalProductAttributeSerializer(GlobalProductAttribute.objects.all(), many=True).data,
            'nomenclatures': NomenclatureSerializer(Nomenclature.objects.all().order_by('order'), many=True).data,
            'product_pack_links': ProductPackLinkSerializer(ProductPackLink.objects.all(), many=True).data
        }
        return Response(data)
