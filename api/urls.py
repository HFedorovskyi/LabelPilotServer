from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    NomenclatureViewSet,
    NomenclatureFolderViewSet,
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
    LicenseRefreshView,
    LicenseSeatListView,
    LicenseSeatListRequestView,
    LicenseSeatListImportView,
)
from api.statistics_views import StatisticsView, StationLabelsView, StationsTodayView
from api.production import (ProductionSettingsView, ProductionTodayView, StationDaysView, StationJournalView,
                            StationLabelsPeriodView, StationStatsView)
from api.search_views import SearchView
from notifications.views import NotificationsView, NotificationsSeenView
from api.auth_views import (
    CsrfView, LoginView, LogoutView, MeView, BootstrapStatusView, BootstrapView,
)
from api.user_views import UserViewSet
from api.operator_views import OperatorViewSet
from api.system_views import (
    BackupRestoreView, BackupsView, UpdateFileView, UpdateProgressView, UpdateView,
)


router = DefaultRouter()
router.register(r'nomenclature', NomenclatureViewSet)
router.register(r'nomenclature_folders', NomenclatureFolderViewSet)
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
    path('statistics/stations_today/', StationsTodayView.as_view(), name='stations-today'),
    path('production/today/', ProductionTodayView.as_view(), name='production-today'),
    path('production/settings/', ProductionSettingsView.as_view(), name='production-settings'),
    path('stations/<uuid:uuid>/stats/', StationStatsView.as_view(), name='station-stats'),
    path('stations/<uuid:uuid>/days/', StationDaysView.as_view(), name='station-days'),
    path('stations/<uuid:uuid>/labels/', StationLabelsPeriodView.as_view(), name='station-labels-period'),
    path('stations/<uuid:uuid>/journal/', StationJournalView.as_view(), name='station-journal'),
    path('search/', SearchView.as_view(), name='search'),
    path('notifications/', NotificationsView.as_view(), name='notifications'),
    path('notifications/seen/', NotificationsSeenView.as_view(), name='notifications-seen'),
    path('full_sync/', FullSyncView.as_view(), name='full-sync'),
    path('version/', VersionView.as_view(), name='version'),
    path('system/update/', UpdateView.as_view(), name='system-update'),
    path('system/update/file/', UpdateFileView.as_view(), name='system-update-file'),
    path('system/update/progress/', UpdateProgressView.as_view(), name='system-update-progress'),
    path('system/backups/', BackupsView.as_view(), name='system-backups'),
    path('system/backups/<str:backup_id>/restore/', BackupRestoreView.as_view(), name='system-backup-restore'),
    path('license/', LicenseView.as_view(), name='license'),
    path('license/import/', LicenseImportView.as_view(), name='license-import'),
    path('license/refresh/', LicenseRefreshView.as_view(), name='license-refresh'),
    path('license/seat-list/', LicenseSeatListView.as_view(), name='license-seat-list'),
    path('license/seat-list/request/', LicenseSeatListRequestView.as_view(), name='license-seat-list-request'),
    path('license/seat-list/import/', LicenseSeatListImportView.as_view(), name='license-seat-list-import'),
    path('', include(router.urls)),
]
