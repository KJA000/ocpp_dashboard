#from ocpp.routing import on, after
import asyncio
#from datetime import datetime
#import urllib
#import requests
from datetime import datetime, timedelta, timezone
#import time
from ocpp.routing import on, after
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from functools import wraps
import json
import random
import random
from datetime import datetime

import ocpp.messages as messages
from ocpp.v16.enums import (
    Action,
    RegistrationStatus,
    AvailabilityType,
    ResetType,
    AvailabilityStatus,
    ConfigurationStatus,
    ClearCacheStatus,
    DataTransferStatus,
    RemoteStartStopStatus,
    ResetStatus,
    ChargePointStatus,
    ChargePointErrorCode,
    UnlockStatus,
    Reason)

with open('Config.json', "r") as file:
    config = json.load(file)


def pause_heartbeat(delay):
    """ 다른 페이로드 처리 함수에 사용하여 Heartbeat를 일시 중지하는 데코레이터 """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Heartbeat 일시 중지
            self.heartbeat_enabled = False
            print("정지.")

            # 원래 함수 실행
            await func(self, *args, **kwargs)

            # 일정 시간 대기 후 Heartbeat 전송 재개를 비동기적으로 처리
            print(f"Waiting {delay} seconds before resuming Heartbeat.")
            asyncio.create_task(self.resume_heartbeat(delay))

        return wrapper
    return decorator


# 충전기 팔 하나
class ChargePoint(cp):
    def __init__(self, id, connection):
        """Init extra variables for testing."""
        super().__init__(id, connection)
        self.request_id: int = 0
        self.accept: bool = True
        self.reboot: bool = False
        self.display_message: str = ""
        self.messages: list = []
        self.getMessages: list = []
        self.url_firmware: str = ""
        self.supported_keys = ['MaxPower', 'MinPower', 'ConnectionTimeout']
        self.configuration_settings = {
            'MaxPower': {'need_reboot': True, 'possible': False},
            'MinPower': {'need_reboot': False, 'possible': True},
            'ConnectionTimeout': {'need_reboot': False, 'possible': False},
        }

        self.heartbeat_task = None
        self.is_authorized = False
        self.heartbeat_enabled = True

        self.soc_percent = round(random.uniform(20.0, 80.0), 2)
        # SoC 변화율(퍼센트/샘플) - 충전 시 증가 (랜덤 범위)
        self._soc_delta_range = (0.05, 0.25)  # 예: 각 전송마다 0.05% ~ 0.25% 증가

        self.Charging = False  # Boolean to manage charging state
        self.config_interval = config.get("interval", 10)


