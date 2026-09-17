using UnityEngine;
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Globalization;
using System.Threading.Tasks;

/// <summary>
/// <para>负责UDP_sock接收与回传的创建</para>
/// <para>接收循环负责日志与数据流的双重监听，脚本启用时新建线程创建接收循环，接收循环自带解析，本地完成到Main_Date的存储</para>
/// <para>回传循环由main负责调用，线程完成传输后自动销毁</para>
/// </summary>
public class Main_UDP : MonoBehaviour
{
    [Header("数据存储")]
    public Main_Date dataStore; //数据存储组件

    [Header("UDP设置")]
    public const int RECEIVER_PORT = 8888;      //接收数据流端口
    public const int RECEIVERLOG_PORT = 8889;   //接收日志端口

    [Header("回传UDP设置")]
    [Tooltip("Python 回传监听地址")]
    public string sendTargetIP = "127.0.0.1";
    [Tooltip("Python 回传监听端口")]
    public int SENDPORT = 8890;
    [Tooltip("每个UDP分片大小（字节）")]
    public int sendChunkSize = 1024;

    // UDP 核心组件
    private UdpClient _udp;
    private UdpClient _udp_log;
    private Thread _thread;
    private bool _running;

    // 回传
    private UdpClient _udpSender;
    private volatile bool _uploadActive;                //回传启用
    private readonly object _sendLock = new object();   //读取锁，多线程，防止数据中断

    private void OnEnable()
    {
        if (dataStore == null)
        {
            UnityEngine.Debug.LogError("Main_UDP: dataStore (Main_Date) not assigned");
            return;
        }

        // 启动 UDP 接收数据流
        _udp = new UdpClient(RECEIVER_PORT);
        _running = true;
        // 启动 UDP 接收日志流
        _udp_log = new UdpClient(RECEIVERLOG_PORT);

        // 新建接收线程
        _thread = new Thread(Loop) { IsBackground = true };  // 直接退出
        _thread.Start();
    }

    // 格式: M=模式 C=当前角度 T=目标角度 A=静息1(float) B=静息2(float)
    private static readonly Regex _pattern = new Regex(@"^M(\d+)C(\d+)T(\d+)A([-\d.]+)B([-\d.]+)$",
        RegexOptions.Compiled);

    // 蓝牙状态前缀（Python 侧经日志端口 8889 发来）
    private const string BLE_STATUS_PREFIX = "BLE_STATUS:";

    /// <summary>解析蓝牙状态载荷，只认约定枚举值</summary>
    private static bool TryParseBleStatus(string payload, out BleStatus status)
    {
        switch (payload.ToLowerInvariant())
        {
            case "searching": status = BleStatus.Searching; return true;
            case "connected": status = BleStatus.Connected; return true;
            case "failed": status = BleStatus.Failed; return true;
            case "disconnected": status = BleStatus.Disconnected; return true;
            default: status = default; return false;
        }
    }


    // 启用时
    private void OnDisable()
    {
        _running = false;
        _udp?.Close();
        _udp_log?.Close();      
        _thread?.Join(50);
        AbortModelUpload();
    }

    //后台线程方法
    private void Loop()
    {
        _ = Task.Run(async () =>
        {
            await ReceiveLoop();    //接收协程
        });
        _ = Task.Run(async () =>
        {
            await ReceiveLogLoop(); //接收日志
        });
    }

