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

class PackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pack
        fields = '__all__'

class LabelTemplatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabelTemplates
        fields = '__all__'

class BarcodeTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BarcodeTemplate
        fields = '__all__'

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

