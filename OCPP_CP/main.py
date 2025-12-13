import asyncio
import logging
from multiprocessing.dummy import active_children
from pkgutil import iter_modules
from urllib.request import Request
import tkinter as tk
from threading import Thread
import FSM

import websockets
import CP
logging.getLogger("ocpp").setLevel(logging.DEBUG)
# logging.getLogger("asyncio").setLevel(logging.DEBUG)
# logging.getLogger("websockets").setLevel(logging.DEBUG)
logging.basicConfig(level=logging.INFO)
import sys
from functools import wraps

fsm = FSM.ChargingStationFSM()

mv_task = None

async def cp_action(input_value, cp):
    # Handle each command based on the input_value
    if input_value == 'VALID_ID_TAG':
        await cp.authorize_request(1)  # Example ID for valid tag authorization
    elif input_value == 'INVALID_ID_TAG':
        await cp.authorize_request(2)  # Example ID for invalid tag

    elif input_value == 'INSERT_PLUG':
        if fsm.state == 'Available':
            await cp.status_notification_request('Preparing')  # Placeholder for the plug insertion action
            fsm.handle_event('A2')
        else:
            print('이미 충전기 연결됨')
    elif input_value == 'REMOVE_PLUG':
        if fsm.state == 'Preparing':
            cp.Charging = False
            fsm.handle_event('B1')
            await cp.status_notification_request('Available')
        
        elif fsm.state == 'Finishing':
            cp.Charging = False
            fsm.handle_event('F1')
            await cp.status_notification_request('Available')
        else:
            print('충전기 제거 불가')

    elif input_value == 'CHARGING':
        if cp.is_authorized == True and fsm.state == 'Preparing':
            global mv_task
            # ✅ 새 MeterValues 루프 시

            await cp.start_transaction_request(1, 1)  # 충전 시작
            await cp.status_notification_request('Charging')  # 충전소 상태 충전중
            fsm.handle_event('B3')  # Transition to 'Charging' state

            cp.Charging = True
            if mv_task is None or mv_task.done():
                mv_task = asyncio.create_task(cp.send_meter_values())
                print("[CP] MeterValues loop started.")
            else:
                print("[CP] MeterValues loop already running.")
                
        else:
            print('인증이 안됨.')
    elif input_value == 'STOPCHARGING':
        if fsm.state == 'Charging':
            cp.Charging = False
            await cp.stop_transaction_request(1, 1)  # Stop charging
            await cp.status_notification_request('Finishing')  # Notify Finishing status
            fsm.handle_event('C6')  # Transition to 'Finishing' state
        else:
            print('충전 중이 아님')
    # TODO: 예외 처리 / 다른 상태 처리 / 타임아웃 필요
    elif input_value == 'SEND_METER_VALUES':
        # 새로 추가한 MeterValuesPayload 전송 명령
        await cp.send_meter_periodic_data()
        print("MeterValuesPayload 전송 완료.")

    else:
        print(f"Unknown command received: {input_value}")


async def handle_user_input(input_queue, cp):
    while True:
        # Wait for a command from the GUI
        input_value = await input_queue.get()
        await cp_action(input_value, cp)


def open_gui(input_queue, loop):
    # Tkinter GUI setup
    root = tk.Tk()
    root.title("CP: User Input")
    root.geometry("300x200")

    def send_command(command):
        # Use the provided loop to schedule the coroutine
        asyncio.run_coroutine_threadsafe(input_queue.put(command), loop)

    def update_status():
        # fsm의 현재 상태를 status_label에 표시
        status_label.config(text=f"Current Status: {fsm.state}")
        # 일정 간격으로 상태를 업데이트 (예: 1초)
        root.after(1000, update_status)

    # Create buttons for each command
    status_label = tk.Label(root, text="Current Status: Unknown", font=("Arial", 12))

    tk.Label(root, text="Select a user behavior:").pack(pady=10)

    tk.Button(root, text="Id Tag (Valid)", command=lambda: send_command("VALID_ID_TAG")).pack(pady=5)
    tk.Button(root, text="Id Tag (Invalid)", command=lambda: send_command("INVALID_ID_TAG")).pack(pady=5)
    tk.Button(root, text="Insert Plug", command=lambda: send_command("INSERT_PLUG")).pack(pady=5)
    tk.Button(root, text="Remove_Plug", command=lambda: send_command("REMOVE_PLUG")).pack(pady=5)
    tk.Button(root, text="Charging", command=lambda: send_command("CHARGING")).pack(pady=5)
    tk.Button(root, text="Stop Charging", command=lambda: send_command("STOPCHARGING")).pack(pady=5)
    tk.Button(root, text="Send MeterValues", command=lambda: send_command("SEND_METER_VALUES")).pack(pady=5)
    status_label.pack(pady=20)
    update_status()

    root.mainloop()


async def main():
    async with websockets.connect('ws://localhost:9000/CP_9000', subprotocols=['ocpp1.6']) as ws:
        cp = CP.ChargePoint('CP_9000', ws)

        # Start a GUI thread and set up the communication queue
        input_queue = asyncio.Queue()
        loop = asyncio.get_running_loop()  # Get the current event loop
        Thread(target=open_gui, args=(input_queue, loop), daemon=True).start()

        # Start asynchronous tasks for the ChargePoint
        await asyncio.gather(
            cp.start(),
            cp.send_boot_notification(),
            handle_user_input(input_queue, cp)
        )


if __name__ == '__main__':
    asyncio.run(main())
