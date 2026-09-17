import socket
import sys
import asyncio
# udp_bridge - Unity 基于UDP收发中转


TARGET_IP = "127.0.0.1"      
TARGET_PORT = 8888           # 蓝牙接收中转数据流端口
LISTEN_PORT = 8890           # Unity 回传 UDP 端口
TARGET_LOG_PORT = 8889       # 蓝牙接收中转测试日志端口

LOG_ENABLED = True           # 对应 logEnabled

MODEL_START_TAG = b'MODEL_START:'   # 模型回传起始标记
MODEL_END_TAG = b'MODEL_END'        # 模型回传结束标记

_UDP_receiver_event = []        # 模型回传回调

_no_sock = False             # 套接字就绪标记
_recv_loop_running = False   # 回传接收循环是否已在运行

# 字典套接字
_channels = {
    "data": {"sock": None, "port": TARGET_PORT,     "warned": False},
    "log":  {"sock": None, "port": TARGET_LOG_PORT, "warned": False},
}

# 注册回传事件
def UDP_register_event(event):
    global _UDP_receiver_event
    _UDP_receiver_event.append(event)

# UDP 发送到端口回调函数
def UDP_Date_send(message):
    UDP_send("data",message)

def UDP_Log_send(message):
    UDP_send("log",message)

def UDP_set_sock(name, sock):
    if name in _channels:
        _channels[name]["sock"] = sock
        _channels[name]["warned"] = False   # 重新就绪后，警告标志复位

# 按字典对应通道发送到指定位置
def UDP_send(name, message):
    ch = _channels.get(name)
    if ch is None:
        print(f"udp_bridge| 未知通道: {name}")
        return False

    sock = ch["sock"]
    if sock is None:
        if not ch["warned"]:
            ch["warned"] = True
            print(f"udp_bridge| [{name}] 套接字未就绪，数据被丢弃")
        return False

    data = message.encode('utf-8') if isinstance(message, str) else message
    try:
        sock.sendto(data, (TARGET_IP, ch["port"]))
        return True
    except OSError as e:
        print(f"udp_bridge| [{name}] 发送失败: {e}")
        return False


# 创建UDP套接字并配置端口参数
def UDP_init():
     
    ch = _channels.get("data")
    if ch is None:
        print("udp_bridge| 未知通道: data")
        return False
    _sock = ch["sock"]
    
    #启用数据流套接字
    if _sock is not None:       # 幂等
        return True
    if not hasattr(asyncio.BaseEventLoop, "sock_recvfrom"):
        raise RuntimeError(
            f"udp_bridge| 需要 Python 3.11+（asyncio.loop.sock_recvfrom），当前 {sys.version.split()[0]}"
        )
    _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    #IPV4协议，UDP传输
    _sock.bind((TARGET_IP, LISTEN_PORT))                    #绑定回传接收端口
    _sock.setblocking(False)                                # 设置非阻塞    
    
    UDP_set_sock("data",_sock)
    return True

# UPD日志端口
def UDP_LOG_init():
    
    ch = _channels.get("log")
    if ch is None:
        print("udp_bridge| 未知通道: log")
        return False
    _sock_log = ch["sock"]

    #启用日志PY日志输出套接字
    if _sock_log is not None:
        return True
    _sock_log = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    #IPV4协议，UDP传输
    _sock_log.setblocking(False)                                 # 设置非阻塞     
    
    UDP_set_sock("log",_sock_log)
    return True
     

# 配置UDP与开启回传循环,无限等待数据
async def UDP_start():
    global _recv_loop_running
    UDP_init()                 # 幂等套接字创建
    UDP_LOG_init()             # 日志sock
    if _recv_loop_running:     # 幂等单一接收循环
        return
    _recv_loop_running = True
    UDP_Log_send("UDP|创建传输")
    
    await _recv_loop()     # 启动回传协程
    

# UDP回传接收循环，持续读取目标端口数据，完成传输后启动中转事件
async def _recv_loop():
    model_buf = bytearray()     # 可变数组
    sock = _channels["data"]["sock"]              # 固定本次循环套接字，避免 UDP_close 读到 None
    loop = asyncio.get_running_loop()   
    while True:
        try:
            data,address = await loop.sock_recvfrom(sock, 65536)   # 协程读取数据
        except OSError as e:
            # UDP_close() 关闭套接字触发属正常收尾，其余异常必须看得见
            print(f"udp_bridge| 接收循环已退出: {e}")
            break
        
        if data.startswith(MODEL_START_TAG):
            model_buf = bytearray(data[len(MODEL_START_TAG):])
            continue
        elif data.strip() == MODEL_END_TAG:      # 容忍尾随空白/换行
            if len(model_buf) > 0:
                if LOG_ENABLED:
                    print(f"udp_bridge: 收到模型，共 {len(model_buf)} 字节，启动回传事件")
                UDP_Event_Savetrigger(_UDP_receiver_event,bytes(model_buf))            # 开始回传事件
            model_buf = bytearray()
            continue
        else:
            model_buf += data
            
            
def UDP_close():
    global _recv_loop_running
    for ch in _channels.values:
        if ch is not None:
            if ch["sock"] is not None:
                ch["sock"].close()
                ch["sock"]=None
                ch["warned"] =False
    _recv_loop_running =False   
        
# 安全事件触发
def UDP_Event_Savetrigger(event,*args, **kwargs):
    if event is None:
        print("udp_bridge| 未注册回传回调")   
        return
    for func in event:                           # 接收事件触发
        try:
            func(*args,**kwargs)
        except Exception as e:
                print(f"udp_bridge| 回调异常: {e}")
