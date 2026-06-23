from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    NomenclatureViewSet, 
    PacksViewSet, 
    LabelTemplatesViewSet, 
    BarcodeTemplatesViewSet, 
    StationsViewSet,
    ProductPackLinkViewSet,
    GlobalProductAttributeViewSet,
    PrintJobViewSet,
    PalletViewSet,
    FullSyncView,
    VersionView,
    LicenseView,
)
from api.statistics_views import StatisticsView


router = DefaultRouter()
router.register(r'nomenclature', NomenclatureViewSet)
router.register(r'packs', PacksViewSet)
router.register(r'labels', LabelTemplatesViewSet)
router.register(r'barcodes', BarcodeTemplatesViewSet)
router.register(r'stations', StationsViewSet)
router.register(r'links', ProductPackLinkViewSet)
router.register(r'attributes', GlobalProductAttributeViewSet)
router.register(r'print_jobs', PrintJobViewSet)
router.register(r'pallets', PalletViewSet)


urlpatterns = [
    path('statistics/', StatisticsView.as_view(), name='statistics'),
    path('full_sync/', FullSyncView.as_view(), name='full-sync'),
    path('version/', VersionView.as_view(), name='version'),
    path('license/', LicenseView.as_view(), name='license'),
    path('', include(router.urls)),
]
