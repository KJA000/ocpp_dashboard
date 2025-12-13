from django.contrib import admin
from .models import ChargePoint, Transaction, MeterValue, EventLog, FuzzJob, ControlCommand

@admin.register(ChargePoint)
class CPAdmin(admin.ModelAdmin):
    list_display = ('id', 'cp_id', 'vendor', 'model', 'status')  # ✅ last_seen, created_at 제거
    search_fields = ('cp_id',)

@admin.register(Transaction)
class TXAdmin(admin.ModelAdmin):
    list_display = ('id', 'cp', 'transaction_id', 'connector_id', 'started_at', 'stopped_at', 'energy_Wh')
    search_fields = ('cp__cp_id',)

@admin.register(MeterValue)
class MVAdmin(admin.ModelAdmin):
    list_display = ('id', 'cp', 'ts', 'power_W', 'energy_Wh', 'voltage_V', 'current_A', 'soc_percent')  # ✅ transaction 제거
    search_fields = ('cp__cp_id',)

@admin.register(EventLog)
class EVAdmin(admin.ModelAdmin):
    list_display = ('id', 'cp', 'direction', 'action', 'created_at')
    search_fields = ('cp__cp_id', 'action')

@admin.register(FuzzJob)
class FZAdmin(admin.ModelAdmin):
    list_display = ('id', 'scenario', 'status', 'started_at', 'ended_at')

@admin.register(ControlCommand)
class CCAdmin(admin.ModelAdmin):
    list_display = ('id', 'cp_id', 'type', 'created_at')
