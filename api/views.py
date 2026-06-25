from rest_framework import viewsets, status
from server_activity.helpers import log_event
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings
from api.serializers import (
    NomenclatureSerializer, 
    PackSerializer, 
    LabelTemplatesSerializer, 
    BarcodeTemplateSerializer, 
    LabelsStationsSerializer,
    ProductPackLinkSerializer,
    GlobalProductAttributeSerializer,
    PrintJobSerializer,
    PalletSerializer,
)

from Nomenclature.models import Nomenclature, ProductPackLink, GlobalProductAttribute
from print_jobs.models import PrintJob

from Packs.models import Pack
from Pallets.models import Pallet
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
from api.i18n import tr


def _require_license_for_export():
    """Pushing REAL station data (nomenclature, identity, sync bundle) requires a valid
    license — ALWAYS, independent of LICENSE_REQUIRED/STRICT. This is THE commercial
    boundary the vendor chose: without a license the product runs in demo (full local UI
    + the built-in client demo with a station/printer/scale work fine), but real data is
    never exported to a station. STRICT mode governs other things (station registration,
    closed-by-default endpoints); it does NOT relax this gate.

    The gate is deliberately stricter than `valid_for_key`: it also requires the license
    be machine-bound-OK and not expired. Decryption of EXISTING data must never brick
    (that's what valid_for_key guards), but exporting NEW data is an active commercial
    action that demands a fully-valid, non-expired, correctly-bound license."""
    from licensing import license_state
    from rest_framework.exceptions import PermissionDenied
    st = license_state()
    if not (st.valid_for_key and st.machine_ok and not st.expired):
        raise PermissionDenied(tr('license.exportDenied'))


class ProductPackLinkViewSet(viewsets.ModelViewSet):
    queryset = ProductPackLink.objects.all().order_by('-created')
    serializer_class = ProductPackLinkSerializer

class GlobalProductAttributeViewSet(viewsets.ModelViewSet):
    queryset = GlobalProductAttribute.objects.all().order_by('-created')
    serializer_class = GlobalProductAttributeSerializer


def _read_import_df(file_obj, sep_param, nrows=None):
    """Read an uploaded .csv/.xls/.xlsx into a pandas DataFrame. CSV is decoded utf-8
    then cp1251 (Russian Excel exports); separator 'auto'/empty -> sniffed by pandas."""
    import pandas as pd
    import io
    name = (file_obj.name or '').lower()
    if name.endswith('.csv'):
        raw = file_obj.read()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = raw.decode('cp1251')
        sep = None if sep_param in (None, '', 'auto') else sep_param
        return pd.read_csv(io.StringIO(text), sep=sep, nrows=nrows, on_bad_lines='skip', engine='python')
    if name.endswith(('.xls', '.xlsx')):
        return pd.read_excel(file_obj, nrows=nrows)
    raise ValueError('Unsupported file format')


def _import_to_int(raw, default=0):
    s = str(raw).strip().replace(',', '.')
    try:
        return int(float(s)) if s else default
    except (ValueError, TypeError):
        return default


def _import_to_float(raw, default=0.0):
    s = str(raw).strip().replace(',', '.')   # Russian Excel uses a comma decimal
    try:
        return float(s) if s else default
    except (ValueError, TypeError):
        return default


