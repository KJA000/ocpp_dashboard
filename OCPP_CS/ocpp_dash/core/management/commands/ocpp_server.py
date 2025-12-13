from django.core.management.base import BaseCommand
import asyncio, websockets
from datetime import datetime, timedelta
from ocpp.v16 import ChargePoint as CpBase
from ocpp.v16 import call_result
from ocpp.routing import on
from ocpp.v16.enums import Action, RegistrationStatus
from core.models import ChargePoint, Transaction, MeterValue, EventLog, FuzzJob
from asgiref.sync import sync_to_async
from django.utils import timezone as dj_timezone
import json


# --------- 공통 유틸 ---------
from datetime import timezone as dt_timezone

ALLOWED_UNITS = {"W", "Wh", "kWh", "V", "A", "%", "Percent"}

def _detect_schema_issues(mv_dict):
    issues = []

    # 0) timestamp 검사
    ts = mv_dict.get("timestamp")
    if ts is None:
        issues.append({"code": "SCHEMA_NO_TIMESTAMP"})
    elif not isinstance(ts, str):
        issues.append({"code": "SCHEMA_TIMESTAMP_NOT_STRING"})

    # 1) sampledValue 키 존재 여부
    if "sampledValue" in mv_dict:
        sv = mv_dict["sampledValue"]
        key = "sampledValue"
    elif "sampled_value" in mv_dict:
        sv = mv_dict["sampled_value"]
        key = "sampled_value"
    else:
        issues.append({"code": "SCHEMA_SAMPLEDVALUE_KEY_MISSING"})
        return issues

    # 2) sampledValue는 리스트여야 함
    if not isinstance(sv, list):
        issues.append({
            "code": "SCHEMA_SAMPLEDVALUE_NOT_ARRAY",
            "actual_type": str(type(sv))
        })
        return issues

    # 3) empty array
    if len(sv) == 0:
        issues.append({"code": "SCHEMA_SAMPLEDVALUE_EMPTY"})
        return issues

    # 4) explode array detection
    if len(sv) > 50:
        issues.append({
            "code": "SCHEMA_SAMPLEDVALUE_EXPLODED",
            "size": len(sv)
        })

    # 5) 각 요소 검사
    for idx, item in enumerate(sv):
        if not isinstance(item, dict):
            issues.append({"code": "SCHEMA_SV_NOT_OBJECT", "index": idx})
            continue

        # value type 검사
        value = item.get("value")
        if isinstance(value, (dict, list, bool)):
            issues.append({
                "code": "SCHEMA_VALUE_TYPE_INVALID",
                "index": idx,
                "value_type": str(type(value))
            })

        # measurand 누락 또는 오타
        if "measurand" not in item:
            issues.append({"code": "SCHEMA_MISSING_MEASURAND", "index": idx})

        # unit 값 enum 검사
        unit = item.get("unit")
        if unit and unit not in ALLOWED_UNITS:
            issues.append({
                "code": "SCHEMA_UNIT_INVALID",
                "unit": unit,
                "index": idx
            })

    return issues


def _detect_temporal_issues(ts, last_ts, now=None, future_skew_min=5):
    issues = []

    if now is None:
        now = dj_timezone.now().astimezone(dt_timezone.utc)

    # 과거 역행
    if last_ts and ts < last_ts:
        issues.append({
            "code": "TEMP_NON_MONOTONIC",
            "previous": last_ts.isoformat(),
            "current": ts.isoformat()
        })

    # 미래 스큐
    if ts > now + timedelta(minutes=future_skew_min):
        issues.append({
            "code": "TEMP_FUTURE_SKEW",
            "current": ts.isoformat(),
            "now": now.isoformat()
        })

    return issues


def _detect_logic_consistency(mv_dict):
    issues = []
    sv_list = mv_dict.get("sampledValue") or mv_dict.get("sampled_value") or []

    # Import/Export 동시에?
    has_import = False
    has_export = False

    for sv in sv_list:
        meas = str(sv.get("measurand", "")).lower()
        if "power.active.import" in meas:
            has_import = True
        if "power.active.export" in meas:
            has_export = True

    if has_import and has_export:
        issues.append({"code": "CONSISTENCY_IMPORT_EXPORT"})

    # connectorId 불일치
    if mv_dict.get("connectorId") not in (None, 1):
        issues.append({
            "code": "CONSISTENCY_WRONG_CONNECTOR",
            "value": mv_dict.get("connectorId")
        })

    # transaction 재사용/중복
    if "transaction_id" in mv_dict and mv_dict["transaction_id"] not in (1, None):
        issues.append({
            "code": "CONSISTENCY_TRANSACTION_REUSE",
            "value": mv_dict["transaction_id"]
        })

    return issues



