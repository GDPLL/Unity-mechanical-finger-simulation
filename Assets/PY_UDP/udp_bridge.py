import socket
import threading

# udp_bridge - Unity 基于UDP收发中转


TARGET_IP = "127.0.0.1"      # 对应 Unity targetIP（Unity 接收地址）
TARGET_PORT = 8888           # 对应 Unity targetPort（Unity 接收端口）
LISTEN_IP = "127.0.0.1"      # Python 回传监听地址
LISTEN_PORT = 8890           # Unity 回传 UDP 端口
LOG_ENABLED = True           # 对应 logEnabled

_sock = None                 # UDP 发送套接字（-> Unity）
_recv_sock = None            # UDP 接收套接字（Unity 回传 ->）
_on_model_callback = None    # 模型回传回调


# ===== 发送到 Unity =====
def UDP_send(message):
    global _sock
    if _sock is None:
        return
    if isinstance(message, str):
        data = message.encode('utf-8')
    else:
        data = message
    _sock.sendto(data, (TARGET_IP, TARGET_PORT))


def UDP_start():
    global _sock
    _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def UDP_close():
    global _sock
    if _sock is not None:
        _sock.close()
        _sock = None


# ===== 接收 Unity 回传 =====
def set_model_callback(cb):
    """注册模型回传回调：收到完整模型数据后调用 cb(model_bytes)"""
    global _on_model_callback
    _on_model_callback = cb


def start_recv(port=LISTEN_PORT):
    """启动 UDP 监听线程，接收 Unity 回传的模型文件"""
    global _recv_sock
    _recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _recv_sock.bind((LISTEN_IP, port))
    _recv_sock.settimeout(0.5)
    t = threading.Thread(target=_recv_loop, daemon=True)
    t.start()
    if LOG_ENABLED:
        print(f"udp_bridge: 回传监听已启动 {LISTEN_IP}:{port}")


def _recv_loop():
    """接收 Unity 回传数据。协议：
       MODEL_START:<totalBytes>  -> 开始
       原始字节分片               -> 数据
       MODEL_END                  -> 结束，重组后触发回调
    """
    model_buf = bytearray()
    while True:
        try:
            data, _addr = _recv_sock.recvfrom(65536)
        except socket.timeout:
            continue
        except Exception:
            break

        if data.startswith(b'MODEL_START:'):
            model_buf = bytearray()
            continue
        elif data == b'MODEL_END':
            if _on_model_callback is not None and len(model_buf) > 0:
                if LOG_ENABLED:
                    print(f"udp_bridge: 收到模型，共 {len(model_buf)} 字节，转交 BLE 回传")
                _on_model_callback(bytes(model_buf))
            model_buf = bytearray()
            continue
        else:
            model_buf += data
