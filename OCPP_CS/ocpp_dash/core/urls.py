from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ChargePointViewSet, TransactionViewSet, MeterValueViewSet, EventLogViewSet, FuzzJobViewSet, events_stream, ControlCommandViewSet, fuzz_stream 
)
from .views import cp_status

router = DefaultRouter()
router.register(r'cps', ChargePointViewSet, basename='cps')
router.register(r'tx', TransactionViewSet, basename='tx')
router.register(r'mv', MeterValueViewSet, basename='mv')
router.register(r'events', EventLogViewSet, basename='events')
router.register(r'fuzz', FuzzJobViewSet, basename='fuzz')
router.register(r'control', ControlCommandViewSet, basename='control')

urlpatterns = [
    path('cps/<str:cp_id>/status/', cp_status, name='cp-status'),
    path('events/stream/', events_stream),
    path("events/fuzz/stream/", fuzz_stream, name="fuzz-stream"),
    path('', include(router.urls)),

   # ← 추가 (SSE)
]
