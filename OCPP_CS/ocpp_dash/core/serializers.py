# core/serializers.py
from rest_framework import serializers
from .models import ChargePoint, Transaction, MeterValue, EventLog, FuzzJob, ControlCommand
from django.utils import timezone

class ChargePointSerializer(serializers.ModelSerializer):
    online = serializers.SerializerMethodField()  # ✅ 최근 20초 이내 하트비트/상태면 online

    class Meta:
        model = ChargePoint
        fields = ['id','cp_id','vendor','model','status','last_seen','online']

    def get_online(self, obj):
        if not obj.last_seen:
            return False
        return (timezone.now() - obj.last_seen).total_seconds() < 20

class TransactionSummarySerializer(serializers.ModelSerializer):
    cp_id = serializers.CharField(source='cp.cp_id', read_only=True)
    class Meta:
        model = Transaction
        fields = ['id','transaction_id','cp_id','connector_id','started_at','stopped_at','meter_start','meter_stop','energy_Wh']

class MeterValueSerializer(serializers.ModelSerializer):
    cp_id = serializers.CharField(source='cp.cp_id', read_only=True)

    class Meta:
        model  = MeterValue
        fields = [
            'id', 'cp_id', 'ts',
            'power_W', 'energy_Wh', 'current_A', 'voltage_V', 'soc_percent',
            # 필요하면 'raw' 도 포함 가능
        ]

class EventLogSerializer(serializers.ModelSerializer):
    cp_id = serializers.CharField(source='cp.cp_id', read_only=True)
    class Meta:
        model = EventLog
        fields = ['id','cp_id','direction','action','payload','unique_id','created_at']

class FuzzJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuzzJob
        fields = ['id','scenario','status','started_at','ended_at']

class ControlCommandSerializer(serializers.ModelSerializer):
    class Meta:
        model = ControlCommand
        fields = ['id','cp_id','type','payload','created_at']
