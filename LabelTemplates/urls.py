from django.urls import path
from .views import LabelTemplatesView, LabelTemplatesCreateView, LabelTemplatesUpdateView

app_name = 'LabelTemplates'

urlpatterns = [
    path('create_label/', LabelTemplatesCreateView.as_view(), name='label_templates_create'),
    path('', LabelTemplatesView.as_view(), name='label_templates'),
    path('edit/<int:label_id>/', LabelTemplatesUpdateView.as_view(), name='edit_label'),
]