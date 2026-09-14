import asyncio
import threading

import ble_receiver
import time


def start_ble_receiber():
    asyncio.run(ble_receiver.main())


ble_thread = threading.Thread(target=start_ble_receiber, daemon=True)

ble_thread.start()


try:
    # 主线程在这里永久阻塞，不退出
    while True:
        time.sleep(1) 
except KeyboardInterrupt:
    print("\n程序已停止")
    