"""URL configuration for LabelPilotServer."""
import os

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.http import HttpResponse, Http404
from django.views.static import serve as media_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def spa_index(_request):
    """Serve the frontend SPA entry (index.html) for client-side routes / deep links.
    WhiteNoise has already served any real static file before reaching here."""
    index_path = os.path.join(getattr(settings, 'FRONTEND_DIST', ''), 'index.html')
    if os.path.isfile(index_path):
        with open(index_path, 'rb') as fh:
            return HttpResponse(fh.read(), content_type='text/html')
    raise Http404('Frontend is not built (no index.html)')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('api.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

# WhiteNoise serves /static/. Media is user-uploaded at runtime, so serve it through
# Django's static view (works with DEBUG=False, unlike conf.urls.static.static()).
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', media_serve, {'document_root': settings.MEDIA_ROOT}),
]

# SPA fallback: any path that is not API/admin/static/media → the frontend index.html.
urlpatterns += [
    re_path(r'^(?!api/|admin/|static/|media/).*$', spa_index),
]

