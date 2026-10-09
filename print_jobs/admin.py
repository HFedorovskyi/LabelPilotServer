from django.contrib import admin
from print_jobs.models import PrintJob


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'station', 'nomenclature', 'quantity', 'quantity_unit', 'batch_number', 'status', 'created_at')
    list_filter = ('status', 'quantity_unit', 'station')
    search_fields = ('batch_number', 'nomenclature__name', 'nomenclature__article')
