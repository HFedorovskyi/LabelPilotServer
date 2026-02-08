from rest_framework import serializers
from Nomenclature.models import Nomenclature, ProductPackLink, GlobalProductAttribute


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

class LabelTemplatesSerializer(serializers.ModelSerializer):
    # 'structure' is for Electron client (which expects a string)
    structure = serializers.SerializerMethodField()
    # 'scheme' is for the React web designer (which expects a JSON object)
    scheme = serializers.JSONField()

    class Meta:
        model = LabelTemplates
        fields = ['id', 'name', 'scheme', 'structure', 'created_at', 'updated_at']

    def get_structure(self, obj):
        # We store it as JSONField in DB, so obj.scheme is already an object.
        # We dump it to string for the Electron client.
        return json.dumps(obj.scheme)

class BarcodeTemplateSerializer(serializers.ModelSerializer):
    structure = serializers.SerializerMethodField()

    class Meta:
        model = BarcodeTemplate
        fields = ['id', 'name', 'structure']

    def get_structure(self, obj):
        return json.dumps(obj.structure)

class LabelsStationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabelsStations
        fields = '__all__'

class NomenclatureSerializer(serializers.ModelSerializer):
    portion_container_name = serializers.CharField(source='portion_container.name', read_only=True)
    box_container_name = serializers.CharField(source='box_container.name', read_only=True)
    templates_pack_label_name = serializers.CharField(source='templates_pack_label.name', read_only=True)
    templates_box_label_name = serializers.CharField(source='templates_box_label.name', read_only=True)

    templates_box_label_name = serializers.CharField(source='templates_box_label.name', read_only=True)

    class Meta:
        model = Nomenclature
        fields = '__all__'

class ProductPackLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Nomenclature.pack_links.rel.model # Accessing the model class
        fields = '__all__'

class GlobalProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalProductAttribute
        fields = '__all__'

