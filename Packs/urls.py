from .views import PacksTemplateListView
from django.urls import path

app_name = 'Packs'

urlpatterns = [
    path('', PacksTemplateListView.as_view(), name='packs')
]