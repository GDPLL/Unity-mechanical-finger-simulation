import asyncio
import threading
import time

import ble_receiver
import udp_bridge

# 启动BLE
def start_BLE_Service():
    asyncio.run(ble_receiver.BLE_Receiver_Start())    #启动BLE服务


def start_UDP_Service():
    asyncio.run(udp_bridge.UDP_start())          #启动UDP发送（-> Unity）


# BLE接收中转至UDP回调
def ble_to_udp(message):
    udp_bridge.UDP_Date_send(message)

# UDP回传BLE回调，启用BLE接收协程
def udp_to_ble(model_bytes):
    ok = ble_receiver.BLE_Sender_Start(model_bytes)
    if not ok:
        print("main|模型未能回传 ESP32（BLE 未连接）")


# 状态变化通知
def ble_status_to_udp(status):
    udp_bridge.UDP_Log_send(f"BLE_STATUS:{status}")


def main():
    ble_receiver.BLE_register(ble_to_udp)                       # BLE -> UDP 接收转发注册
    ble_receiver.BLE_register_callback(ble_status_to_udp)       # BLE 状态 -> UDP
    udp_bridge.UDP_register_event(udp_to_ble)                   # UDP -> BLE 回传事件

    udp_bridge.UDP_init()                                       # 先建好UDP套接字，避免BLE首包早于UDP就绪被丢弃
    udp_bridge.UDP_LOG_init()                                   # UDP_log sock

    ble_thread = threading.Thread(target=start_BLE_Service, name="ble", daemon=True)    # 启用BLE接收自动中转   
    udp_thread = threading.Thread(target=start_UDP_Service, name="udp", daemon=True)    # 启用UDP回传自动中转
    ble_thread.start()
    udp_thread.start()

    try:
        # 主线程在这里永久阻塞，不退出
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n程序已停止")
        ble_receiver.stop_ble()      # 线程安全地请求 BLE 会话退出
        udp_bridge.UDP_close()      # 退出UDP服务


if __name__ == "__main__":
    main()
    