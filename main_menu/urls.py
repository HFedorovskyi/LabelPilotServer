from .views import MainMenuView
from django.urls import path

app_name = 'main_menu'


urlpatterns = [
    path('', MainMenuView.as_view(), name='main_menu'),
]