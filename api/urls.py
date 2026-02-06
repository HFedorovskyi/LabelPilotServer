from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    NomenclatureViewSet, 
    PacksViewSet, 
    LabelTemplatesViewSet, 
    BarcodeTemplatesViewSet, 
    StationsViewSet,
    ProductPackLinkViewSet,
    GlobalProductAttributeViewSet
)


router = DefaultRouter()
router.register(r'nomenclature', NomenclatureViewSet)
router.register(r'packs', PacksViewSet)
router.register(r'labels', LabelTemplatesViewSet)
router.register(r'barcodes', BarcodeTemplatesViewSet)
router.register(r'stations', StationsViewSet)
router.register(r'links', ProductPackLinkViewSet)
router.register(r'attributes', GlobalProductAttributeViewSet)


urlpatterns = [
    path('', include(router.urls)),
]
