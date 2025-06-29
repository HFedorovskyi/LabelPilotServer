from django.urls import path
from .views import BarcodeTemplateListView

app_name = 'barcodeTemplates'

urlpatterns = [
    path('', BarcodeTemplateListView.as_view(), name='barcode_templates_list'),
]