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
    LicenseImportView,
)
from api.statistics_views import StatisticsView, StationLabelsView
from api.search_views import SearchView, NotificationsView
from api.auth_views import (
    CsrfView, LoginView, LogoutView, MeView, BootstrapStatusView, BootstrapView,
)
from api.user_views import UserViewSet
from api.operator_views import OperatorViewSet


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
router.register(r'users', UserViewSet, basename='user')
router.register(r'operators', OperatorViewSet)


urlpatterns = [
    path('auth/csrf/', CsrfView.as_view(), name='auth-csrf'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', MeView.as_view(), name='auth-me'),
    path('auth/bootstrap-status/', BootstrapStatusView.as_view(), name='auth-bootstrap-status'),
    path('auth/bootstrap/', BootstrapView.as_view(), name='auth-bootstrap'),
    path('statistics/', StatisticsView.as_view(), name='statistics'),
    path('statistics/station_labels/', StationLabelsView.as_view(), name='station-labels'),
    path('search/', SearchView.as_view(), name='search'),
    path('notifications/', NotificationsView.as_view(), name='notifications'),
    path('full_sync/', FullSyncView.as_view(), name='full-sync'),
    path('version/', VersionView.as_view(), name='version'),
    path('license/', LicenseView.as_view(), name='license'),
    path('license/import/', LicenseImportView.as_view(), name='license-import'),
    path('', include(router.urls)),
]
