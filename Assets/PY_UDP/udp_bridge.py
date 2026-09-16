import socket
import threading
import asyncio
# udp_bridge - Unity 基于UDP收发中转


TARGET_IP = "127.0.0.1"      
TARGET_PORT = 8888           # 蓝牙接收中转数据流端口
LISTEN_PORT = 8890           # Unity 回传 UDP 端口
TARGET_LOG_PORT = 8889       # 蓝牙接收中转测试日志端口

LOG_ENABLED = True           # 对应 logEnabled

_sock = None                 # UDP 发送套接字（-> Unity）
_recv_sock = None            # UDP 接收套接字（Unity 回传 ->）

_UDP_receiver_event = []    # 模型回传回调


# UDP 发送到端口回调函数
def UDP_send(message):
    global _sock
    if _sock is None:
        return
    if isinstance(message, str):
        data = message.encode('utf-8')
    else:
        data = message
    _sock.sendto(data, (TARGET_IP, TARGET_PORT))

# 配置UDP与开启回传循环
async def UDP_start():
    global _sock
    if _sock is not None:      # 幂等：可被 Main 与 UDP 线程重复调用
        return
    _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    #IPV4协议，UDP传输
    _sock.bind((TARGET_IP, LISTEN_PORT))                   #绑定接收端口
    _sock.setblocking(False)    # 设置非阻塞
    UDP_send("UDP|创建传输")
    
    await _recv_loop()     # 启动回传协程

# UDP回传接收循环
async def _recv_loop():
    model_buf = bytearray()     #可变数组
    loop = asyncio.get_running_loop()   
    while True:
        data,address = await loop.sock_recvfrom(_sock, 65536)   # 协程读取数据
        
        if data.startswith(b'MODEL_START:'):
            model_buf = bytearray()
            continue
        elif data == b'MODEL_END':
            if _UDP_receiver_event is not None and len(model_buf) > 0:
                if LOG_ENABLED:
                    print(f"udp_bridge: 收到模型，共 {len(model_buf)} 字节，启动回传事件")
                UDP_Event_Savetrigger(_UDP_receiver_event,bytes(model_buf))            # 开始回传事件
            model_buf = bytearray()
            continue
        else:
            model_buf += data
            
            
def UDP_close():
    global _sock
    if _sock is not None:
        _sock.close()
        _sock = None
        
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
