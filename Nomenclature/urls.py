from .views import NomenclatureListView
from django.urls import path

app_name = 'Nomenclature'

urlpatterns = [
    path('', NomenclatureListView.as_view(), name='nomenclature'),
    path('', NomenclatureListView.as_view(), name='check_stations', kwargs={'stations': 'check_online'}),
    path('update_nomenclature_list/', NomenclatureListView.as_view(), name='update_nomenclature', kwargs={'view_type': 'list'}),
]