class NomenclatureViewSet(viewsets.ModelViewSet):
    queryset = Nomenclature.objects.all().order_by('-created')
    serializer_class = NomenclatureSerializer

    @action(detail=False, methods=['post'])
    def send_to_stations(self, request):
        # Pushing the real nomenclature table to station IPs is a real-data export -> gated.
        _require_license_for_export()
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

    @action(detail=False, methods=['post'])
    def preview_import(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            df = _read_import_df(file_obj, request.data.get('separator'), nrows=10).fillna('')
        except Exception as e:
            return Response({'error': f'Parsing failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'columns': df.columns.tolist(), 'preview': df.to_dict(orient='records')})

    @action(detail=False, methods=['post'])
    def execute_import(self, request):
        file_obj = request.FILES.get('file')
        mapping_str = request.data.get('mapping')
        if not file_obj or not mapping_str:
            return Response({'error': 'File or mapping not provided'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            mapping = json.loads(mapping_str)
        except json.JSONDecodeError:
            return Response({'error': 'Invalid mapping format json'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            df = _read_import_df(file_obj, request.data.get('separator')).fillna('')
        except Exception as e:
            return Response({'error': f'Import failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        cols = {k: mapping.get(k) for k in (
            'article', 'name', 'exp_date', 'close_box_counter',
            'fixed_weight_grams', 'min_weight_grams', 'max_weight_grams')}
        extra_map = mapping.get('extra_data_map') or {}
        static = mapping.get('staticValues') or {}
        static_fk = {}
        for src, dst in (('portionContainerId', 'portion_container_id'),
                         ('boxContainerId', 'box_container_id'),
                         ('packLabelId', 'templates_pack_label_id'),
                         ('boxLabelId', 'templates_box_label_id')):
            if static.get(src):
                static_fk[dst] = static[src]

        def cell(row, key):
            col = cols[key]
            return row.get(col, '') if col else ''

        # 1) Validate EVERY row up front (collect all errors), dedup by article (last wins).
        #    to_dict('records') iterates plain dicts — far faster than DataFrame.iterrows().
        errors, parsed = [], {}
        for i, row in enumerate(df.to_dict('records')):
            article = str(cell(row, 'article')).strip()
            name = str(cell(row, 'name')).strip()
            if not article or not name:
                errors.append(tr('import.rowMissingArticleOrName', row=i + 2))
                continue
            extra = {}
            for attr_name, col in extra_map.items():
                if col:
                    val = row.get(col)
                    if val is not None and str(val).strip() not in ('', 'None'):
                        extra[attr_name] = val
            fwg = _import_to_float(cell(row, 'fixed_weight_grams'))
            parsed[article] = dict(
                name=name,
                exp_date=_import_to_int(cell(row, 'exp_date')),
                close_box_counter=_import_to_int(cell(row, 'close_box_counter')),
                fixed_weight_grams=fwg,
                min_weight_grams=_import_to_float(cell(row, 'min_weight_grams')),
                max_weight_grams=_import_to_float(cell(row, 'max_weight_grams')),
                is_fixed_weight=fwg > 0,   # a product with a fixed weight set IS fixed-weight
                extra_data=extra,
                **static_fk,
            )

        if not parsed:
            return Response({'success': True, 'imported': 0, 'created': 0, 'updated': 0,
                             'errors': errors[:10], 'error_count': len(errors)})

        # 2) Fetch existing in chunks (huge files would blow the SQLite param limit), then a
        #    single bulk create + bulk update in one transaction.
        from django.db import transaction
        from django.db.models import Max
        from django.utils import timezone
        existing, arts = {}, list(parsed.keys())
        for j in range(0, len(arts), 900):
            for n in Nomenclature.objects.filter(article__in=arts[j:j + 900]):
                existing[n.article] = n

        to_create, to_update, upd_fields = [], [], set()
        for article, fields in parsed.items():
            if article in existing:
                obj = existing[article]
                for k, v in fields.items():
                    setattr(obj, k, v)
                    upd_fields.add(k)
                obj.edited = timezone.now()
                upd_fields.add('edited')
                to_update.append(obj)
            else:
                to_create.append(Nomenclature(article=article, **fields))

        if to_create:   # give new rows incrementing sort order after the current max
            next_order = (Nomenclature.objects.aggregate(m=Max('order'))['m'] or 0) + 1
            for idx, obj in enumerate(to_create):
                obj.order = next_order + idx

        try:
            with transaction.atomic():
                if to_create:
                    Nomenclature.objects.bulk_create(to_create, batch_size=500)
                if to_update:
                    Nomenclature.objects.bulk_update(to_update, list(upd_fields), batch_size=500)
        except Exception as e:
            return Response({'error': f'Import failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'imported': len(to_create) + len(to_update),
            'created': len(to_create),
            'updated': len(to_update),
            'errors': errors[:10],
            'error_count': len(errors),
        })

class PacksViewSet(viewsets.ModelViewSet):
    queryset = Pack.objects.all().order_by('-created')
    serializer_class = PackSerializer


class PalletViewSet(viewsets.ModelViewSet):
    queryset = Pallet.objects.all().prefetch_related('items', 'items__nomenclature').order_by('-created')
    serializer_class = PalletSerializer

class LabelTemplatesViewSet(viewsets.ModelViewSet):
    queryset = LabelTemplates.objects.all()
    serializer_class = LabelTemplatesSerializer

class BarcodeTemplatesViewSet(viewsets.ModelViewSet):
    queryset = BarcodeTemplate.objects.all()
    serializer_class = BarcodeTemplateSerializer

    @action(detail=False, methods=['post'])
    def generate(self, request):
        from api.utils import BarcodeGenerator, validate_structure

        from Nomenclature.models import Nomenclature

        structure = request.data.get('barcode_structure')
        product_id = request.data.get('product_id')

        if not structure:
            return Response({'errors': [tr('barcode.noStructure')]}, status=status.HTTP_400_BAD_REQUEST)

        # Validate the structure before rendering. Returns 400 {errors: [...]}.
        validation_errors = validate_structure(structure)
        if validation_errors:
            return Response({'errors': validation_errors}, status=status.HTTP_400_BAD_REQUEST)

        test_product = None
        if product_id:
            try:
                test_product = Nomenclature.objects.get(pk=product_id)
            except Nomenclature.DoesNotExist:
                pass

        try:
            generator = BarcodeGenerator()
            image_base64, data_string, warnings = generator.generate_image_base64(
                structure, product=test_product
            )
            return Response({
                'success': True,
                'png': image_base64,
                'data_string': data_string,
                'warnings': warnings,
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

from rest_framework.views import APIView

class FullSyncView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        _require_license_for_export()
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
        from pathlib import Path

        # Read version dynamically so it reflects updates without container restart
        def _live_version() -> str:
            for candidate in [Path("/version/VERSION"), Path(settings.BASE_DIR).parent / "VERSION"]:
                try:
                    if candidate.exists():
                        return candidate.read_text().strip()
                except Exception:
                    pass
            return settings.VERSION  # fallback to startup-cached value

        return Response({
            'server_version': _live_version(),
            'min_client_version': settings.MIN_CLIENT_VERSION,
            'latest_client_version': settings.LATEST_CLIENT_VERSION,
        })


class LicenseView(APIView):
    """Public license status for the admin UI: edition, customer, expiry, seat usage,
    and this server's machine_id (so the vendor can issue a machine-bound license).
    GET /api/v1/license/"""
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings
        from licensing import license_status, license_state
        data = dict(license_status())
        st = license_state()
        # Surfaced separately so the admin UI can tell "bound to a different machine"
        # apart from "no license" (license_status() reports a wrong-machine license as
        # unlicensed). `strict` reflects the effective fail-closed posture.
        data['strict'] = bool(getattr(settings, 'LICENSE_REQUIRED', False)) and not getattr(settings, 'DEBUG', False)
        data['signature_valid'] = st.signature_valid
        data['machine_ok'] = st.machine_ok
        data['stations_used'] = LabelsStations.objects.count()
        return Response(data)


class StationsViewSet(viewsets.ModelViewSet):
    queryset = LabelsStations.objects.all()
    serializer_class = LabelsStationsSerializer
    lookup_field = 'station_uuid'

    # Station/handshake endpoints stay OPEN (stations have no user session) — gated by
    # license (_require_license_for_export) + the LAN boundary, not user auth. Everything
    # else (station CRUD, send-to-station) inherits closed-by-default IsAuthenticated.
    _PUBLIC_ACTIONS = {"ping", "server_ip", "full_dump", "upload_report",
                       "download_identity", "download_update", "sync_data"}

    def get_permissions(self):
        from rest_framework.permissions import AllowAny
        if getattr(self, "action", None) in self._PUBLIC_ACTIONS:
            return [AllowAny()]
        return super().get_permissions()

    def perform_create(self, serializer):
        # Seat limit applies only to an over-cap or invalid license; no license = unlimited.
        from licensing import seat_available
        from rest_framework.exceptions import ValidationError
        if not seat_available(LabelsStations.objects.count()):
            raise ValidationError({"license": tr('station.seatLimitReached')})
        serializer.save()


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

        # Operators for this station (station-specific + the shared/global pool). pin_hash
        # is included so the client validates PINs locally/offline. License-gated like the
        # rest of the bundle (the export endpoints call _require_license_for_export).
        from label_stations.models import Operator
        from django.db.models import Q
        operators = [{
            "uuid": str(o.uuid), "full_name": o.full_name, "short_code": o.short_code,
            "pin_hash": o.pin_hash, "is_active": o.is_active,
        } for o in Operator.objects.filter(is_active=True).filter(Q(station=station) | Q(station__isnull=True))]

        data = {
            "station": station_info,
            "payload": {
                "operators": operators,
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
        _require_license_for_export()
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
            from django.utils import timezone as tz
            station.last_sync_at = tz.now()
            station.save(update_fields=['last_sync_at', 'changed_at'])
            log_event('station_synced', f'Данные синхронизированы со станцией «{station.station_name}» (онлайн)')
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
        _require_license_for_export()
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
        _require_license_for_export()
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
        """Ingest an encrypted .lpr report from a station — same payload over either
        transport: USB upload OR the station's automatic online push.

        Built to absorb many stations (10-20) reporting on a 5-min cadence: FKs are
        batch-resolved, rows are bulk_create'd with ignore_conflicts, and the whole
        write is one transaction. Fully idempotent — PrintedLabel dedupes on unique_id
        and StationLog on event_uid, so retries / USB-then-online never double-count.
        """
        from common.crypto_utils import decrypt_data
        from ProductionLogs.models import PrintedLabel, StationLog
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone as tz
        from django.db import transaction
        from django.core.exceptions import ValidationError as DjangoValidationError

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = decrypt_data(file_obj.read())
        except Exception as e:
            return Response({'error': f'Decryption failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        station_uuid = data.get('station_uuid')
        # station_uuid is a UUIDField; a malformed/non-UUID value raises ValidationError.
        # Treat it like an unknown station (process unattached) rather than 500 the endpoint.
        try:
            station = LabelsStations.objects.filter(station_uuid=station_uuid).first() if station_uuid else None
        except (ValueError, DjangoValidationError):
            station = None

        labels_data = [it for it in (data.get('printed_labels') or []) if it.get('unique_id')]
        logs_data = data.get('logs') or []

        new_labels, new_logs = [], []

        # --- Printed labels: skip ids already stored, batch-resolve product/pack FKs ---
        if labels_data:
            uids = [it['unique_id'] for it in labels_data]
            seen = set(PrintedLabel.objects.filter(unique_id__in=uids).values_list('unique_id', flat=True))
            prods = Nomenclature.objects.in_bulk({it['product_id'] for it in labels_data if it.get('product_id')})
            packs = Pack.objects.in_bulk({it['pack_id'] for it in labels_data if it.get('pack_id')})
            for it in labels_data:
                uid = it['unique_id']
                if uid in seen:
                    continue
                seen.add(uid)  # also dedupes within this one payload
                prod = prods.get(it.get('product_id'))
                pack = packs.get(it.get('pack_id'))
                new_labels.append(PrintedLabel(
                    station=station,
                    station_user_name=it.get('user_name', ''),
                    product=prod,
                    product_name_snapshot=it.get('product_name', '') or (prod.name if prod else ''),
                    pack=pack,
                    pack_name_snapshot=it.get('pack_name', '') or (pack.name if pack else ''),
                    unique_id=uid,
                    printed_at=parse_datetime(it.get('printed_at') or '') or tz.now(),
                ))

        # --- Logs: skip event_uids already stored (legacy/USB logs without one are kept) ---
        if logs_data:
            euids = [it['event_uid'] for it in logs_data if it.get('event_uid')]
            seen_l = set(StationLog.objects.filter(event_uid__in=euids).values_list('event_uid', flat=True)) if euids else set()
            for it in logs_data:
                euid = it.get('event_uid')
                if euid and euid in seen_l:
                    continue
                if euid:
                    seen_l.add(euid)
                new_logs.append(StationLog(
                    station=station,
                    level=it.get('level', 'INFO'),
                    message=it.get('message', ''),
                    timestamp=parse_datetime(it.get('timestamp') or '') or tz.now(),
                    event_uid=euid or None,
                ))

        with transaction.atomic():
            if new_labels:
                PrintedLabel.objects.bulk_create(new_labels, ignore_conflicts=True)
            if new_logs:
                StationLog.objects.bulk_create(new_logs, ignore_conflicts=True)
            if station:
                station.last_sync_at = tz.now()
                station.save(update_fields=['last_sync_at', 'changed_at'])

        labels_count, logs_count = len(new_labels), len(new_logs)
        station_label = station.station_name if station else station_uuid
        log_event('report_imported', f'Импортирован отчёт со станции «{station_label}»: {labels_count} этикеток, {logs_count} логов')

        return Response({
            'status': 'success',
            'message': 'Report processed successfully',
            'details': {'labels_processed': labels_count, 'logs_processed': logs_count},
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
        # full_dump is AllowAny (stations have no user session). The gate must run FIRST,
        # unconditionally — otherwise an anonymous request with no/unknown station_uuid
        # falls through to the fallback below and leaks the entire dataset with no license.
        _require_license_for_export()

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


class PrintJobViewSet(viewsets.ModelViewSet):
    queryset = PrintJob.objects.all().select_related('station', 'nomenclature')
    serializer_class = PrintJobSerializer

    # USB download endpoints stay open for the offline/USB transfer flow.
    _PUBLIC_ACTIONS = {"download_for_usb", "download_usb_bundle"}

    def get_permissions(self):
        from rest_framework.permissions import AllowAny
        if getattr(self, "action", None) in self._PUBLIC_ACTIONS:
            return [AllowAny()]
        return super().get_permissions()

    def perform_create(self, serializer):
        job = serializer.save()
        station_name = job.station.station_name if job.station else '—'
        product_name = job.nomenclature.name if job.nomenclature else '—'
        log_event('job_created', f'Создано задание #{job.pk} «{product_name}» для станции «{station_name}»')

    @action(detail=True, methods=['post'])
    def send_to_station(self, request, pk=None):
        """
        Sends a print job to the assigned station via HTTP.
        """
        # Pushing a real print job (nomenclature payload) to a station is a data export -> gated.
        _require_license_for_export()
        job = self.get_object()
        station = job.station

        if not station.station_ip:
            job.status = 'error'
            job.save(update_fields=['status', 'updated_at'])
            return Response({'error': tr('station.noIp')}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            'type': 'PRINT_JOB',
            'job_id': job.pk,
            'nomenclature_id': job.nomenclature_id,
            'nomenclature_name': job.nomenclature.name,
            'nomenclature_article': job.nomenclature.article,
            'quantity': job.quantity,
            'quantity_unit': job.quantity_unit,
            'batch_number': job.batch_number,
            'marking_date': job.marking_date.isoformat() if job.marking_date else None,
        }

        target_port = station.station_port or 5556
        url = f'http://{station.station_ip}:{target_port}/api/print_job'

        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            job.status = 'sent'
            job.save(update_fields=['status', 'updated_at'])
            log_event('job_sent', f'Задание #{job.pk} «{job.nomenclature.name}» отправлено на станцию «{station.station_name}»')
            return Response({'status': 'success', 'message': tr('job.sentToStation', station=station.station_name)})
        except requests.RequestException as e:
            job.status = 'error'
            job.save(update_fields=['status', 'updated_at'])
            return Response({'error': tr('job.sendError', error=str(e))}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=True, methods=['get'])
    def download_for_usb(self, request, pk=None):
        """
        Downloads a single print job as an encrypted .lpj file for USB transfer.
        """
        _require_license_for_export()
        from common.crypto_utils import encrypt_data
        from django.http import HttpResponse
        import datetime

        job = self.get_object()
        data = {
            'type': 'PRINT_JOB',
            'jobs': [{
                'job_id': job.pk,
                'nomenclature_id': job.nomenclature_id,
                'nomenclature_name': job.nomenclature.name,
                'nomenclature_article': job.nomenclature.article,
                'quantity': job.quantity,
                'quantity_unit': job.quantity_unit,
                'batch_number': job.batch_number,
                'marking_date': job.marking_date.isoformat() if job.marking_date else None,
            }],
            'station': {
                'uuid': str(job.station.station_uuid),
                'number': job.station.station_number,
                'name': job.station.station_name,
            },
            'meta': {
                'generated_at': datetime.datetime.now().isoformat(),
                'server_version': settings.VERSION,
            }
        }

        encrypted = encrypt_data(data)
        filename = f"job_{job.pk}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.lpj"
        response = HttpResponse(encrypted, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        job.status = 'sent'
        job.save(update_fields=['status', 'updated_at'])
        return response

    @action(detail=False, methods=['get'])
    def download_usb_bundle(self, request):
        """
        Downloads ALL pending print jobs as a single encrypted .lpj file,
        grouped by station. Ideal for USB transfer of multiple jobs at once.
        Optionally filter by station with ?station_id=<id>.
        """
        _require_license_for_export()
        from common.crypto_utils import encrypt_data
        from django.http import HttpResponse
        import datetime

        station_id = request.query_params.get('station_id')
        qs = PrintJob.objects.filter(status='pending').select_related('station', 'nomenclature')
        if station_id:
            qs = qs.filter(station_id=station_id)

        if not qs.exists():
            return Response({'error': tr('job.noPending')}, status=status.HTTP_404_NOT_FOUND)

        stations_data = {}
        job_ids = []
        for job in qs:
            key = str(job.station.station_uuid)
            if key not in stations_data:
                stations_data[key] = {
                    'station': {
                        'uuid': str(job.station.station_uuid),
                        'number': job.station.station_number,
                        'name': job.station.station_name,
                    },
                    'jobs': []
                }
            stations_data[key]['jobs'].append({
                'job_id': job.pk,
                'nomenclature_id': job.nomenclature_id,
                'nomenclature_name': job.nomenclature.name,
                'nomenclature_article': job.nomenclature.article,
                'quantity': job.quantity,
                'quantity_unit': job.quantity_unit,
                'batch_number': job.batch_number,
                'marking_date': job.marking_date.isoformat() if job.marking_date else None,
            })
            job_ids.append(job.pk)

        data = {
            'type': 'PRINT_JOB_BUNDLE',
            'stations': list(stations_data.values()),
            'meta': {
                'total_jobs': len(job_ids),
                'generated_at': datetime.datetime.now().isoformat(),
                'server_version': settings.VERSION,
            }
        }

        encrypted = encrypt_data(data)
        filename = f"print_jobs_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.lpj"
        response = HttpResponse(encrypted, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        # Mark all bundled jobs as sent
        qs.filter(pk__in=job_ids).update(status='sent')
        return response

