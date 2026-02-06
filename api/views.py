from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
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

class StationsViewSet(viewsets.ModelViewSet):
    queryset = LabelsStations.objects.all()
    serializer_class = LabelsStationsSerializer
    lookup_field = 'station_uuid'

    @action(detail=False, methods=['get'])
    def discover(self, request):
        UDP_PORT = 5005
        BROADCAST_IP = '255.255.255.255'
        MESSAGE = b'Check online status'

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2) # Reduced timeout for API responsiveness
        
        clients = []
        try:
             sock.sendto(MESSAGE, (BROADCAST_IP, UDP_PORT))
             while True:
                try:
                    data, address = sock.recvfrom(1024)
                    client_uuid = data.decode().split()[1]
                    hostname = data.decode().split()[0]
                    clients.append({'uuid': client_uuid, 'address': address[0], 'hostname': hostname})
                except socket.timeout:
                    break
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            sock.close()
            
        return Response(clients)