def _dt(s: str):
    """'2025-10-29T09:27:09Z' → aware UTC datetime"""
    try:
        dt = datetime.strptime((s or "").replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=dt_timezone.utc)
    except Exception:
        return dj_timezone.now()

def _brief(obj, limit=120):
    s = str(obj)
    return s if len(s) <= limit else s[:limit] + "...(+more)"

# --------- 퍼징 도우미 ---------
async def _get_running_fuzz():
    """실행 중인 가장 최근 FuzzJob 1개 조회"""
    def _q():
        return FuzzJob.objects.filter(status="running").order_by("-id").first()
    return await sync_to_async(_q)()

def _mutate_sampled_values_for_format_error(sv_list):
    """형식 오류: value를 숫자형으로(문자열 아님), measurand 누락 등 스키마 위반 유도"""
    out = []
    for i, sv in enumerate(sv_list):
        sv2 = dict(sv)
        if i == 0 and 'value' in sv2:
            # OCPP 1.6 스키마는 문자열을 기대 → 숫자로 바꿔서 위반 유도
            try:
                sv2['value'] = float(sv2['value'])
            except Exception:
                sv2['value'] = 123.45
        if i == 1 and 'measurand' in sv2:
            sv2.pop('measurand', None)  # 필수 필드 제거
        out.append(sv2)
    return out

def _mutate_sampled_values_for_logic_error(sv_list):
    """논리 오류: 물리/상식적으로 말 안 되는 값 주입"""
    out = []
    for sv in sv_list:
        sv2 = dict(sv)
        meas = str(sv2.get('measurand', '')).lower()
        if 'voltage' in meas:
            sv2['value'] = '800'        # 말도 안 되게 높은 전압
        elif 'current.import' in meas:
            sv2['value'] = '-5'         # 음수 전류
        elif 'power.active.import' in meas:
            sv2['value'] = '200000'     # 과도한 전력
        elif 'energy.active.import' in meas:
            sv2['value'] = '-1'         # 음수 에너지
        elif meas == 'soc':
            sv2['value'] = '120'        # 120% SoC
        out.append(sv2)
    return out

def _mutate_timestamp_for_timing(mv_dict):
    """타이밍 변조: 타임스탬프를 미래로 크게 이동"""
    try:
        ts = mv_dict.get("timestamp")
        base = _dt(ts)
        moved = base + timedelta(minutes=5)
        mv_dict["timestamp"] = moved.astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    except Exception:
        pass
    return mv_dict
