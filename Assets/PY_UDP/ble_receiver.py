import asyncio
import time
from bleak import BleakClient, BleakScanner
import udp_bridge

# BLE - ble_receiver - udp_bridge 基于蓝牙BLE三端通信


# ===== 配置 =====
ESP32_NAME = "ESP32_Bridge"                  # ESP32 广播的名字（和你 Arduino 代码里一致）
CHARACTERISTIC_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"   # 数据接收特征值（ESP32 -> PC）
WRITE_CHARACTERISTIC_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # 数据写入特征值（PC -> ESP32）
BLE_CHUNK_SIZE = 20                          # BLE 单次写入字节数（默认 MTU 20）
BLE_WRITE_DELAY = 0.02                       # 两次 BLE 写入间隔（秒）

_loop = None
_client = None


# ble_receiver - > udp_bridge 消息转发
def notification_handler(sender, data):
    # 把收到的字节数据转成字符串并打印
    message = data.decode('utf-8', errors='replace').strip()
    print(f"收到: {message}")
    udp_bridge.UDP_send(message)                        

# 将ble_receiver -> BLE写入异步事件池
def send_model_data(model_bytes):
    """把模型字节数据经 BLE 回传 ESP32。可在 udp_bridge 的线程中调用。"""
    global _loop, _client
    if _loop is None or _client is None or not _client.is_connected:
        print("ble_receiver: BLE 未连接，无法回传模型")
        return False

    asyncio.run_coroutine_threadsafe(_write_model(model_bytes), _loop)
    return True

# ble_receiver - > BLE  消息转发 
async def _write_model(model_bytes):
    global _client
    total = len(model_bytes)
    print(f"ble_receiver: 开始回传模型，共 {total} 字节")
    for i in range(0, total, BLE_CHUNK_SIZE):
        chunk = model_bytes[i:i + BLE_CHUNK_SIZE] #分包
        try:
            await _client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, chunk, response=True) #传入，必须确认收到
        except Exception:
            await _client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, chunk, response=False) #超时切换无收到传输
        await asyncio.sleep(BLE_WRITE_DELAY) # 延时等待对方处理
    # 发送结束标记
    try:
        await _client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, b"__MODEL_END__", response=True)
    except Exception as e:
        print(f"ble_receiver: 结束标记发送失败: {e}")
    print("ble_receiver: 模型回传完成")


# 基于异步实现GATT协程通信 - 所有转发方法的订阅 
async def main():
    global _loop, _client
    _loop = asyncio.get_running_loop()

    # 提前启动 UDP，用于发送蓝牙状态到 Unity
    udp_bridge.UDP_start()
    udp_bridge.UDP_send("BLE_STATUS:searching")

    print(f"正在扫描 '{ESP32_NAME}' ...")
    # 扫描 5 秒，找到 ESP32
    devices = await BleakScanner.discover(timeout=5.0)
    esp32_mac = None
    print("设备列表：")
    for device in devices:
        print(f"{device.name}")
        if device.name == ESP32_NAME:
            esp32_mac = device.address
            print(f"找到设备! MAC: {esp32_mac}")
            break

    if not esp32_mac:
        print("没找到 ESP32，请检查：")
        udp_bridge.UDP_send("BLE_STATUS:failed")
        return

    try:
        async with BleakClient(esp32_mac) as client:
            _client = client
            print("连接成功！等待数据中... (按 Ctrl+C 停止)")
            udp_bridge.UDP_send("BLE_STATUS:connected")        # 蓝牙已连接
            udp_bridge.set_model_callback(send_model_data)  # 注册回传回调
            udp_bridge.start_recv()                         # 启动回传 UDP 监听

            # 将转发方法订阅在接收事件中
            await client.start_notify(CHARACTERISTIC_UUID, notification_handler)

            # 保持程序运行（永久等待，直到用户按 Ctrl+C）
            await asyncio.Event().wait()

    except Exception as e:
        print(f"连接失败: {e}")
        udp_bridge.UDP_send("BLE_STATUS:failed")


# 手动主启动入口 - 启动异步 
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已停止")
