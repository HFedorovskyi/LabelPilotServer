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
    NomenclatureFolderSerializer,
    PrintJobSerializer,
    PalletSerializer,
)

from Nomenclature.models import Nomenclature, ProductPackLink, GlobalProductAttribute, NomenclatureFolder
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
from django.core.exceptions import ValidationError as DjangoValidationError


def _require_license_for_export():
    """Pushing REAL station data (nomenclature, identity, sync bundle) requires a valid
    license — ALWAYS, independent of LICENSE_REQUIRED/STRICT. This is THE commercial
    boundary the vendor chose: without a license the product runs in demo (full local UI
    + the built-in client demo with a station/printer/scale work fine), but real data is
    never exported to a station.

    Implementation lives in licensing.enforcement (fresh signature re-verify + machine +
    expiry + integrity fingerprint). A second gate runs inside crypto_utils.encrypt_data
    in production so this helper is not the only line an attacker must delete.
    """
    from licensing.enforcement import require_export_or_http
    require_export_or_http()


def _require_station_seat(station):
    """Station data only goes to a station holding an active licence seat."""
    from licensing import seats
    try:
        seats.ensure_may_receive_data(station)
    except seats.SeatError as error:
        raise _seat_denied(error)


def _mark_data_handed_over(station):
    """The station got the full data set (USB file or its own pull): products changed before
    now are on it. Like a USB print job, a downloaded file counts as handed over."""
    from django.utils import timezone as tz
    LabelsStations.objects.filter(pk=station.pk).update(data_pushed_at=tz.now())


def _station_license_token():
    """The signed license token for a station, or None without a valid commercial
    license (the same gate as every data export)."""
    from licensing.core import load_license
    from licensing.enforcement import commercial_license_ok
    ok, _reason = commercial_license_ok()
    if not ok:
        return None
    lic = load_license()
    return lic.token if lic is not None else None


def _seat_denied(error):
    from rest_framework.exceptions import PermissionDenied
    return PermissionDenied(tr(error.code))