def _fuzz_apply_mv(scenario, mv):
    """
    scenario: format_error / logic_error / timing_mutate / order_disrupt
    mv: MeterValuesPayload dict
    """

    before = json.dumps(mv)
    mv = json.loads(before)  # deep copy
    sv_list = mv.get("sampledValue") or mv.get("sampled_value") or []

    import random
    r = random.random()

    # ============================================================
    # 1) FORMAT / SCHEMA FUZZING  (  95% 확률로 오류)
    # ============================================================
    if scenario == "format_error":

        if r < 0.80:
            #   강한 스키마 붕괴 (80%)
            for sv in sv_list:
                sv["value"] = {"oops": True}
                sv["unit"] = "XW"
            mv["sampledValue"] = "NOT_ARRAY"

        elif r < 0.95:
            #   중간 강도 오류 (필드명 교란)
            if "sampledValue" in mv:
                mv["sampled value"] = mv.pop("sampledValue")
            for sv in sv_list:
                if "measurand" in sv:
                    sv["measurrand"] = sv.pop("measurand")
            for sv in sv_list:
                sv["unit"] = "INVALID"

        else:
            #   배열 경계값 (empty / 폭발)
            mode = random.choice(["empty", "explode"])
            if mode == "empty":
                mv["sampledValue"] = []
            else:
                mv["sampledValue"] = [sv_list[0]] * 300  # 300개 복제

    # ============================================================
    # 2) VALUE RANGE / PHYSICAL FUZZING (  70% 확률 오류)
    # ============================================================
    elif scenario == "logic_error":

        if r < 0.40:
            #   비현실적 전압/전류/전력 (40%)
            for sv in sv_list:
                meas = sv.get("measurand", "").lower()
                if "voltage" in meas:
                    sv["value"] = "99999"
                if "current" in meas:
                    sv["value"] = "-120"
                if "power" in meas:
                    sv["value"] = "300000"

        elif r < 0.70:
            #   상관성 붕괴 (Power != V*I)
            for sv in sv_list:
                meas = sv.get("measurand", "").lower()
                if "power" in meas:
                    sv["value"] = "5000"
                if "voltage" in meas:
                    sv["value"] = "210"
                if "current" in meas:
                    sv["value"] = "1.0"

        else:
            #   에너지 역행 (edge-case)
            for sv in sv_list:
                if "energy" in sv.get("measurand", "").lower():
                    sv["value"] = "0.001"

    # ============================================================
    # 3) TEMPORAL / ORDERING FUZZING 
    # ============================================================
    elif scenario == "timing_mutate":

        ts = mv.get("timestamp")
        try:
            dt = datetime.strptime(ts.replace("Z",""), "%Y-%m-%dT%H:%M:%S")
        except:
            dt = datetime.utcnow()

        if r < 0.30:
            dt -= timedelta(minutes=5)
            mv["timestamp"] = dt.isoformat() + "Z"

        elif r < 0.60:
            # 미래로 +10분
            dt += timedelta(minutes=10)
            mv["timestamp"] = dt.isoformat() + "Z"

        else:
            #   Burst (timestamp 반복)
            mv["burst"] = True

    # ============================================================
    # 4) LOGICAL CONSISTENCY FUZZING (  60% 확률 오류)
    # ============================================================
    elif scenario == "order_disrupt":

        if r < 0.30:
            #   Import + Export 동시 보고
            sv_list.append({
                "value": "100",
                "measurand": "Power.Active.Export",
                "unit": "W",
                "location": "Outlet",
                "context": "Sample.Periodic",
                "format": "Raw"
            })

        elif r < 0.60:
            #   connectorId 불일치
            mv["connectorId"] = 999

        else:
            #   transaction 재사용 / 중복
            mv["transaction_id"] = random.choice([1, 2, 3, 4, 99])

    return json.loads(before), mv


# --------- 이상치(Anomaly) 규칙 ---------
def _detect_anomalies(power, voltage, current, energy, soc):
    issues = []

    # 전압 범위
    if voltage is not None and not (10 <= voltage <= 500):
        issues.append({"code": "RANGE_VOLTAGE", "voltage": voltage})

    # 전류 범위
    if current is not None and not (0 <= current <= 300):
        issues.append({"code": "RANGE_CURRENT", "current": current})

    # 전력 범위
    if power is not None and not (0 <= power <= 200000):
        issues.append({"code": "RANGE_POWER", "power": power})

    # SoC
    if soc is not None and not (0 <= soc <= 100):
        issues.append({"code": "RANGE_SOC", "soc": soc})

    # 일관성 검사 |P - V*I|
    if voltage and current and power:
        ref = voltage * current
        err = abs(power - ref) / (ref + 1e-6)
        if err > 1.0:
            issues.append({
                "code": "CONSISTENCY_P_VI",
                "power": power,
                "voltage": voltage,
                "current": current,
                "relative_error": round(err, 3)
            })

    return issues


# =====================================================================================

