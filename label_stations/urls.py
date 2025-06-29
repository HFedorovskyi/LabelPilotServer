
from .views import LabelStationsListView, LabelStationsEditView, LabelStationsAdding, DiscoverStationsView, LabelStationsDeleteView,UpdateStationStatusView
from django.urls import path

app_name = 'label_stations'

urlpatterns = [
    path('', LabelStationsListView.as_view(), name='label_stations_list'),
    path('discover/', DiscoverStationsView.as_view(), name='discover_clients'),
    path('save/', LabelStationsAdding.as_view(), name='label_stations_adding'),
    path('delete/', LabelStationsDeleteView.as_view(), name='delete_station'),
    path('update_name/', LabelStationsEditView.as_view(), name='update_station_name'),

    path('check_status/', UpdateStationStatusView.as_view(), name='check_status')
]