def _actor(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return ''
    return user.get_username()


class ProductPackLinkViewSet(viewsets.ModelViewSet):
    queryset = ProductPackLink.objects.all().order_by('-created')
    serializer_class = ProductPackLinkSerializer

class GlobalProductAttributeViewSet(viewsets.ModelViewSet):
    queryset = GlobalProductAttribute.objects.all().order_by('-created')
    serializer_class = GlobalProductAttributeSerializer

    def perform_destroy(self, instance):
        # The field's values go from every product too, so no template keeps printing a
        # value nobody can see or edit any more; `edited` moves, so stations get the change.
        from django.db import transaction
        with transaction.atomic():
            for product in Nomenclature.objects.filter(extra_data__has_key=instance.name):
                product.extra_data.pop(instance.name, None)
                product.save(update_fields=['extra_data', 'edited'])
            instance.delete()


class NomenclatureFolderViewSet(viewsets.ModelViewSet):
    """CRUD for nomenclature folders (server-side catalog organization)."""
    queryset = NomenclatureFolder.objects.all().order_by('order', 'name')
    serializer_class = NomenclatureFolderSerializer


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

    def get_queryset(self):
        qs = super().get_queryset()
        # ?no_template=1: products a station cannot print (no pack label template).
        if self.request.query_params.get('no_template') == '1':
            qs = qs.filter(templates_pack_label__isnull=True)
        return qs

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

def _mark_products_changed(condition):
    """Stations get tare weights and label templates together with the products. A
    changed or removed one makes the products using it "changed since the last push",
    so the admin shows those stations as behind until the data is sent again."""
    from django.utils import timezone
    Nomenclature.objects.filter(condition).update(edited=timezone.now())


class PacksViewSet(viewsets.ModelViewSet):
    queryset = Pack.objects.all().order_by('-created')
    serializer_class = PackSerializer

    def perform_update(self, serializer):
        from django.db.models import Q
        pack = serializer.save()
        _mark_products_changed(Q(portion_container=pack) | Q(box_container=pack))

    def perform_destroy(self, instance):
        from django.db.models import Q
        _mark_products_changed(Q(portion_container=instance) | Q(box_container=instance))
        instance.delete()


class PalletViewSet(viewsets.ModelViewSet):
    queryset = Pallet.objects.all().prefetch_related('items', 'items__nomenclature').order_by('-created')
    serializer_class = PalletSerializer

class LabelTemplatesViewSet(viewsets.ModelViewSet):
    queryset = LabelTemplates.objects.all()
    serializer_class = LabelTemplatesSerializer

    @staticmethod
    def _users(template):
        from django.db.models import Q
        return Q(templates_pack_label=template) | Q(templates_box_label=template) | Q(templates_pallet_label=template)

    def perform_update(self, serializer):
        template = serializer.save()
        _mark_products_changed(self._users(template))

    def perform_destroy(self, instance):
        _mark_products_changed(self._users(instance))
        instance.delete()

def _labels_with_barcode(template_id, name):
    """Label templates whose barcode points at this barcode template (by id, or by name in
    templates saved before ids were stored)."""
    found = []
    for label in LabelTemplates.objects.all():
        elements = label.scheme.get('elements') if isinstance(label.scheme, dict) else None
        for el in elements or []:
            if not isinstance(el, dict) or el.get('type') != 'barcode':
                continue
            ref = el.get('templateId')
            if (ref and ref == template_id) or (not ref and name and el.get('barcodeType') == name):
                found.append(label)
                break
    return found


class BarcodeTemplatesViewSet(viewsets.ModelViewSet):
    queryset = BarcodeTemplate.objects.all()
    serializer_class = BarcodeTemplateSerializer

    # Stations get the symbology and parts of a barcode with the label templates that
    # use it: their products count as changed, like after a tare or template edit.
    def _mark_users(self, template_id, name):
        from django.db.models import Q
        labels = _labels_with_barcode(template_id, name)
        if labels:
            _mark_products_changed(Q(templates_pack_label__in=labels) | Q(templates_box_label__in=labels) | Q(templates_pallet_label__in=labels))

    def perform_update(self, serializer):
        old_name = serializer.instance.name
        template = serializer.save()
        self._mark_users(template.pk, old_name)

    def perform_destroy(self, instance):
        self._mark_users(instance.pk, instance.name)
        instance.delete()

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
        return Response(_license_payload())


def _license_payload():
    """Licence status + seats + verifier facts (status, import and refresh views)."""
    from django.conf import settings
    from licensing import license_status, license_state, commercial_license_ok
    data = dict(license_status())
    st = license_state()
    # Surfaced separately so the admin UI can tell "bound to a different machine"
    # apart from "no license" (license_status() reports a wrong-machine license as
    # unlicensed). `strict` reflects the effective fail-closed posture.
    data['strict'] = bool(getattr(settings, 'LICENSE_REQUIRED', False)) or not bool(getattr(settings, 'DEBUG', False))
    data['signature_valid'] = st.signature_valid
    data['machine_ok'] = st.machine_ok
    # What the licence file is, for «Лицензия»: none, valid here, issued for another server
    # (e.g. the server moved to new hardware) or not a LabelPilot licence at all.
    data['license_file'] = ('none' if not st.present else 'invalid' if not st.signature_valid
                            else 'foreign' if not st.machine_ok else 'ok')
    from licensing.seats import summary as seat_summary
    data['seats'] = seat_summary()
    data['stations_used'] = data['seats']['active']
    from licensing.refresh import last_refresh
    data['refresh_last'] = last_refresh()
    try:
        from licensing.seat_list import status as seat_list_status
        data['seat_list'] = seat_list_status()
    except Exception:
        data['seat_list'] = {'required': False}
    ok, reason = commercial_license_ok()
    data['commercial_ok'] = ok
    data['commercial_reason'] = reason
    try:
        from licensing.integrity import integrity_status
        data['integrity'] = integrity_status()
    except Exception:
        data['integrity'] = {'integrity_ok': None}
    try:
        from licensing.native_guard import native_guard_status
        guard = native_guard_status()
        data['native_guard'] = {
            'available': guard.get('available'),
            'ok': guard.get('ok'),
            'reason': guard.get('reason'),
        }
    except Exception:
        data['native_guard'] = {'available': False, 'ok': False, 'reason': 'native_guard'}
    return data


from api.permissions import IsAdmin as _IsAdmin


class LicenseRefreshView(APIView):
    """Admin-only: ask the LabelPilot sales service for a renewed licence now
    (the server also checks once a day when online).
    POST /api/v1/license/refresh/ -> licence payload + {"refresh": {status, detail}}."""
    permission_classes = [_IsAdmin]

    def post(self, request):
        from licensing.refresh import refresh_license
        result = refresh_license()
        if result.status == 'updated':
            from licensing.seat_list import schedule_sync
            schedule_sync(0.5)  # a licence that now uses a seat list gets one at once
        data = _license_payload()
        data['refresh'] = {'status': result.status, 'detail': result.detail}
        return Response(data)


class LicenseSeatListView(APIView):
    """Admin-only: the vendor-signed seat list (licences with the "seat-list" feature).
    GET  /api/v1/license/seat-list/          -> licence payload (incl. "seat_list")
    POST /api/v1/license/seat-list/          -> ask the sales service for a fresh list now
    The server also renews it daily and a few seconds after every seat change."""
    permission_classes = [_IsAdmin]

    def get(self, request):
        return Response(_license_payload())

    def post(self, request):
        from licensing.seat_list import sync
        result = sync()
        data = _license_payload()
        data['seat_list_sync'] = {'status': result.status, 'detail': result.detail}
        return Response(data)


class LicenseSeatListRequestView(APIView):
    """Admin-only: the request file an offline site has signed in the customer cabinet.
    GET /api/v1/license/seat-list/request/ -> JSON attachment."""
    permission_classes = [_IsAdmin]

    def get(self, request):
        import json as _json
        from django.http import HttpResponse
        from licensing.seat_list import request_document
        try:
            document = request_document()
        except ValueError:
            return Response({'detail': tr('license.exportDenied')}, status=status.HTTP_409_CONFLICT)
        response = HttpResponse(
            _json.dumps(document, indent=2), content_type='application/json',
        )
        response['Content-Disposition'] = f'attachment; filename="seat-request-{document["license_id"]}.json"'
        return response


class LicenseSeatListImportView(APIView):
    """Admin-only: install a seat list signed in the customer cabinet (offline sites).
    POST /api/v1/license/seat-list/import/  (multipart 'file' OR JSON {token})."""
    permission_classes = [_IsAdmin]

    def post(self, request):
        from licensing.seat_list import install

        raw = None
        f = request.FILES.get('file')
        if f is not None:
            try:
                raw = f.read(5 * 1024 * 1024).decode('utf-8').strip()
            except Exception:
                raw = None
        if not raw:
            raw = str(request.data.get('token') or '').strip()
        if not raw:
            return Response({'detail': tr('license.importNoFile')}, status=status.HTTP_400_BAD_REQUEST)
        try:
            install(raw)
        except ValueError as error:
            key = 'license.seatListOlder' if 'older' in str(error) else 'license.seatListInvalid'
            return Response({'detail': tr(key)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({'detail': tr('license.seatListInvalid')}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_license_payload())


class LicenseImportView(APIView):
    """Admin-only: install/replace license.lpl from an uploaded file (or pasted token).
    The Ed25519 signature is verified BEFORE writing, so only a vendor-signed license is
    accepted. Picked up live — license_state() caches on the file's (mtime, size), so the
    server flips out of demo on the next status read without a restart.
    POST /api/v1/license/import/  (multipart 'file' OR JSON {token})."""
    permission_classes = [_IsAdmin]

    def post(self, request):
        from licensing.core import _verify_and_parse
        from licensing.refresh import install_license_token

        raw = None
        f = request.FILES.get('file')
        if f is not None:
            try:
                raw = f.read().decode('utf-8').strip()
            except Exception:
                raw = None
        if not raw:
            raw = (request.data.get('token') or '').strip()
        if not raw:
            return Response({'detail': tr('license.importNoFile')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            _verify_and_parse(raw)  # raises on bad signature / malformed payload
        except Exception:
            return Response({'detail': tr('license.importInvalid')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            install_license_token(raw)  # atomic replace
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        from licensing.seat_list import reset_cache as reset_seat_list, schedule_sync
        reset_seat_list()
        schedule_sync(0.5)

        data = _license_payload()
        # Notify sales service: license file installed on this machine (async, optional).
        try:
            from licensing.telemetry import report_license_activated
            report_license_activated(data.get("license_id"))
        except Exception:
            pass
        return Response(data)


class StationsViewSet(viewsets.ModelViewSet):
    queryset = LabelsStations.objects.all()
    serializer_class = LabelsStationsSerializer
    lookup_field = 'station_uuid'

    # Only what stations themselves call stays OPEN (stations have no user session):
    # ping and report upload. Pushing or downloading a station's data set is an admin
    # action from the web UI, so it inherits closed-by-default IsAuthenticated — an
    # anonymous LAN host can no longer fetch a full data set by station UUID.
    _PUBLIC_ACTIONS = {"ping", "server_ip", "upload_report"}

    def get_permissions(self):
        from rest_framework.permissions import AllowAny
        if getattr(self, "action", None) in self._PUBLIC_ACTIONS:
            return [AllowAny()]
        return super().get_permissions()

    def perform_create(self, serializer):
        # A station over the licence's seat cap is registered as "pending": it is
        # visible to the admin but receives no data until a seat is free.
        from django.utils import timezone as tz
        from rest_framework.exceptions import ValidationError
        from licensing import seats
        state = seats.initial_state()
        if state is None:
            raise ValidationError({"license": tr('station.seatLimitReached')})
        station = serializer.save(seat_state=state, seat_changed_at=tz.now())
        seats.record_registration(station, actor=_actor(self.request))

    def perform_destroy(self, instance):
        # Deleting an active station frees its seat and spends a release.
        from licensing import seats
        try:
            seats.delete(instance, actor=_actor(self.request))
        except seats.SeatError as error:
            raise _seat_denied(error)

    def _seat_action(self, operation):
        from licensing import seats
        station = self.get_object()
        try:
            operation(station, actor=_actor(self.request))
        except seats.SeatError as error:
            raise _seat_denied(error)
        station.refresh_from_db()
        from notifications.checks import check_stations
        check_stations()
        return Response(self.get_serializer(station).data)

    @action(detail=True, methods=['post'], permission_classes=[_IsAdmin])
    def release_seat(self, request, station_uuid=None):
        from licensing import seats
        return self._seat_action(seats.release)

    @action(detail=True, methods=['post'], permission_classes=[_IsAdmin])
    def activate_seat(self, request, station_uuid=None):
        from licensing import seats
        return self._seat_action(seats.activate)

    @action(detail=True, methods=['post'], permission_classes=[_IsAdmin])
    def replace_hardware(self, request, station_uuid=None):
        from licensing import seats
        return self._seat_action(seats.replace_hardware)

    @action(detail=False, methods=['get'])
    def seat_events(self, request):
        from label_stations.models import SeatEvent
        events = SeatEvent.objects.all()[:200]
        return Response([{
            'station_uuid': str(event.station_uuid) if event.station_uuid else None,
            'station_name': event.station_name,
            'event': event.event,
            'actor': event.actor,
            'detail': event.detail,
            'created_at': event.created_at,
        } for event in events])


    def _gather_sync_data(self, station, sync_type='UPDATE'):
        """
        Helper method to gather all data for a station sync.
        Returns a unified dictionary structure.
        """
        # Third dispersed gate: even if a caller forgot _require_license_for_export(),
        # assembling a real sync payload still demands a commercial license.
        _require_license_for_export()
        _require_station_seat(station)

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
        
        from notifications import events as notify
        if not station.station_ip:
            notify.station_push(station, 'Station has no IP address')
            return Response({'error': 'Station has no IP address'}, status=status.HTTP_400_BAD_REQUEST)

        payload = self._gather_sync_data(station, sync_type='ONLINE_SYNC')

        # Use discovered port, default to 5556 (Client Sync Server Port)
        target_port = station.station_port or 5556
        url = f'http://{station.station_ip}:{target_port}/api/full_sync'

        # Encrypt the live push as LPI2 (the signed license token is embedded) so the station can
        # AUTHENTICATE the sender — an unauthenticated plaintext push from a rogue LAN host is
        # rejected. Matches the already-encrypted USB/download path (download_update).
        from common.crypto_utils import encrypt_data
        try:
            resp = requests.post(
                url, data=encrypt_data(payload),
                headers={'Content-Type': 'application/octet-stream'}, timeout=5,
            )
            resp.raise_for_status()
            from django.utils import timezone as tz
            station.last_sync_at = tz.now()
            station.data_pushed_at = station.last_sync_at
            station.save(update_fields=['last_sync_at', 'data_pushed_at', 'changed_at'])
            log_event('station_synced', f'Данные синхронизированы со станцией «{station.station_name}» (онлайн)')
            notify.station_push(station)
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
            notify.station_push(station, error_msg)
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
        _mark_data_handed_over(station)

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
        _mark_data_handed_over(station)
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
        from notifications import events as notify
        try:
            data = decrypt_data(file_obj.read())
        except Exception as e:
            notify.report_rejected(request.META.get('REMOTE_ADDR'))
            return Response({'error': f'Decryption failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        station_uuid = data.get('station_uuid')
        # station_uuid is a UUIDField; a malformed/non-UUID value raises ValidationError.
        # Treat it like an unknown station (process unattached) rather than 500 the endpoint.
        try:
            station = LabelsStations.objects.filter(station_uuid=station_uuid).first() if station_uuid else None
        except (ValueError, DjangoValidationError):
            station = None
        if station is not None:
            # Production records are always kept (traceability); the reporting device
            # is only observed so a cloned identity shows up as a conflict.
            from licensing import seats
            seats.observe_fingerprint(station, data.get('station_fingerprint'), 'report')

        labels_data = [it for it in (data.get('printed_labels') or []) if it.get('unique_id')]
        deleted_data = [it for it in (data.get('deleted_labels') or []) if it.get('unique_id')]
        logs_data = data.get('logs') or []

        new_labels, new_logs, fresh_logs = [], [], []
        deleted_uids = [it['unique_id'] for it in deleted_data]

        def _audit(it):
            # Per-pack traceability passport (same for the good + deleted insert paths).
            return {
                'weight_netto_grams': it.get('weight_netto_grams'),
                'weight_brutto_grams': it.get('weight_brutto_grams'),
                'batch': it.get('batch') or '',
                'production_date': it.get('production_date') or '',
                'expiration_date': it.get('expiration_date') or '',
                'barcode': it.get('barcode') or '',
            }

        # --- Printed labels: skip ids already stored, batch-resolve product/pack FKs ---
        if labels_data:
            uids = [it['unique_id'] for it in labels_data]
            seen = set(PrintedLabel.objects.filter(unique_id__in=uids).values_list('unique_id', flat=True))
            prods = Nomenclature.objects.in_bulk({it['product_id'] for it in labels_data if it.get('product_id')})
            for it in labels_data:
                uid = it['unique_id']
                if uid in seen:
                    continue
                seen.add(uid)  # also dedupes within this one payload
                prod = prods.get(it.get('product_id'))
                new_labels.append(PrintedLabel(
                    station=station,
                    station_user_name=it.get('user_name', ''),
                    product=prod,
                    product_name_snapshot=it.get('product_name', '') or (prod.name if prod else ''),
                    # A station's "pack" is its own weighed pack row (number in pack_name), not
                    # a tare from «Упаковка и тара»: its id must not be looked up as a Pack.
                    pack=None,
                    pack_name_snapshot=it.get('pack_name', '') or '',
                    unique_id=uid,
                    printed_at=parse_datetime(it.get('printed_at') or '') or tz.now(),
                    **_audit(it),
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
                fresh_logs.append(it)
                new_logs.append(StationLog(
                    station=station,
                    level=it.get('level', 'INFO'),
                    message=it.get('message', ''),
                    component=str(it.get('component') or '')[:32],
                    timestamp=parse_datetime(it.get('timestamp') or '') or tz.now(),
                    event_uid=euid or None,
                ))

        # --- Deleted weighings ("отвесы"): the station removed these packs from an open box.
        # Insert any not-yet-stored ones as is_deleted=True; the transaction below ALSO flips
        # every reported deleted uid to is_deleted=True, so a pack reported as good on an
        # earlier delta and only later deleted is reconciled. Idempotent on replay.
        if deleted_data:
            seen_d = set(PrintedLabel.objects.filter(unique_id__in=deleted_uids).values_list('unique_id', flat=True))
            dprods = Nomenclature.objects.in_bulk({it['product_id'] for it in deleted_data if it.get('product_id')})
            for it in deleted_data:
                uid = it['unique_id']
                if uid in seen_d:
                    continue
                seen_d.add(uid)
                prod = dprods.get(it.get('product_id'))
                new_labels.append(PrintedLabel(
                    station=station,
                    station_user_name=it.get('user_name', ''),
                    product=prod,
                    product_name_snapshot=it.get('product_name', '') or (prod.name if prod else ''),
                    # A station's "pack" is its own weighed pack row (number in pack_name), not
                    # a tare from «Упаковка и тара»: its id must not be looked up as a Pack.
                    pack=None,
                    pack_name_snapshot=it.get('pack_name', '') or '',
                    unique_id=uid,
                    printed_at=parse_datetime(it.get('printed_at') or '') or tz.now(),
                    **_audit(it),
                    is_deleted=True,
                    deleted_at=parse_datetime(it.get('deleted_at') or '') or tz.now(),
                ))

        with transaction.atomic():
            if new_labels:
                PrintedLabel.objects.bulk_create(new_labels, ignore_conflicts=True)
            if new_logs:
                StationLog.objects.bulk_create(new_logs, ignore_conflicts=True)
            # Reconcile good -> deleted for packs already stored from an earlier delta (Case B),
            # stamping each row's own deletion time so the dashboard buckets it on the right day.
            # NOTE: deletion is TERMINAL — the client has no "undelete", so this only ever flips
            # is_deleted False -> True; a row never goes back to good.
            for it in deleted_data:
                PrintedLabel.objects.filter(unique_id=it['unique_id']).update(
                    is_deleted=True,
                    deleted_at=parse_datetime(it.get('deleted_at') or '') or tz.now(),
                )
            if station:
                station.last_sync_at = tz.now()
                station.save(update_fields=['last_sync_at', 'changed_at'])

        # Notifications: every new station error, job progress / completion, client version.
        notify.station_errors(station, fresh_logs)
        jobs_updated = notify.job_progress(station, data.get('print_jobs') or [])
        notify.client_version(station, data.get('client_version'))

        labels_count, logs_count, deleted_count = len(new_labels), len(new_logs), len(deleted_data)
        station_label = station.station_name if station else station_uuid
        # Stations push a report every few dozen seconds while they print; only a report an
        # admin uploads by hand (.lpr from USB) is an event worth the activity list.
        if request.user.is_authenticated:
            log_event('report_imported', f'Импортирован отчёт со станции «{station_label}»: {labels_count} этикеток, {deleted_count} отвесов, {logs_count} логов')

        return Response({
            'status': 'success',
            'message': 'Report processed successfully',
            'details': {'labels_processed': labels_count, 'deleted_processed': deleted_count,
                        'logs_processed': logs_count, 'jobs_updated': jobs_updated},
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
        from licensing import seats
        station_uuid = request.query_params.get('station_uuid')
        message = "Pong"
        seat = None
        license_token = None
        seat_list_token = None

        if station_uuid:
            try:
                station = LabelsStations.objects.get(station_uuid=station_uuid)
                fingerprint = seats.observe_fingerprint(
                    station, request.query_params.get('fingerprint'), 'ping',
                )
                from notifications import events as notify
                notify.station_seen(station, conflict=fingerprint == seats.FINGERPRINT_CONFLICT)
                # A second device reusing this identity never marks it online.
                if fingerprint != seats.FINGERPRINT_CONFLICT:
                    station.is_online = True
                    station.save(update_fields=['is_online', 'changed_at'])
                    message = f"Pong, station {station.station_name} updated"
                seat = seats.station_seat(station, fingerprint)
                # A station that reports no vendor token (lost file, never synced) prints
                # DEMO-marked labels; one whose token is expiring asks for the renewal
                # (license=refresh). It gets the same public, signed token every LPI2
                # push embeds — only on its bound hardware, with an active seat, and
                # only while this server holds a valid commercial license.
                if (request.query_params.get('license') in ('none', 'refresh')
                        and fingerprint == seats.FINGERPRINT_MATCH
                        and seat['state'] == seats.SEAT_ACTIVE):
                    license_token = _station_license_token()
                # The vendor-signed seat list, so the station can show whether it is
                # listed (it checks the list in every data push anyway).
                if fingerprint == seats.FINGERPRINT_MATCH and seat.get('seat_list'):
                    from licensing.seat_list import push_token
                    seat_list_token = push_token()
            except (LabelsStations.DoesNotExist, ValueError, TypeError, DjangoValidationError):
                pass

        response = {
            'seat': seat,
            'status': 'online',
            'server_time': timezone.now(),
            'message': message,
            'server_version': settings.VERSION,
            'min_client_version': settings.MIN_CLIENT_VERSION,
            'latest_client_version': settings.LATEST_CLIENT_VERSION,
        }
        if license_token:
            response['license_token'] = license_token
        if seat_list_token:
            response['seat_list'] = seat_list_token
        return Response(response)

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
                data = self._gather_sync_data(station)
                _mark_data_handed_over(station)
                return Response(data)
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

    def get_queryset(self):
        """?status=error,pending narrows the list; ?recent_days=N drops jobs completed more
        than N days ago (the Print page refreshes the list every few seconds)."""
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(status__in=params['status'].split(','))
        days = params.get('recent_days', '')
        if days.isdigit():
            from datetime import timedelta
            from django.db.models import Q
            from django.db.models.functions import Coalesce
            from django.utils import timezone as tz
            since = tz.now() - timedelta(days=int(days))
            qs = qs.annotate(_done_at=Coalesce('completed_at', 'updated_at')).exclude(
                Q(status='completed') & Q(_done_at__lt=since))
        return qs

    def perform_create(self, serializer):
        job = serializer.save()
        station_name = job.station.station_name if job.station else '—'
        product_name = job.nomenclature.name if job.nomenclature else '—'
        log_event('job_created', f'Создано задание #{job.pk} «{product_name}» для станции «{station_name}»')

    def perform_update(self, serializer):
        job = serializer.save()
        # Marked done by hand: a station that does not report progress (older client, USB).
        if job.status == 'completed' and job.completed_at is None:
            from django.utils import timezone as tz
            job.completed_at = tz.now()
            job.save(update_fields=['completed_at'])

    @action(detail=True, methods=['post'])
    def send_to_station(self, request, pk=None):
        """
        Sends a print job to the assigned station via HTTP.
        """
        # Pushing a real print job (nomenclature payload) to a station is a data export -> gated.
        _require_license_for_export()
        job = self.get_object()
        station = job.station
        _require_station_seat(station)

        from notifications import events as notify
        from django.utils import timezone as tz
        if not station.station_ip:
            job.status = 'error'
            job.last_error = tr('station.noIp')[:500]
            job.save(update_fields=['status', 'last_error', 'updated_at'])
            notify.job_send(job, job.last_error)
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

        # Encrypt the live push as LPI2 so the station can authenticate the sender (see sync_data).
        from common.crypto_utils import encrypt_data
        try:
            resp = requests.post(
                url, data=encrypt_data(payload),
                headers={'Content-Type': 'application/octet-stream'}, timeout=5,
            )
            resp.raise_for_status()
            job.status = 'sent'
            job.sent_at = tz.now()
            job.last_error = ''
            job.save(update_fields=['status', 'sent_at', 'last_error', 'updated_at'])
            notify.job_send(job)
            log_event('job_sent', f'Задание #{job.pk} «{job.nomenclature.name}» отправлено на станцию «{station.station_name}»')
            return Response({'status': 'success', 'message': tr('job.sentToStation', station=station.station_name)})
        except requests.RequestException as e:
            job.status = 'error'
            job.last_error = str(e)[:500]
            job.save(update_fields=['status', 'last_error', 'updated_at'])
            notify.job_send(job, e)
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
        _require_station_seat(job.station)
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

        from django.utils import timezone as tz
        job.status = 'sent'
        job.sent_at = tz.now()
        job.save(update_fields=['status', 'sent_at', 'updated_at'])
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
        from licensing import seats
        qs = PrintJob.objects.filter(
            status='pending', station__seat_state='active',
        ).select_related('station', 'nomenclature')
        seated = seats.seated_ids()
        if seated is not None:
            qs = qs.filter(station_id__in=seated)
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
        from django.utils import timezone as tz
        qs.filter(pk__in=job_ids).update(status='sent', sent_at=tz.now())
        return response

