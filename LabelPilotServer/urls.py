"""
URL configuration for LabelPilotServer project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('main_menu.urls')),
    path('label_stations/', include('label_stations.urls')),
    path('label_templates/', include('LabelTemplates.urls')),
    path('nomenclature/', include('Nomenclature.urls')),
    path('barcodes/', include('BarcodeTemplates.urls')),
    path('packs/', include('Packs.urls')),

]
