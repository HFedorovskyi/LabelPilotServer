from django.contrib import admin
from .models import Pallet, PalletItem


class PalletItemInline(admin.TabularInline):
    model = PalletItem
    extra = 1


@admin.register(Pallet)
class PalletAdmin(admin.ModelAdmin):
    list_display = ('pallet_number', 'shipping_date', 'production_date', 'created')
    search_fields = ('pallet_number',)
    inlines = [PalletItemInline]
