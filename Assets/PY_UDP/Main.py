import asyncio
import threading
import time

import ble_receiver
import udp_bridge

# ============================================================
# Main - 编排层（Composition Root）
# ------------------------------------------------------------
# 职责只有三件事：
#   1) 启动两个互相不认识的服务（各自独立线程）
#   2) 接线：把 A 的输出注入成 B 的输入，反之亦然
#   3) 生命周期：启动 / 优雅停止
# ble_receiver 与 udp_bridge 之间没有任何 import 关系，
# 单独运行任何一个文件都能正常工作。
# ============================================================


# ===== 1. 两个组件的独立启动函数 =====
def start_BLE_Service():
    asyncio.run(ble_receiver.BLE_Receiver_Start())    #启动BLE服务


def start_UDP_Service():
    udp_bridge.UDP_start()          #启动UDP发送（-> Unity）
    udp_bridge.start_recv()         #启动UDP监听（Unity 回传模型）


# ===== 2. 中转逻辑：组件之间怎么调度，只写在这里 =====
def ble_to_udp(message):
    """方向 A：ESP32 --BLE--> PC --UDP--> Unity"""
    udp_bridge.UDP_send(message)


def udp_to_ble(model_bytes):
    """方向 B：Unity --UDP--> PC --BLE--> ESP32
       本函数运行在 udp_bridge 的接收线程里，
       ble_receiver.BLE_Sender_Start 内部用 run_coroutine_threadsafe 投递到 BLE 事件循环"""
    ok = ble_receiver.BLE_Sender_Start(model_bytes)
    if not ok:
        print("main|模型未能回传 ESP32（BLE 未连接）")


def ble_status_to_udp(status):
    """方向 C：把 BLE 连接状态同步给 Unity（BLE_STATUS:xxx）"""
    udp_bridge.UDP_send(f"BLE_STATUS:{status}")


def main():
    # 先建好 UDP 发送 socket：避免 BLE 先收到数据时 UDP_send 因 _sock 为空而丢包
    # （UDP_start 是幂等的，UDP 线程内再调用一次也不会重复建 socket）
    udp_bridge.UDP_start()

    # ---- 接线：双方只认识回调，不认识对方 ----
    ble_receiver.set_message_callback(ble_to_udp)            # BLE -> UDP
    ble_receiver.set_status_callback(ble_status_to_udp)      # BLE 状态 -> UDP
    udp_bridge.set_model_callback(udp_to_ble)                # UDP -> BLE

    # ---- 启动两个完全独立的服务 ----
    ble_thread = threading.Thread(target=start_BLE_Service, name="ble", daemon=True)
    udp_thread = threading.Thread(target=start_UDP_Service, name="udp", daemon=True)
    ble_thread.start()
    udp_thread.start()

    try:
        # 主线程在这里永久阻塞，不退出
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n程序已停止")
        ble_receiver.stop_ble()      # 线程安全地请求 BLE 会话退出
        udp_bridge.UDP_close()


if __name__ == "__main__":
    main()
    