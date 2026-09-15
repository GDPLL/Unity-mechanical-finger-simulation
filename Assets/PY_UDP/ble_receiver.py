import asyncio
import time
from bleak import BleakClient, BleakScanner

# BLE - ble_receiver - udp_bridge 基于蓝牙BLE三端通信


# ===== 配置 =====
ESP32_NAME = "ESP32_Bridge"                  # ESP32 广播的名字（和你 Arduino 代码里一致）
CHARACTERISTIC_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"   # 数据接收特征值（ESP32 -> PC）
WRITE_CHARACTERISTIC_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # 数据写入特征值（PC -> ESP32）
BLE_CHUNK_SIZE = 20                          # BLE 单次写入字节数（默认 MTU 20）
BLE_WRITE_DELAY = 0.02                       # 两次 BLE 写入间隔（秒）

_loop = None        #事件循环
_client = None      #蓝牙客户端组件
_stop_event = None  # asyncio.Event，控制会话退出
_on_message_callback = None   # 收到 BLE 数据后的去处，由 Main 注入
_on_status_callback = None    # 连接状态变化的去处，由 Main 注入

# ===== 对外注册接口（Main 用来接线） =====
def set_message_callback(cb):
    """注册数据接收回调：收到 ESP32 数据后调用 cb(message: str)
       cb 为 None 时只打印日志（即本模块可完全独立运行）"""
    global _on_message_callback
    _on_message_callback = cb


def set_status_callback(cb):
    """注册状态回调：连接状态变化时调用 cb(status: str)
       status 取值：searching / connecting / connected / failed / disconnected"""
    global _on_status_callback
    _on_status_callback = cb


def _notify_status(status):
    """把状态抛给外部，未注册时静默忽略"""
    print(f"ble_receiver|状态: {status}")
    if _on_status_callback is None:
        return
    try:
        _on_status_callback(status)
    except Exception as e:
        print(f"ble_receiver| 状态回调异常: {e}")


# 将ble_receiver -> BLE 启动回传协程
def BLE_Sender_Start(model_bytes):
    #可从任意线程调用（如 udp_bridge 的接收线程）。
    #把模型字节数据经 BLE 回传 ESP32。
    global _loop, _client
    if _loop is None or _client is None or not _client.is_connected:
        print("ble_receiver| BLE 未连接，无法回传模型")
        return False

    try:
        # 关键：BLE 的 client 只属于 _loop 所在线程，必须用这个跨线程投递，
        # 绝不能直接 await 或在别的线程里操作 client
        asyncio.run_coroutine_threadsafe(BLE_Sender(model_bytes), _loop)
    except RuntimeError as e:
        print(f"ble_receiver| 事件循环不可用: {e}")
        return False
    return True


def stop_ble():
    """线程安全地请求 BLE 会话退出，可从任意线程调用"""
    if _loop is None or _stop_event is None:
        return
    _loop.call_soon_threadsafe(_stop_event.set)

# ble_receiver - > BLE  回传协程
async def BLE_Sender(model_bytes):
    global _client
    total = len(model_bytes)
    print(f"ble_receiver|开始回传模型，共 {total} 字节")
    for i in range(0, total, BLE_CHUNK_SIZE):
        chunk = model_bytes[i:i + BLE_CHUNK_SIZE]           #分包
        try:
            await _client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, chunk, response=True) #传入目标特征，必须确认收到
        except Exception:
            await _client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, chunk, response=False) #超时切换无收到传输
        await asyncio.sleep(BLE_WRITE_DELAY) # 延时等待对方处理
    # 发送结束标记
    try:
        await _client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, b"__MODEL_END__", response=True)
    except Exception as e:
        print(f"ble_receiver| 结束标记发送失败: {e}")
    print("ble_receiver| 模型回传完成")


# 启用并配置GATT会话协程
async def BLE_Receiver_Start():
    global _loop, _client, _stop_event

    _loop = asyncio.get_running_loop()
    _stop_event = asyncio.Event()

    _notify_status("searching")
    print(f"ble_receiver|正在扫描 '{ESP32_NAME}' ...")
    devices = await BleakScanner.discover(timeout=5.0)

    esp32_mac = None
    print("ble_receiver|设备列表：")
    for device in devices:
        print(f"ble_receiver|{device.name}")
        if device.name == ESP32_NAME:
            esp32_mac = device.address
            print(f"ble_receiver|找到设备! MAC: {esp32_mac}")
            break

    if not esp32_mac:
        print("ble_receiver|没找到 ESP32，请检查")
        _notify_status("failed")
        return

    _notify_status("connecting")
    await BLE_Receiver_Session(esp32_mac)

# 接收端会话
async def BLE_Receiver_Session(esp32_mac):
   
    global _client, _stop_event

    try:
        async with BleakClient(esp32_mac) as client:
            _client = client
            print("ble_receiver|连接成功！等待数据中... (Ctrl+C 或 stop_ble() 停止)")
            _notify_status("connected")

            await client.start_notify(CHARACTERISTIC_UUID, BLE_Receiver)

            # 等待停止信号，而不是永久阻塞
            await _stop_event.wait()

            print("ble_receiver|收到停止信号，正在断开...")
            await client.stop_notify(CHARACTERISTIC_UUID)

    except asyncio.CancelledError:
        print("ble_receiver|会话被取消")
        raise
    except Exception as e:
        print(f"ble_receiver|连接失败: {e}")
        _notify_status("failed")
        return False
    finally:
        _client = None
        _notify_status("disconnected")
        print("ble_receiver|连接已关闭")
    return True

# ble_receiver - > 外部回调 消息转发
def BLE_Receiver(sender, data):
    message = data.decode('utf-8', errors='replace').strip()    # 把收到的字节数据转成字符串并打印
    print(f"ble_receiver|收到: {message}")

    if _on_message_callback is None:
        print("ble_receiver| 未注册回调，数据仅打印")   # 独立运行时的默认行为
        return
    try:
        _on_message_callback(message)
    except Exception as e:
        print(f"ble_receiver| 回调异常: {e}")


# 手动主启动入口 - 启动异步 
if __name__ == "__main__":
    try:
        asyncio.run(BLE_Receiver_Start())
    except KeyboardInterrupt:
        print("\n已停止")
