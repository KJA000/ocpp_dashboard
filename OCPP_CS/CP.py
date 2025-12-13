import asyncio
from asyncio.base_subprocess import WriteSubprocessPipeProto
from dataclasses import dataclass
import logging
from sqlite3 import connect
import websockets
from datetime import datetime, timedelta, timezone
import time
from ocpp.routing import on, after
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
import ocpp.messages as messages
from ocpp.v16.enums import (
    Action,
    RegistrationStatus,
    AvailabilityType,
    ResetType)

from logger import _LOGGER
#import ocpp.v16.datatypes.List


class ChargePoint(cp):
    def __init__(self, id, connection):
        super().__init__(id, connection)
        self.status: str = "OK"
        self.request_id: int = 0
        self.firmware_status: str = "Idle"
        self.request_id = 0

    async def post_connect(self, **kwargs):
        self.status = "OK"


    @on(Action.Authorize)
    async def on_authorize(self, id_tag):
        #TODO id tag 확인 하는 함수 구현
        #DB 구현 필요
        if id_tag == '1':
            sta = 'Accepted'
        else:
            sta = 'Invalid'
        return call_result.AuthorizePayload(
            {'expiryDate': datetime.now().strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
             'status': sta
             }
        )

    @on(Action.BootNotification)
    async def on_boot_notification(self, **kwargs):
        return call_result.BootNotificationPayload(
            current_time=datetime.utcnow().isoformat(), #
            interval=10, # Accepted 외의 상태를 전송시 boot noti를 알리기 까지의 대기 간격 이 기간 동안에는 연결 X
                         # 통신 채널을 닫거나 통신 하드웨어를 통신 하드웨어를 종료하는 상황
                         # 거부된 동안 충전소는 중앙과 시스템은 메시지를 응답하거나 보내면 안 됨
                         # pending state 주의
                         # 부트 승인전의 트랜젝션
            status=RegistrationStatus('Accepted')
        )

    async def change_availability_request(self, my_val):
        print(my_val)
        if my_val not in ['Inoperative', 'Operative']:
            print('err')
            return

        request = call.ChangeAvailabilityPayload(
            connector_id=1,
            type=AvailabilityType(my_val)
        )
        response = await self.call(request)
        #TODO response 처리 함수

    async def change_configuration_request(self, key, value):
        request = call.ChangeConfigurationPayload(
            key=key,
            value=value
        )
        response = await self.call(request)
        print(key + ':' + response)


    @on(Action.Heartbeat)
    async def on_heartbeat(self):
        # 연결 상태 알리기 위함
        # 시간은 내부 클럭 동기화를 위함
        # 인터벌 동안 다른 메시지로 대체 가능
        print('Got a Heartbeat!')
        return call_result.HeartbeatPayload(
            current_time=datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + "Z"
        )

    async def clear_cache_request(self):
        request = call.ClearCachePayload()
        response = await self.call(request)
        #TODO response 처리 함수

    async def data_transfer_request(self):
        request = call.DataTransferPayload(
            vendor_id='ID',
            message_id='MSG_ID',
            data='Dummy Data'
        )
        response = await self.call(request)
        #TODO response 처리 함수

    async def get_configuration_request(self):
        request = call.GetConfigurationPayload(
            key=[]
        )

        response = await self.call(request)
        #TODO response 처리 함수

    @on(Action.MeterValues)
    def on_meter_values(self, evse_id: int, meter_value: dict, **kwargs):
        # 개량값을 보고값 전송 시간은 CP에서 결정
        # ChangeConfiguration에서 설정
        return call_result.MeterValuesPayload()
        #TODO CP 구현에서 확인 필요

    async def remote_start_transaction_request(self):
        request = call.RemoteStartTransactionPayload(
            id_tag="id_tag_S_0511",

        )
        response = await self.call(request)
        #TODO response 처리 함수

    async def remote_stop_transaction_request(self):
        request = call.RemoteStopTransactionPayload(
            transaction_id=1
        )

        response = await self.call(request)
        #TODO response 처리 함수

    async def reset_request(self):
        request = call.ResetPayload(
            type=ResetType('soft')
        )

        response = await self.call(request)
        #TODO response 처리 함수

    @on(Action.StartTransaction)
    def on_start_transaction(self, **kwargs):
        #이 트랙젝션이 예약을 종료하는 경우(RESERVE NOW 참조), StartTransaction.req에는 예약Id가 포함되어야 함
        return call_result.StartTransactionPayload(
            transaction_id=1,
            id_tag_info={'status':'Accepted'}
        )#트랜잭션 ID와 승인 상태 값이 포함
        # 식별자가 오래된 정보를 사용하여 충전 포인트에서 로컬로 승인되었을 수 있으므로
        # 중앙 시스템은 StartTransaction.req PDU에서 식별자의 유효성을 확인

    @on(Action.StatusNotification)
    def on_status_notification(self, connector_id, error_code, status):

        return call_result.StatusNotificationPayload()
    # Preparing, Charging, SuspendedEV, SuspendedEVSE and Finishing

    @on(Action.StopTransaction)
    def on_stop_transaction(self, *args, **kwargs):
        #TODO
        return call_result.StopTransactionPayload(
            {
                'expiryDate': datetime.now().strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
                'parentIdTag': '1',
                'status': 'Accepted'
            }
        )
    # 트랙잭션 사용량에 대한 자세한 정보를 제공하는 선택적 TransactionData가 
    # #StopTransaction.req PDU에 포함될 수 있음
    # meterValue 요소와 동일한 데이터 구조를 사용하는 임의의 수의 MeterValue를 위한 컨테이너입니다(MeterValues 섹션 참조).
    # 중앙 시스템은 거래가 중지되는 것을 막을 수 없
    # 거래를 중지하는 데 사용된 idTag에 대한 정보를 보낼 수 있을 뿐 CACHE 업데이트를 사용
    # 충전 포인트 자체에서 거래를 중지해야 하는 경우 요청 PDU의 id태그가 생략
    # 거래가 정상적으로 종료된 경우(예: 전기차 운전자가 신분증을 제시하여 거래를 중지한 경우) Reason 요소는 생략할 수 있으며 Reason은 '로컬'로 가정
    # 정상적으로 종료되지 않은 경우 Reason을 올바른 값으로 설정
    # 정상적인 거래 종료의 일부로, 충전 포인트는 케이블을 잠금 해제해야 합니다(영구적으로 연결되지 않은 경우).
    # Unlock Connector 참조

    async def unlock_connector_request(self):
        request = call.UnlockConnectorPayload(
            connector_id=1)

        response = await self.call(request)


    async def start(self):
        """Start charge point."""
        await self.run([super().start(), self.post_connect()])

    async def run(self, tasks):
        """Run a specified list of tasks."""
        self.tasks = [asyncio.ensure_future(task) for task in tasks]
        try:
            await asyncio.gather(*self.tasks)
        except asyncio.TimeoutError:
            pass
        except websockets.exceptions.WebSocketException as websocket_exception:
            _LOGGER.debug(f"Connection closed to '{self.id}': {websocket_exception}")
        except Exception as other_exception:
            _LOGGER.error(
                f"Unexpected exception in connection to '{self.id}': '{other_exception}'",
                exc_info=True,
            )
        finally:
            await self.stop()

    async def stop(self):
        """Close connection and cancel ongoing tasks."""
        self.status = "Unavailable"
        if self._connection.open:
            _LOGGER.debug(f"Closing websocket to '{self.id}'")
            await self._connection.close()
        for task in self.tasks:
            task.cancel()

    async def reconnect(self, connection):
        _LOGGER.debug(f"Reconnect websocket to {self.id}")
        await self.stop()
        self.status = "OK"
        self._connection = connection
        if self.status == "OK":
            await self.run([super().start()])
        else:
            await self.run([super().start(), self.post_connect()])

    @on(Action.SecurityEventNotification)
    async def on_security_event(self, **kwargs):
        return call_result.SecurityEventNotificationPayload()