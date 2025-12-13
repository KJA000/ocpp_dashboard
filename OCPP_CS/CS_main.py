import asyncio
from asyncio.base_subprocess import WriteSubprocessPipeProto
from dataclasses import dataclass
from sqlite3 import connect
import websockets
from datetime import datetime, timedelta, timezone
import time
import CS
import aioconsole
from logger import _LOGGER  # logger
import tkinter as tk
from tkinter import ttk
# GUI 생성
from tkinter import simpledialog  # 입력 대화 상자
from threading import Thread
import queue
input_queue = queue.Queue()

cp_id = []
charge_points = {}


def open_gui():
    # Tkinter GUI setup
    root = tk.Tk()
    root.title("CSMS: User Input")
    root.geometry("300x200")

    def send_command(command, *args):
        # 인자와 함께 command 전송
        input_queue.put((command, *args))


    tk.Label(root, text="Select a CS behavior:").pack(pady=10)
    set_config_var = tk.StringVar()
    tk.Button(root, text="Get Config", command=lambda: send_command("GET_CONFIG")).pack(pady=5)
    # 드롭다운 메뉴 생성 (Set Config 용 옵션)
    tk.Label(root, text="Set Config Options:").pack(pady=10)
    set_config_var = tk.StringVar()
    set_config_options = ["Option A", "Option B", "Option C"]
    set_config_dropdown = ttk.Combobox(root, textvariable=set_config_var, values=set_config_options)
    set_config_dropdown.pack(pady=5)
    set_config_dropdown.set("Select Option")

    tk.Label(root, text="Enter Config Value:").pack(pady=5)
    set_config_entry = tk.Entry(root)
    set_config_entry.pack(pady=5)

    # Set Config 버튼
    tk.Button(
        root,
        text="Set Config",
        command=lambda: send_command("SET_CONFIG", set_config_var.get(), set_config_entry.get())
    ).pack(pady=5)

    # 드롭다운 메뉴 생성 (Change Avail 용 옵션)
    tk.Label(root, text="Change Avail Options:").pack(pady=10)
    change_avail_var = tk.StringVar()
    change_avail_options = ["Inoperative", "Operative"]
    change_avail_dropdown = ttk.Combobox(root, textvariable=change_avail_var, values=change_avail_options)
    change_avail_dropdown.pack(pady=5)
    change_avail_dropdown.set("Select Option")

    # Change Avail 버튼
    tk.Button(root, text="Change Avail", command=lambda: send_command("CHAN_AVAIL", change_avail_var.get())).pack(pady=5)

    root.mainloop()


async def handle_user_input():
    while True:
        try:
            # Use run_in_executor to check input_queue without blocking
            input_value = await asyncio.get_running_loop().run_in_executor(None, input_queue.get)
            await cs_action(input_value)
        except queue.Empty:
            await asyncio.sleep(0.1)  # Add slight delay to reduce CPU usage


async def on_connect(websocket, path):
    """ For every new charge point that connects, create a ChargePoint
    instance and start listening for messages.
    """
    try:
        requested_protocols = websocket.request_headers[
            'Sec-WebSocket-Protocol']
    except KeyError:
        _LOGGER.info("Client hasn't requested any Subprotocol. "
                     "Closing Connection")
    if websocket.subprotocol:
        _LOGGER.info("Protocols Matched: %s", websocket.subprotocol)
    else:
        # In the websockets lib if no subprotocols are supported by the
        # client and the server, it proceeds without a subprotocol,
        # so we have to manually close the connection.
        _LOGGER.warning('Protocols Mismatched | Expected Subprotocols: %s,'
                        ' but client supports  %s | Closing connection',
                        websocket.available_subprotocols,
                        requested_protocols)
        return await websocket.close()

    _LOGGER.info(f"Charger websocket path={path}")
    charge_point_id = path.strip('/')

    if charge_point_id not in cp_id:
        _LOGGER.info(f"Charger {charge_point_id} connected is connected.")
        cp = CS.ChargePoint(charge_point_id, websocket)
        charge_points[charge_point_id] = cp
        cp_id.append(charge_point_id)
        await CS.start()
    else:
        print("hello")
        _LOGGER.info(f"Charger {charge_point_id} reconnected.")
        cp: CS.ChargePoint = charge_points[charge_point_id]
        await CS.reconnect(websocket)
    _LOGGER.info(f"Charger {cp_id} disconnected.")


async def cs_action(command_tuple):
    command = command_tuple[0]
    print("Processing command:", command)

    print(command)
    if command == 'GET_CONFIG':
        for charge_point in cp_id:
            await charge_points[charge_point].get_configuration_request()
    elif command == "SET_CONFIG":
        arg = command_tuple[1] if len(command_tuple) > 1 else None
        for charge_point in cp_id:
            await charge_points[charge_point].change_configuration_request(arg)
    elif command == "CHAN_AVAIL":
        arg = command_tuple[1] if len(command_tuple) > 1 else None
        for charge_point in cp_id:
            await charge_points[charge_point].change_availability_request(arg)

    else:
        print('')


async def main():
    server = await websockets.serve(
        on_connect,
        '0.0.0.0',
        9000,
        subprotocols=['ocpp1.6']
    )
    _LOGGER.info(f"WebSocket Server Started")

    # Start Tkinter GUI in a separate thread
    gui_thread = Thread(target=open_gui, daemon=True)
    gui_thread.start()

    # Start handling user input asynchronously
    asyncio.create_task(handle_user_input())

    # Wait for WebSocket server to close
    await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(main())
