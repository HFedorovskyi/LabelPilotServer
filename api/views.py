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
from common.utils import get_local_ip

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


class VersionView(APIView):
    """
    Public endpoint returning server and client version info.
    Used by the admin panel and the Updater Service.
    GET /api/v1/version/
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings
        return Response({
            'server_version': settings.VERSION,
            'min_client_version': settings.MIN_CLIENT_VERSION,
            'latest_client_version': settings.LATEST_CLIENT_VERSION,
        })

class StationsViewSet(viewsets.ModelViewSet):
    queryset = LabelsStations.objects.all()
    serializer_class = LabelsStationsSerializer
    lookup_field = 'station_uuid'


    def _gather_sync_data(self, station, sync_type='UPDATE'):
        """
        Helper method to gather all data for a station sync.
        Returns a unified dictionary structure.
        """
        import datetime
        from common.utils import get_local_ip
        
        # Data objects
        barcodes = BarcodeTemplateSerializer(BarcodeTemplate.objects.all(), many=True).data
        labels = LabelTemplatesSerializer(LabelTemplates.objects.all(), many=True).data
        containers = PackSerializer(Pack.objects.all(), many=True).data
        nomenclature = NomenclatureSerializer(Nomenclature.objects.all().order_by('order'), many=True).data
        global_attributes = GlobalProductAttributeSerializer(GlobalProductAttribute.objects.all(), many=True).data
        product_pack_links = ProductPackLinkSerializer(ProductPackLink.objects.all(), many=True).data

        # Station identity info
        # We try to get the server IP dynamically for the identity
        try:
            local_ip = get_local_ip()
            server_url = f"http://{local_ip}:8000"
        except:
            server_url = "http://localhost:8000"

        station_info = {
            "uuid": str(station.station_uuid),
            "number": station.station_number,
            "name": station.station_name,
            "server_url": server_url
        }

        data = {
            "station": station_info,
            "payload": {
                "barcodes": barcodes,
                "labels": labels,
                "containers": containers,
                "nomenclature": nomenclature,
                "global_attributes": global_attributes,
                "product_pack_links": product_pack_links,
                "packs": [] # Placeholder for transactional data compatibility
            },
            "meta": {
                "type": sync_type,
                "format_version": "1.0",
                "server_version": settings.VERSION,
                "min_client_version": settings.MIN_CLIENT_VERSION,
                "generated_at": datetime.datetime.now().isoformat(),
            }
        }
        return data

    @action(detail=True, methods=['post'])
    def sync_data(self, request, station_uuid=None):
        """
        Pushes full data set to the station (Online).
        """
        station = self.get_object()
        
        if not station.station_ip:
            return Response({'error': 'Station has no IP address'}, status=status.HTTP_400_BAD_REQUEST)

        payload = self._gather_sync_data(station, sync_type='ONLINE_SYNC')

        # Use discovered port, default to 5556 (Client Sync Server Port)
        target_port = station.station_port or 5556
        url = f'http://{station.station_ip}:{target_port}/api/full_sync'

        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            return Response({'status': 'success', 'message': f'Data synced to {station.station_name}'})
        except requests.RequestException as e:
            error_msg = f'Failed to connect to station: {str(e)}'
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json().get('error') or e.response.text
                    error_msg += f' - Details: {error_detail}'
                except Exception:
                    if e.response.text:
                        error_msg += f' - Details: {e.response.text[:200]}'
            return Response({'error': error_msg}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=['get'])
    def download_update(self, request, station_uuid=None):
        """
        Generates an encrypted .lps file for offline update.
        """
        from common.crypto_utils import encrypt_data
        from django.http import HttpResponse
        import datetime

        station = self.get_object()
        data = self._gather_sync_data(station, sync_type='OFFLINE_UPDATE')

        encrypted_data = encrypt_data(data)
        
        filename = f"update_{station.station_number or 'XX'}_{datetime.datetime.now().strftime('%Y%m%d')}.lps"
        response = HttpResponse(encrypted_data, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=['get'])
    def download_identity(self, request, station_uuid=None):
        """
        Generates an encrypted .lpi file for offline station setup.
        Now uses the unified structure and includes full data.
        """
        from common.crypto_utils import encrypt_data
        from django.http import HttpResponse

        station = self.get_object()
        if station.station_number is None:
             return Response({'error': 'Station has no number assigned'}, status=status.HTTP_400_BAD_REQUEST)

        data = self._gather_sync_data(station, sync_type='OFFLINE_IDENTITY')
        encrypted_identity = encrypt_data(data)
        
        filename = f"identity_{station.station_number:02d}.lpi"
        response = HttpResponse(encrypted_identity, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=['post'])
    def upload_report(self, request):
        """
        Accepts an encrypted .lpr file from a station.
        """
        from common.crypto_utils import decrypt_data
        
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            encrypted_data = file_obj.read()
            data = decrypt_data(encrypted_data)
        except Exception as e:
             return Response({'error': f'Decryption failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
             
        # Process report data
        # For now, just log it and return success
        # In future: Save to TransactionLog model
        
        station_uuid = data.get('station_uuid')
        # report_type = data.get('type')
        
        from ProductionLogs.models import PrintedLabel, StationLog
        from django.utils.dateparse import parse_datetime
        
        station = LabelsStations.objects.filter(station_uuid=station_uuid).first()
        
        # 1. Process Printed Labels
        labels_data = data.get('printed_labels', [])
        labels_count = 0
        for item in labels_data:
            unique_id = item.get('unique_id')
            # Skip if already exists (idempotency)
            if not unique_id or PrintedLabel.objects.filter(unique_id=unique_id).exists():
                continue
            
            # Resolve FKs if possible
            prod_id = item.get('product_id')
            pack_id = item.get('pack_id')
            
            prod = Nomenclature.objects.filter(pk=prod_id).first() if prod_id else None
            pack = Pack.objects.filter(pk=pack_id).first() if pack_id else None
            
            try:
                PrintedLabel.objects.create(
                    station=station,
                    station_user_name=item.get('user_name', ''),
                    product=prod,
                    product_name_snapshot=item.get('product_name', '') or (prod.name if prod else ''),
                    pack=pack,
                    pack_name_snapshot=item.get('pack_name', '') or (pack.name if pack else ''),
                    unique_id=unique_id,
                    printed_at=parse_datetime(item.get('printed_at'))
                )
                labels_count += 1
            except Exception as e:
                print(f"Error saving label {unique_id}: {e}")

        # 2. Process Logs
        logs_data = data.get('logs', [])
        logs_count = 0
        for item in logs_data:
            try:
                StationLog.objects.create(
                    station=station,
                    level=item.get('level', 'INFO'),
                    message=item.get('message', ''),
                    timestamp=parse_datetime(item.get('timestamp'))
                )
                logs_count += 1
            except Exception as e:
                print(f"Error saving log: {e}")
        
        # 3. Update Station Status if provided
        if station and 'status' in data:
             # Example: could update last_seen, is_online (though report implies async)
             pass 
        
        print(f"Report processed for {station_uuid}: {labels_count} labels, {logs_count} logs.")
        
        return Response({
            'status': 'success', 
            'message': 'Report processed successfully',
            'details': {
                'labels_processed': labels_count,
                'logs_processed': logs_count
            }
        })

    @action(detail=False, methods=['get'])
    def server_ip(self, request):
        """
        Returns the server's local IP address.
        """
        ip = get_local_ip()
        return Response({'ip': ip})

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def ping(self, request):
        """
        Heartbeat/Handshake endpoint for stations.
        If ?station_uuid=... is provided, marks that station as online.
        """
        from django.utils import timezone
        from django.conf import settings
        station_uuid = request.query_params.get('station_uuid')
        message = "Pong"
        
        if station_uuid:
            try:
                station = LabelsStations.objects.get(station_uuid=station_uuid)
                station.is_online = True
                station.save(update_fields=['is_online', 'changed_at'])
                message = f"Pong, station {station.station_name} updated"
            except (LabelsStations.DoesNotExist, ValueError, TypeError):
                pass
                
        return Response({
            'status': 'online',
            'server_time': timezone.now(),
            'message': message,
            'server_version': settings.VERSION,
            'min_client_version': settings.MIN_CLIENT_VERSION,
            'latest_client_version': settings.LATEST_CLIENT_VERSION,
        })

    @action(detail=False, methods=['get'])
    def full_dump(self, request):
        """
        Endpoint for stations to pull data if they prefer pulling.
        Now reuses gather_sync_data logic if possible, or keeps separate.
        Let's unify slightly but keep structure compatible.
        """
        station_number = None
        station_uuid = request.query_params.get('station_uuid')
        if station_uuid:
            try:
                station = LabelsStations.objects.get(station_uuid=station_uuid)
                return Response(self._gather_sync_data(station))
            except LabelsStations.DoesNotExist:
                pass
        
        # Fallback if no station identified
        data = {
            'barcodes': BarcodeTemplateSerializer(BarcodeTemplate.objects.all(), many=True).data,
            'labels': LabelTemplatesSerializer(LabelTemplates.objects.all(), many=True).data,
            'containers': PackSerializer(Pack.objects.all(), many=True).data,
            'nomenclature': NomenclatureSerializer(Nomenclature.objects.all().order_by('order'), many=True).data,
            'global_attributes': GlobalProductAttributeSerializer(GlobalProductAttribute.objects.all(), many=True).data,
            'product_pack_links': ProductPackLinkSerializer(ProductPackLink.objects.all(), many=True).data,
            'station_number': None
        }
        return Response(data)
