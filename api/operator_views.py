"""Operators CRUD (server-managed factory-floor workers). manager+ can manage them.

The web API hides pin_hash and accepts a write-only `pin` (hashed server-side); the
synced bundle (see _gather_sync_data) carries pin_hash so clients validate PINs offline."""
from rest_framework import viewsets, serializers

from label_stations.models import Operator
from api.permissions import IsManagerOrAdmin


class OperatorSerializer(serializers.ModelSerializer):
    has_pin = serializers.SerializerMethodField()
    pin = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Operator
        fields = ['id', 'uuid', 'full_name', 'short_code', 'is_active', 'station', 'has_pin', 'pin']
        read_only_fields = ['id', 'uuid']

    def get_has_pin(self, obj):
        return bool(obj.pin_hash)

    def create(self, validated):
        pin = validated.pop('pin', None)
        op = Operator(**validated)
        if pin is not None:
            op.set_pin(pin)
        op.save()
        return op

    def update(self, instance, validated):
        pin = validated.pop('pin', None)
        for k, v in validated.items():
            setattr(instance, k, v)
        if pin is not None:          # '' clears the PIN
            instance.set_pin(pin)
        instance.save()
        return instance


class OperatorViewSet(viewsets.ModelViewSet):
    queryset = Operator.objects.all().order_by('full_name')
    serializer_class = OperatorSerializer
    permission_classes = [IsManagerOrAdmin]
