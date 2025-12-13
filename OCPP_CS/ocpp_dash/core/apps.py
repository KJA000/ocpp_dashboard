# core/apps.py
import os, threading, asyncio, websockets
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    _started = False

    def ready(self):
        if os.environ.get("RUN_MAIN") == "true" and not CoreConfig._started:
            CoreConfig._started = True
            def run_ocpp():
                async def main():
                    from core.management.commands.ocpp_server import DjangoChargePoint
                    async def on_connect(ws, path):
                        cp_id = path.strip('/')
                        cp = DjangoChargePoint(cp_id, ws)
                        await cp.init_cp()
                        await cp.start()
                    server = await websockets.serve(on_connect, '0.0.0.0', 9000, subprotocols=['ocpp1.6'])
                    await server.wait_closed()
                asyncio.run(main())
            threading.Thread(target=run_ocpp, daemon=True).start()
