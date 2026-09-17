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
_send_lock = None   # asyncio.Lock，单协程运行锁

_ble_status_event = []    # BLE连接变化事件
_ble_Receive_event = []     #BLE接收事件


# BLE接收事件注册
def BLE_register(func):   
    global _ble_Receive_event                                 
    _ble_Receive_event.append(func)

# BLE状态变化注册
def BLE_register_callback(func):
    global _ble_status_event
    _ble_status_event.append(func)

# 将ble_receiver -> BLE 启动回传协程
def BLE_Sender_Start(model_bytes):
    global _loop, _client
    if _loop is None or _client is None or not _client.is_connected:
        print("ble_receiver| BLE 未连接，无法回传模型")
        return False

    try:
        # 采用跨线程启动回传协程
        future = asyncio.run_coroutine_threadsafe(BLE_Sender(model_bytes), _loop)
    except RuntimeError as e:
        print(f"ble_receiver| 事件循环不可用: {e}")
        return False
    future.add_done_callback(_BLE_Sender_done)   # 回传结束事件
    return True


# 异常和取消时抛出异常并打印
def _BLE_Sender_done(future):
    try:
        future.result()
    except Exception as e:
        print(f"ble_receiver| 模型回传失败: {e}")


def stop_ble():
    """线程安全地请求 BLE 会话退出，可从任意线程调用"""
    if _loop is None or _stop_event is None:
        return
    _loop.call_soon_threadsafe(_stop_event.set)

# ble_receiver - > BLE  回传协程
async def BLE_Sender(model_bytes):
    global _client, _send_lock
    client = _client                                    # 固定本次回传使用的客户端
    if client is None or not client.is_connected:
        print("ble_receiver| BLE 未连接，回传中止")
        return False
    if _send_lock is None:                              # 在所属事件循环内创建
        _send_lock = asyncio.Lock()

    total = len(model_bytes)
    print(f"ble_receiver|开始回传模型，共 {total} 字节")
    async with _send_lock:                              #同一时刻只允许一次回传，避免分片交错
        for i in range(0, total, BLE_CHUNK_SIZE):
            chunk = model_bytes[i:i + BLE_CHUNK_SIZE]           #分包
            try:
                await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, chunk, response=True) #传入目标特征，必须确认收到
            except Exception:
                try:
                    await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, chunk, response=False) #超时切换无收到传输
                except Exception as e:
                    print(f"ble_receiver| 分片写入失败（偏移 {i}），回传中止: {e}")
                    return False
            await asyncio.sleep(BLE_WRITE_DELAY) # 延时等待对方处理
        # 发送结束标记
        try:
            await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, b"__MODEL_END__", response=True)
        except Exception as e:
            print(f"ble_receiver| 结束标记发送失败: {e}")
            return False
    print("ble_receiver| 模型回传完成")
    return True


# 启用并配置GATT会话协程
async def BLE_Receiver_Start():
    global _loop, _client, _stop_event

    _loop = asyncio.get_running_loop()
    _stop_event = asyncio.Event()

    BLE_Event_Savetrigger(_ble_status_event,f"ble_receiver|正在扫描'{ESP32_NAME}' ...")
    print(f"ble_receiver|正在扫描 '{ESP32_NAME}' ...")
    devices = await BleakScanner.discover(timeout=5.0)

    esp32_mac = None
    print("ble_receiver|设备列表：")
    for device in devices:
        print(f"ble_receiver|{device.name}")
        if device.name == ESP32_NAME:
            esp32_mac = device.address
            print(f"ble_receiver|找到设备! MAC: {esp32_mac}")
            BLE_Event_Savetrigger(_ble_status_event,f"ble_receiver|找到设备! MAC: {esp32_mac}")
            break

    if not esp32_mac:
        print("ble_receiver|没找到 ESP32，请检查")
        BLE_Event_Savetrigger(_ble_status_event,f"ble_receiver|没找到 ESP32，请检查")
        return

    BLE_Event_Savetrigger(_ble_status_event,f"ble_receiver|连接成功")
    await BLE_Receiver_Session(esp32_mac)

# 接收端会话
async def BLE_Receiver_Session(esp32_mac):
   
    global _client, _stop_event

    try:
        # 自动连接并拿到客户端对象
        async with BleakClient(esp32_mac) as client:
            _client = client
            print("ble_receiver|连接成功！等待数据中... (Ctrl+C 或 stop_ble() 停止)")
            BLE_Event_Savetrigger(_ble_status_event,f"ble_receiver|连接成功！等待数据中... ")

            # 等待数据，触发注册事件
            await client.start_notify(CHARACTERISTIC_UUID, BLE_Receiver)

            # 等待停止信号
            await _stop_event.wait()

            print("ble_receiver|收到停止信号，正在断开...")
            await client.stop_notify(CHARACTERISTIC_UUID)

    except asyncio.CancelledError:
        print("ble_receiver|会话被取消")
        raise
    except Exception as e:
        print(f"ble_receiver|连接失败: {e}")
        BLE_Event_Savetrigger(_ble_status_event,f"ble_receiver|连接失败: {e}")
        return False
    finally:
        _client = None
        BLE_Event_Savetrigger(_ble_status_event,f"ble_receiver|连接已关闭")
        print("ble_receiver|连接已关闭")
    return True

# ble_receiver - > 外部回调 消息转发
def BLE_Receiver(sender, data):
    message = data.decode('utf-8', errors='replace').strip()    # 把收到的字节数据转成字符串并打印
    print(f"ble_receiver|收到: {message}")
    
    BLE_Event_Savetrigger(_ble_Receive_event,message)           # 触发事件

# 安全事件触发
def BLE_Event_Savetrigger(event,*args, **kwargs):
    if event is None:
        print("ble_receiver| 未注册回调，数据仅打印")   # 独立运行时的默认行为
        return
    for func in event:                           # 接收事件触发
        try:
            func(*args,**kwargs)
        except Exception as e:
                print(f"ble_receiver| 回调异常: {e}")
    

   
    

        





# 手动主启动入口 - 启动异步 
if __name__ == "__main__":
    try:
        asyncio.run(BLE_Receiver_Start())
    except KeyboardInterrupt:
        print("\n已停止")