    /// <summary>无限接收循环与解析写入方法</summary>
    private async Task ReceiveLoop()
    {
        IPEndPoint remoteEP = new IPEndPoint(IPAddress.Any, 0); // 发送方IP+端口

        while (_running)
        {
            string msg;
            try
            {
                byte[] bytes = _udp.Receive(ref remoteEP);          // 接收数据并填写发射放地址端口
                msg = Encoding.UTF8.GetString(bytes).Trim();
            }
            catch (ObjectDisposedException)
            {
                break;                                              // OnDisable 关闭套接字，正常收尾
            }
            catch (SocketException e) when (!_running)
            {
                UnityEngine.Debug.Log($"Main_UDP: 数据接收已停止 ({e.SocketErrorCode})");
                break;
            }
            catch (Exception e)
            {
                UnityEngine.Debug.LogException(e);                  // 绝不静默退出
                break;
            }

            // 单包解析失败只跳过这一包，不能打断整条接收链
            try
            {
                Match m = _pattern.Match(msg);                  // 匹配字段
                if (!m.Success) continue;

                int mode = int.Parse(m.Groups[1].Value);
                int currentAngle = int.Parse(m.Groups[2].Value);
                int targetAngle = int.Parse(m.Groups[3].Value);
                float rest1 = float.Parse(m.Groups[4].Value, CultureInfo.InvariantCulture);
                float rest2 = float.Parse(m.Groups[5].Value, CultureInfo.InvariantCulture);

                // 写入 Main_Date
                dataStore.WriteData(mode, currentAngle, targetAngle, rest1, rest2);

                // 若正在记录，则采样一帧双通道数据
                if (dataStore.isRecording)
                    dataStore.RecordSample(rest1, rest2);
            }
            catch (Exception e)
            {
                UnityEngine.Debug.LogError($"Main_UDP: 数据包处理失败，已跳过: {e.Message}");
            }
        }
    }
    /// <summary>无限接收日志循环</summary>
    private async Task ReceiveLogLoop()
    {
        IPEndPoint remoteEP = new IPEndPoint(IPAddress.Any, 0); // 发送方IP+端口

        while (_running)
        {
            string msg;
            try
            {
                byte[] bytes = _udp_log.Receive(ref remoteEP);          // 接收数据并填写发射放地址端口
                msg = Encoding.UTF8.GetString(bytes).Trim();
            }
            catch (ObjectDisposedException)
            {
                break;                                                  // OnDisable 关闭套接字，正常收尾
            }
            catch (SocketException e) when (!_running)
            {
                UnityEngine.Debug.Log($"Main_UDP: 日志接收已停止 ({e.SocketErrorCode})");
                break;
            }
            catch (Exception e)
            {
                UnityEngine.Debug.LogException(e);                      // 绝不静默退出
                break;
            }

            try
            {
                // 蓝牙状态：BLE_STATUS:searching|connected|failed|disconnected -> UI 事件
                if (msg.StartsWith(BLE_STATUS_PREFIX, StringComparison.Ordinal))
                {
                    string payload = msg.Substring(BLE_STATUS_PREFIX.Length).Trim();
                    if (TryParseBleStatus(payload, out BleStatus bleStatus))
                    {
                        AppEvents.Instance?.PublishBleStatus(bleStatus);
                        continue;
                    }
                    // 未识别的载荷不静默丢弃，落成日志便于排查
                    UnityEngine.Debug.LogWarning($"Main_UDP: 无法识别的蓝牙状态: {payload}");
                }

                // 写入 Main_Date 日志（内部会转发到 UI 事件）
                dataStore.WritLog(msg);
            }
            catch (Exception e)
            {
                UnityEngine.Debug.LogError($"Main_UDP: 日志处理失败，已跳过: {e.Message}");
            }
        }

    }

    /// <summary>启用回传 UDP sock</summary>
    public void ReSend_sock_init()
    {
        lock (_sendLock)
        {
            if (_udpSender != null) return;
            _udpSender = new UdpClient();
            _uploadActive = true;
            Debug.Log($"Main_UDP: 回传已启用 → {sendTargetIP}:{SENDPORT}");
        }
    }

    /// <summary>中止回传（关闭发送通道）</summary>
    public void AbortModelUpload()
    {
        lock (_sendLock)
        {
            _uploadActive = false;
            if (_udpSender != null)
            {
                _udpSender.Close();
                _udpSender = null;
            }
        }
        Debug.Log("Main_UDP: 回传已中止");
    }

    /// <summary>把模型文件字节数据回传给 Python（后台线程发送，不阻塞主线程）</summary>
    public void SendModelToEsp32(byte[] fileData)
    {
        if (fileData == null || fileData.Length == 0)
        {
            UnityEngine.Debug.LogError("Main_UDP: 模型数据为空");
            return;
        }
        ReSend_sock_init();
        Thread t = new Thread(() => UploadLoop(fileData)) { IsBackground = true };
        t.Start();
    }

    private void UploadLoop(byte[] data)
    {
        try
        {
            // 协议: MODEL_START:<总字节数> + 数据分片 + MODEL_END
            SendRaw(Encoding.ASCII.GetBytes($"MODEL_START:{data.Length}"));
            for (int i = 0; i < data.Length && _uploadActive; i += sendChunkSize)
            {
                int len = Math.Min(sendChunkSize, data.Length - i);
                byte[] chunk = new byte[len];
                Array.Copy(data, i, chunk, 0, len);
                SendRaw(chunk);
            }
            SendRaw(Encoding.ASCII.GetBytes("MODEL_END"));
            UnityEngine.Debug.Log($"Main_UDP: 模型已发送 {data.Length} 字节");
            // 本方法在后台线程运行，AppEvents 内部会派发到主线程
            AppEvents.Instance?.PublishTransferStatus(TransferStatus.Completed);
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogError($"Main_UDP: 模型发送失败: {ex.Message}");
        }
        finally
        {
            _uploadActive = false;
        }
    }
    /// <summary>
    /// UDP 回传方法，
    /// </summary>
    /// <param name="data"></param>
    private void SendRaw(byte[] data)
    {
        lock (_sendLock)
        {
            if (_udpSender == null || !_uploadActive) return;
            try
            {
                _udpSender.Send(data, data.Length, sendTargetIP, SENDPORT);
            }
            catch { /* 发送通道可能已被关闭 */ }
        }
    }
}