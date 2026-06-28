from rest_framework import serializers
from Nomenclature.models import Nomenclature, ProductPackLink, GlobalProductAttribute, NomenclatureFolder


# ... (rest of imports)

# ... (previous classes)

class ProductPackLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPackLink
        fields = '__all__'

from Packs.models import Pack
from LabelTemplates.models import LabelTemplates
from BarcodeTemplates.models import BarcodeTemplate
from label_stations.models import LabelsStations

import json

class PackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pack
        fields = '__all__'


from Pallets.models import Pallet, PalletItem


class PalletItemSerializer(serializers.ModelSerializer):
    article = serializers.CharField(source='nomenclature.article', read_only=True)
    name = serializers.CharField(source='nomenclature.name', read_only=True)

    class Meta:
        model = PalletItem
        fields = ['id', 'nomenclature', 'article', 'name', 'quantity',
                  'batch_number', 'weight_netto', 'weight_brutto', 'order']


class PalletSerializer(serializers.ModelSerializer):
    items = PalletItemSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField()

    class Meta:
        model = Pallet
        fields = ['id', 'pallet_number', 'shipping_date', 'production_date',
                  'note', 'items', 'totals', 'created', 'edited']

    def get_totals(self, obj):
        items = list(obj.items.all())
        return {
            'count': round(sum(i.quantity for i in items), 3),
            'positions': len(items),
            'weight_netto': round(sum(i.weight_netto for i in items), 3),
            'weight_brutto': round(sum(i.weight_brutto for i in items), 3),
        }

class LabelTemplatesSerializer(serializers.ModelSerializer):
    # 'structure' is for Electron client (which expects a string)
    structure = serializers.SerializerMethodField()
    # 'scheme' is for the React web designer (which expects a JSON object)
    scheme = serializers.SerializerMethodField()

    class Meta:
        model = LabelTemplates
        fields = ['id', 'name', 'scheme', 'structure', 'created_at', 'updated_at']

    def get_scheme(self, obj):
        import copy
        scheme = copy.deepcopy(obj.scheme)
        if isinstance(scheme, dict) and 'elements' in scheme and isinstance(scheme['elements'], list):
            for el in scheme['elements']:
                if el.get('type') == 'text':
                    text_val = el.get('text', '')
                    if '{{ pack_number }}' in text_val or '{{ box_number }}' in text_val:
                        el['minLength'] = 12
        return scheme

    def create(self, validated_data):
        # scheme is a SerializerMethodField (read-only), so we pull it from raw request data
        request = self.context.get('request')
        if request and 'scheme' in request.data:
            validated_data['scheme'] = request.data['scheme']
        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context.get('request')
        if request and 'scheme' in request.data:
            validated_data['scheme'] = request.data['scheme']
        return super().update(instance, validated_data)

    def get_structure(self, obj):
        # We store it as JSONField in DB, so obj.scheme is already an object.
        # We dump it to string for the Electron client.
        
        # DEEP COPY to match implementation plan and avoid mutation issues if any cache exists
        import copy
        scheme = copy.deepcopy(obj.scheme)
        
        # Ensure elements exist
        if isinstance(scheme, dict) and 'elements' in scheme and isinstance(scheme['elements'], list):
            for el in scheme['elements']:
                if el.get('type') == 'barcode':
                    # The Designer saves the "Template Name" (Human Readable) in 'barcodeType'.
                    # The Client needs the "Technical Type" (bwip-js, e.g. ean13).
                    
                    template_id = el.get('templateId')
                    current_type_name = el.get('barcodeType')
                    
                    bt = None
                    # Try finding by ID first
                    if template_id:
                        try:
                            bt = BarcodeTemplate.objects.get(pk=template_id)
                        except BarcodeTemplate.DoesNotExist:
                            pass
                    
                    # Fallback to name if no ID or ID not found
                    if not bt and current_type_name:
                        try:
                            bt = BarcodeTemplate.objects.get(name=current_type_name)
                        except BarcodeTemplate.DoesNotExist:
                            pass
                            
                    # If found, replace the field with technical type
                    if bt and isinstance(bt.structure, dict):
                        technical_type = bt.structure.get('barcode_type')
                        if technical_type:
                            el['barcodeType'] = technical_type
                
                # Check for counters that need length = 12
                elif el.get('type') == 'text':
                    text_val = el.get('text', '')
                    if '{{ pack_number }}' in text_val or '{{ box_number }}' in text_val:
                        el['minLength'] = 12

        return json.dumps(scheme)

class BarcodeTemplateSerializer(serializers.ModelSerializer):
    structure = serializers.JSONField()

    class Meta:
        model = BarcodeTemplate
        fields = ['id', 'name', 'structure']

    def validate_structure(self, value):
        from api.utils import validate_structure as validate_barcode_structure
        errors = validate_barcode_structure(value)
        if errors:
            raise serializers.ValidationError(errors)
        return value

class LabelsStationsSerializer(serializers.ModelSerializer):
    station_number = serializers.SerializerMethodField()

    class Meta:
        model = LabelsStations
        fields = '__all__'

    def get_station_number(self, obj):
        if obj.station_number is not None:
            return f"{obj.station_number:02d}"
        return None

class NomenclatureSerializer(serializers.ModelSerializer):
    portion_container_name = serializers.CharField(source='portion_container.name', read_only=True)
    box_container_name = serializers.CharField(source='box_container.name', read_only=True)
    templates_pack_label_name = serializers.CharField(source='templates_pack_label.name', read_only=True)
    templates_box_label_name = serializers.CharField(source='templates_box_label.name', read_only=True)

    class Meta:
        model = Nomenclature
        fields = '__all__'

class ProductPackLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPackLink
        fields = '__all__'

class NomenclatureFolderSerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = NomenclatureFolder
        fields = ['id', 'name', 'order', 'item_count']

    def get_item_count(self, obj):
        return obj.items.count()


class GlobalProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalProductAttribute
        fields = '__all__'


from print_jobs.models import PrintJob

class PrintJobSerializer(serializers.ModelSerializer):
    station_name = serializers.CharField(source='station.station_name', read_only=True)
    nomenclature_name = serializers.CharField(source='nomenclature.name', read_only=True)
    nomenclature_article = serializers.CharField(source='nomenclature.article', read_only=True)

    class Meta:
        model = PrintJob
        fields = '__all__'

