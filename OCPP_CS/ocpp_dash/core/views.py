from rest_framework import viewsets, filters, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django.utils import timezone
from django.http import StreamingHttpResponse
from django.db import close_old_connections
from django.db.models import Q
import json, time
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.parsers import JSONParser


from .models import ChargePoint, Transaction, MeterValue, EventLog, FuzzJob, ControlCommand
from .serializers import (
    ChargePointSerializer, TransactionSummarySerializer,
    MeterValueSerializer, EventLogSerializer, FuzzJobSerializer, ControlCommandSerializer
)

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import ChargePoint
from .serializers import ChargePointSerializer


import json
from django.http import StreamingHttpResponse
from time import sleep
from core.models import EventLog
from django.utils.timezone import now

def fuzz_stream(request):
    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    return response


def event_stream():
    """Fuzzing 관련 로그만 실시간 전송"""
    last_id = None

    while True:
        logs = EventLog.objects.order_by('-id')

        if last_id:
            logs = logs.filter(id__gt=last_id)

        for log in logs:
            if log.action in (
                "FuzzApplied",
                "SchemaViolation",
                "TemporalViolation",
                "AnomalyDetected"
            ):
                data = {
                    "id": log.id,
                    "cp": log.cp.cp_id,
                    "action": log.action,
                    "direction": log.direction,
                    "payload": log.payload,
                    "timestamp": log.created_at.isoformat(),
                }
                yield f"event: fuzzylog\ndata: {json.dumps(data)}\n\n"
                last_id = log.id

        sleep(1)





@api_view(['GET'])
def cp_status(request, cp_id):
    cp = get_object_or_404(ChargePoint, cp_id=cp_id)
    return Response(ChargePointSerializer(cp).data)

# --------- ViewSets ---------
class ChargePointViewSet(viewsets.ModelViewSet):
    queryset = ChargePoint.objects.all().order_by('cp_id')
    serializer_class = ChargePointSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['cp_id']

    @action(detail=True, methods=['get'])
    def sessions(self, request, pk=None):
        cp = self.get_object()
        qs = cp.transactions.order_by('-started_at')[:200]
        return Response(TransactionSummarySerializer(qs, many=True).data)

    @action(detail=True, methods=['get'])
    def events(self, request, pk=None):
        cp = self.get_object()
        qs = cp.events.order_by('-created_at')[:500]
        return Response(EventLogSerializer(qs, many=True).data)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Transaction.objects.all().order_by('-started_at')
    serializer_class = TransactionSummarySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['cp__cp_id']


class MeterValueViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MeterValue.objects.all().order_by('-ts')
    serializer_class = MeterValueSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['cp__cp_id']


class EventLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EventLog.objects.all().order_by('-created_at')
    serializer_class = EventLogSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['cp__cp_id', 'action', 'direction']


class FuzzJobViewSet(viewsets.ModelViewSet):
    queryset = FuzzJob.objects.all().order_by('-started_at')
    serializer_class = FuzzJobSerializer

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        job = self.get_object()
        job.started_at = timezone.now()
        job.status = "running" 
        job.save()

        # 타깃 CP 목록을 프론트에서 보낼 수도 있고 기본 CP_9000 사용
        cp_id = request.data.get('cp_id') or "CP_9000"

        ControlCommand.objects.create(
            cp_id=cp_id,
            type='start_fuzz',
            payload={'fuzz_id': job.id, 'scenario': job.scenario},
            status='pending'
        )

        return Response({'status': 'started', 'job': FuzzJobSerializer(job).data})
   
    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        job = self.get_object()
        job.ended_at = timezone.now()
        job.status = "stopped" 
        job.save()
        return Response({'status': 'stopped', 'job': FuzzJobSerializer(job).data})


# ControlCommand 모델/serializer 이미 있으니 사용
class ControlCommandViewSet(viewsets.GenericViewSet,
                             mixins.ListModelMixin,
                             mixins.RetrieveModelMixin,
                             mixins.UpdateModelMixin):
    """
    GET /api/control/?cp_id=CP_9000&status=pending  -> CP가 폴링해서 pending 명령들을 가져감
    POST /api/control/{id}/complete/ -> CP가 처리 완료 보고
    """
    queryset = ControlCommand.objects.all().order_by('-created_at')
    serializer_class = ControlCommandSerializer
    permission_classes = [AllowAny]  # 테스트 환경: 인증 있으면 바꾸세요
    parser_classes = [JSONParser]
    filter_backends = [filters.SearchFilter]
    search_fields = ['cp_id', 'type', 'status']

    def get_queryset(self):
        qs = super().get_queryset()
        cp_id = self.request.GET.get('cp_id')
        status_q = self.request.GET.get('status')  # pending | done | processing
        if cp_id:
            qs = qs.filter(cp_id=cp_id)
        if status_q:
            qs = qs.filter(status=status_q)
        return qs

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """CP가 명령 처리 완료 시 호출"""
        cmd = self.get_object()
        cmd.status = 'done'
        cmd.result = request.data.get('result', '')
        cmd.save()
        return Response({'ok': True, 'id': cmd.id})

    @action(detail=True, methods=['post'])
    def take(self, request, pk=None):
        """
        CP가 명령을 '가져감' (race 방지용): 상태 -> processing
        사용법: CP는 처리를 시작하기 전에 take() 호출 -> 성공하면 처리
        """
        cmd = self.get_object()
        if cmd.status != 'pending':
            return Response({'ok': False, 'reason': 'not pending', 'status': cmd.status}, status=409)
        cmd.status = 'processing'
        cmd.taken_by = request.data.get('cp_id') or cmd.cp_id
        cmd.save()
        return Response({'ok': True, 'id': cmd.id})


# --------- 제어 명령 (웹 버튼 -> DB 큐 적재) ---------
@api_view(['POST'])
def control_command(request):
    """
    body 예:
    {
      "cp_id": "CP_9000",
      "type": "remote_start",   # remote_start | remote_stop | trigger_status ...
      "payload": {"id_tag":"1","connector_id":1}
    }
    """
    ser = ControlCommandSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data, status=status.HTTP_201_CREATED)


# --------- SSE: 실시간 이벤트 로그 ---------
def events_stream(request):
    """
    text/event-stream 으로 EventLog 스트리밍
    GET params: last_id, cp_id, action, direction
    """
    try:
        last_id = int(request.GET.get("last_id", 0))
    except Exception:
        last_id = 0
    cp_id     = request.GET.get("cp_id") or None
    action    = request.GET.get("action") or None
    direction = request.GET.get("direction") or None

    def gen():
        nonlocal last_id
        yield ": connected\n\n"  # keep-alive
        while True:
            close_old_connections()
            qs = EventLog.objects.all()
            if cp_id:     qs = qs.filter(cp__cp_id=cp_id)
            if action:    qs = qs.filter(action=action)
            if direction: qs = qs.filter(direction=direction)
            qs = qs.filter(id__gt=last_id).order_by("id")[:200]

            any_new = False
            for ev in qs:
                any_new = True
                data = {
                    "id": ev.id,
                    "cp_id": ev.cp.cp_id,
                    "direction": ev.direction,
                    "action": ev.action,
                    "created_at": ev.created_at.isoformat(),
                    "payload": ev.payload,
                }
                last_id = ev.id
                yield f"id: {ev.id}\n"
                yield "event: eventlog\n"
                yield "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"

            if not any_new:
                yield ": heartbeat\n\n"

            time.sleep(1)

    resp = StreamingHttpResponse(gen(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    resp["Access-Control-Allow-Origin"] = "*"
    return resp