######################새로 추가
    async def send_meter_values(self):
        """Charging 동안 주기적으로 MeterValues 전송"""
        while self.Charging:
            mv = self.generate_meter_value()
            req = call.MeterValuesPayload(
                connector_id=1,
                transaction_id=1,          # 데모 고정 (실제는 StartTransaction 응답 txId 사용)
                meter_value=[mv]
            )
            await self.call(req)
            await asyncio.sleep(self.config_interval)

  # Transmit based on interval

    def generate_meter_value(self):
        """OCPP 1.6 유효 스키마에 맞춘 측정값 생성"""
        now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
        
        # 예시용 랜덤 값
        power_w   = round(random.uniform(1200, 2500), 1)        # W
        voltage_v = round(random.uniform(215, 235), 1)          # V
        current_a = round(power_w / max(voltage_v, 1), 2)       # A
        energy_wh = round(random.uniform(0.1, 0.5), 3)          # Wh
        soc_str = str(round(self.soc_percent, 3))
        return {
            "timestamp": now,
            "sampledValue": [
                {
                    "value": str(power_w),                      # ✅ 문자열
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Power.Active.Import",         # ✅ enum
                    "location": "Outlet",
                    "unit": "W",                                 # ✅ 단위
                    
                },
                {
                    "value": str(voltage_v),
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Voltage",
                    "location": "Outlet",
                    "unit": "V"
                },
                {
                    "value": str(current_a),
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Current.Import",
                    "location": "Outlet",
                    "unit": "A"
                },
                {
                    "value": str(energy_wh),
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "Outlet",
                    "unit": "Wh"
                },
                {
                    "value": soc_str,
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "SoC",
                    "location": "Outlet",
                    "unit": "Percent"
                },
            ]
        }

    async def cp_action(self, action):
        """ Control Charging state based on action input """
        if action == 'CHARGING':
            self.Charging = True
            print("Charging started.")
            asyncio.create_task(self.send_meter_values())  # Start sending meter values
        elif action == 'STOPCHARGING':
            self.Charging = False
            print("Charging stopped.")
            # Additional logic to send final meter values, if needed


    async def send_heartbeat(self, interval):
        request = call.HeartbeatPayload()
        while True:
            if self.heartbeat_enabled:
                await self.call(request)
                print("Heartbeat sent.")
            else:
                print("Heartbeat paused due to other payload exchange.")
            await asyncio.sleep(interval) #TODO: 인터벌 변경 함수

    async def resume_heartbeat(self, delay):
        """ Heartbeat 재개를 위한 비동기 작업 """
        await asyncio.sleep(delay)
        self.heartbeat_enabled = True
        print("Heartbeat resumed.")

    async def send_boot_notification(self):
        request = call.BootNotificationPayload(
            charge_point_model='Dummy_Model',
            charge_point_vendor='KHU'
        )
        response = await self.call(request)

        if response.status == 'Accepted':
            print("Connected to central system.")
            #    await self.send_meter_periodic_data()

            await self.send_heartbeat(response.interval) #TODO: 인터벌 변경 함수 

    async def send_meter_periodic_data(self):
        request = call.MeterValuesPayload(
            connector_id=1,
            transaction_id=0,
            meter_value=
            [{
                "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
                "sampledValue":
                    [{
                        "value": 50.10,
                        "context": 'Sample.Periodic',
                        "format": 'a',
                        "measurand": 'b',
                        "phase": 'c',
                        "location": 'loc',
                        "unit": 'w'
                    }]
            }]
        )

        while True:
            await self.call(request)
            await asyncio.sleep(10)# 인터벌 값

    @pause_heartbeat(10)  # 10초 동안 Heartbeat 중지
    async def authorize_request(self, my_id_tag):

        request = call.AuthorizePayload(
            id_tag=str(my_id_tag)
        )
        response = await self.call(request)
        if response.id_tag_info.get('status') == 'Accepted':
            self.is_authorized = True
        else:
            self.is_authorized = False
        # 암 여러개인 경우 ?

    @on(Action.ChangeAvailability)
    async def on_change_availability(self, **kwargs):

        return call_result.ChangeAvailabilityPayload(
            status=AvailabilityStatus('Accepted')
        )

    @on(Action.ChangeConfiguration)
    async def on_change_configuration(self, *args, **kwargs):
        '''
        - 변경 사항이 성공적으로 적용되고 변경 사항이 즉시 적용되는 경우, 충전 포인트는 다음과 같이 응답합니다. 상태가 '수락됨'으로 응답합니다.
        - 변경 사항이 성공적으로 적용되었지만 적용하려면 재부팅이 필요한 경우, 충전 포인트는 다음과 같이 응답합니다. '재부팅 필요' 상태로 응답합니다.
        - '키'가 차지 포인트에서 지원하는 구성 설정에 해당하지 않는 경우, 차지 포인트는 '지원되지 않음' 상태를 반환합니다.
        - 충전 포인트가 구성을 설정하지 않았고 이전 상태 중 어느 것도 적용되지 않는 경우, Charge 포인트는 '거부됨' 상태로 응답합니다.
        '''
        key = kwargs['key']
        value = kwargs['value']
        status = await self.check_configuration_key_status(key)
        if status == 'Accepted':
            print()
        elif status == 'RebootRequired':
            print()
        return call_result.ChangeConfigurationPayload(
            status=ConfigurationStatus(status)
        )

    async def check_configuration_key_status(self, key):
        if key in self.configuration_settings:
            need_reboot = self.configuration_settings[key].get('need_reboot', False)
            possible = self.configuration_settings[key].get('possible', False)
        else:
            return 'NotSupported'

        if possible:
            if need_reboot:
                return 'RebootRequired'  # 리부팅 필요
            else:
                return 'Accepted'  # 즉시 적용
        else:
            return 'Rejected'  # 설정 거부

    @on(Action.ClearCache)
    async def on_clearcache(self, *args, **kwargs):

        return call_result.ClearCachePayload(
            status=ClearCacheStatus('Accepted')
        )

    @on(Action.DataTransfer)
    async def on_data_transfer(self, vendor_id, message_id, data):
        return call_result.DataTransferPayload(
            status=DataTransferStatus('A'),
            data='Accepted'
        )

    @on(Action.GetConfiguration)
    async def on_get_configuration(self, *args, **kwargs):
        return call_result.GetConfigurationPayload(
            configuration_key=config["configuration"]
        )



    @on(Action.RemoteStartTransaction)
    async def on_remote_start_transaction(self, *args, **kwargs):

        return call_result.RemoteStartTransactionPayload(
            status=RemoteStartStopStatus('Accepted')
        )

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop_transaction(self, transaction_id):

        return call_result.RemoteStopTransactionPayload(
            status=RemoteStartStopStatus('Accepted')
        )

    @on(Action.Reset)
    async def on_reset(self, *args, **kwargs):

        await asyncio.sleep(2)

        return call_result.ResetPayload(
            status=ResetStatus('Accepted')
        )

    @pause_heartbeat(10)
    async def start_transaction_request(self, my_connector_id, my_id_tag):

        request = call.StartTransactionPayload(
            connector_id=my_connector_id,
            id_tag=str(my_id_tag),
            meter_start=0,
            timestamp=datetime.now().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
        )

        response = await self.call(request)

    @pause_heartbeat(10)
    async def status_notification_request(self, my_status):
        request = call.StatusNotificationPayload(
            connector_id=1,
            status=ChargePointStatus(my_status),
            error_code=ChargePointErrorCode('NoError')
        )

        response = await self.call(request)

    @pause_heartbeat(10)
    async def stop_transaction_request(self, stop, now_id):

        request = call.StopTransactionPayload(
            meter_stop=100,
            timestamp=datetime.now().strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
            transaction_id=1,
            reason=Reason('Local')
        )

        response = await self.call(request)

    @on(Action.UnlockConnector)
    async def unlock_connector(self, connector_id):

        return call_result.UnlockConnectorPayload(
            status=UnlockStatus('a')
        )