class DjangoChargePoint(CpBase):
    """CSMS측 OCPP 핸들러: Django ORM + 퍼징/이상치 검출 포함"""

    def __init__(self, cp_id, connection):
        super().__init__(cp_id, connection)
        self.cp_id = cp_id
        self.cp_obj = None

        self._last_mv_ts = {}

    async def init_cp(self):
        self.cp_obj, _ = await sync_to_async(ChargePoint.objects.get_or_create)(cp_id=self.cp_id)

    async def _log_in(self, action: str, payload: dict, unique_id: str = None):
        await sync_to_async(EventLog.objects.create)(
            cp=self.cp_obj, direction='IN', action=action, payload=payload, unique_id=unique_id
        )

    async def _log_out(self, action: str, payload: dict, unique_id: str = None):
        await sync_to_async(EventLog.objects.create)(
            cp=self.cp_obj, direction='OUT', action=action, payload=payload, unique_id=unique_id
        )

    # ---------------- Handlers ----------------

    @on(Action.BootNotification)
    async def on_boot(self, charge_point_vendor, charge_point_model, **kwargs):
        await self._log_in('BootNotification', kwargs)
        self.cp_obj.vendor = charge_point_vendor
        self.cp_obj.model = charge_point_model
        self.cp_obj.status = 'Available'
        self.cp_obj.last_seen = dj_timezone.now()
        await sync_to_async(self.cp_obj.save)()

        payload = {
            'current_time': dj_timezone.now().astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
            'interval': 10,
            'status': RegistrationStatus.accepted.value
        }
        await self._log_out('BootNotification', payload)
        return call_result.BootNotification(**payload)

    @on(Action.Authorize)
    async def on_authorize(self, id_tag):
        await self._log_in('Authorize', {'id_tag': id_tag})
        status = 'Accepted' if id_tag == '1' else 'Invalid'
        payload = {
            'id_tag_info': {
                'expiry_date': dj_timezone.now().astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
                'status': status
            }
        }
        await self._log_out('Authorize', payload)
        return call_result.Authorize(**payload)

    @on(Action.StartTransaction)
    async def on_start_tx(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        await self._log_in('StartTransaction', {"connector_id": connector_id, "id_tag": id_tag, "meter_start": meter_start, "timestamp": timestamp})

        # 순서 교란 검출 예시 (Authorize 없이 StartTransaction이 들어온 경우)
        # 실제로는 최근 Authorize 수신 여부 상태를 저장/조회하는 로직을 추가해도 됨.
        # 여기서는 간단히 id_tag != '1' 인 경우를 SequenceViolation으로 기록.
        if id_tag != '1':
            await self._log_in("SequenceViolation", {
                "reason": "StartTransaction without valid Authorize",
                "id_tag": id_tag
            })

        tx_id = 1  # 데모: 고정
        ts = _dt(timestamp)
        await sync_to_async(Transaction.objects.create)(
            cp=self.cp_obj, connector_id=connector_id, transaction_id=tx_id,
            started_at=ts, meter_start=meter_start
        )
        payload = {
            'transaction_id': tx_id,
            'id_tag_info': {'status': 'Accepted'}
        }
        await self._log_out('StartTransaction', payload)
        return call_result.StartTransaction(**payload)

    @on(Action.StopTransaction)
    async def on_stop_tx(self, transaction_id, meter_stop, timestamp, **kwargs):
        await self._log_in('StopTransaction', {"transaction_id": transaction_id, "meter_stop": meter_stop, "timestamp": timestamp})
        ts = _dt(timestamp)
        try:
            tx = await sync_to_async(Transaction.objects.get)(cp=self.cp_obj, transaction_id=transaction_id)
            tx.stopped_at = ts
            tx.meter_stop = meter_stop
            if tx.meter_start is not None and meter_stop is not None:
                tx.energy_Wh = float(meter_stop - tx.meter_start)
            await sync_to_async(tx.save)()
        except Transaction.DoesNotExist:
            # 순서 교란: StartTransaction 없이 Stop이 들어온 경우
            await self._log_in("SequenceViolation", {
                "reason": "StopTransaction without StartTransaction",
                "transaction_id": transaction_id
            })

        payload = {'id_tag_info': {'status': 'Accepted'}}
        await self._log_out('StopTransaction', payload)
        return call_result.StopTransaction(**payload)

    @on(Action.MeterValues)
    async def on_meter_values(self, connector_id: int, meter_value: list, transaction_id: int = None, **kwargs):
        """MeterValues 수신 → 퍼징 적용(있다면) → 이상치 검사 → DB 저장"""
        

        
        await self._log_in('MeterValues', {
            'connector_id': connector_id,
            'transaction_id': transaction_id,
            'meter_value': meter_value,
        })

        print(f"[MV] batch size: {len(meter_value)}")

        # 1) 실행 중인 퍼징 잡 확인
        job = await _get_running_fuzz()
        scenario = job.scenario if job else None

        print(f"[FUZZCHK] running={bool(job)} scenario={scenario}")


        for mv in meter_value:
            
            schema_issues = _detect_schema_issues(mv)
            if schema_issues:
                await self._log_in("SchemaViolation", {
                    "cp_id": self.cp_obj.cp_id,
                    "connector_id": connector_id,
                    "transaction_id": transaction_id,
                    "issues": schema_issues,
                    "raw": mv,
                })
                print(f"[SCHEMA] {schema_issues}")


            # 퍼징 적용 (format_error / logic_error / timing_mutate)
            if scenario in ("format_error", "logic_error", "timing_mutate"):
                before, after = _fuzz_apply_mv(scenario, mv)
                await self._log_in("FuzzApplied", {
                    "cp_id": self.cp_obj.cp_id,
                    "scenario": scenario,
                    "connector_id": connector_id,
                    "transaction_id": transaction_id,
                    "before": before,
                    "after": after,
                })
                print(f"[FUZZ] scenario={scenario} applied. before={_brief(before)} after={_brief(after)}")

            # timestamp 파싱 (aware)
            ts_str = mv.get("timestamp")
            try:
                ts = datetime.strptime(ts_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt_timezone.utc)
            except Exception:
                ts = dj_timezone.now().astimezone(dt_timezone.utc)


            key = (connector_id, transaction_id or 0)
            last_ts = self._last_mv_ts.get(key)
            temp_issues = _detect_temporal_issues(ts, last_ts)
            if temp_issues:
                await self._log_in("TemporalViolation", {
                    "cp_id": self.cp_obj.cp_id,
                    "connector_id": connector_id,
                    "transaction_id": transaction_id,
                    "issues": temp_issues,
                    "timestamp": ts_str,
                })
                print(f"[TEMP] {temp_issues}")
            self._last_mv_ts[key] = ts


            # sampledValue / sampled_value 모두 대응
            sv_list = mv.get("sampled_value", mv.get("sampledValue", []))
            if sv_list:
                print("[MV] first sv keys:", list(sv_list[0].keys()))

            power = energy = current = voltage = soc = None

            for sv in sv_list:
                meas = str(sv.get("measurand", "")).strip().lower()
                val_raw = sv.get("value", None)
                try:
                    val = float(str(val_raw).strip())
                except (TypeError, ValueError):
                    continue

                if "power.active.import" in meas:
                    power = val
                elif "energy.active.import.register" in meas or "energy.active.import" in meas:
                    energy = val
                elif "current.import" in meas:
                    current = val
                elif "voltage" in meas:
                    voltage = val
                elif meas == "soc":
                    soc = val

            # 2) 이상치 규칙 검사
            value_issues = _detect_anomalies(power, voltage, current, energy, soc)

            # 5-2) Import/Export 동시 보고 등 논리 일관성
            logic_issues = _detect_logic_consistency(mv)

            all_issues = value_issues + logic_issues
            if all_issues:
                await self._log_in("AnomalyDetected", {
                    "cp_id": self.cp_obj.cp_id,
                    "connector_id": connector_id,
                    "transaction_id": transaction_id,
                    "issues": all_issues,
                    "values": {
                        "power_W": power,
                        "voltage_V": voltage,
                        "current_A": current,
                        "energy_Wh": energy,
                        "soc_percent": soc
                    },
                    "timestamp": ts_str,
                    "scenario": scenario,
                })
                print(f"[ANOMALY] {all_issues} at {ts_str}")

            # 6) DB 저장 (MeterValue)
            await sync_to_async(MeterValue.objects.create)(
                cp=self.cp_obj,
                ts=ts,
                power_W=power,
                energy_Wh=energy,
                current_A=current,
                voltage_V=voltage,
                soc_percent=soc,
                raw={
                    "connector_id": connector_id,
                    "transaction_id": transaction_id,
                    "meter_value": mv,   # 변조 후 최종 저장
                },
            )

        # 1.6은 빈 페이로드
        return call_result.MeterValuesPayload()

    @on(Action.Heartbeat)
    async def on_heartbeat(self, **kwargs):
        await self._log_in('Heartbeat', kwargs)
        # 상태 갱신
        self.cp_obj.last_seen = dj_timezone.now()
        await sync_to_async(self.cp_obj.save)()
        payload = {'current_time': dj_timezone.now().astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'}
        await self._log_out('Heartbeat', payload)
        return call_result.Heartbeat(**payload)

    @on(Action.StatusNotification)
    async def on_status_notification(self, connector_id, error_code, status):
        await self._log_in('StatusNotification', {
            'connector_id': connector_id, 'status': status, 'error_code': error_code
        })
        # 상태/라스트씬 갱신
        self.cp_obj.status = status
        self.cp_obj.last_seen = dj_timezone.now()
        await sync_to_async(self.cp_obj.save)()
        return call_result.StatusNotification()

# =====================================================================================

class Command(BaseCommand):
    help = "Run OCPP 1.6 WebSocket server on port 9000 (CSMS within Django)."

    def handle(self, *args, **options):
        async def on_connect(ws, path):
            cp_id = path.strip('/')
            cp = DjangoChargePoint(cp_id, ws)
            await cp.init_cp()
            await cp.start()

        async def main():
            server = await websockets.serve(on_connect, '0.0.0.0', 9000, subprotocols=['ocpp1.6'])
            print("OCPP WS Server started on :9000")
            await server.wait_closed()

        asyncio.run(main())
