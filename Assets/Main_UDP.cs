using UnityEngine;
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Globalization;

public class Main_UDP : MonoBehaviour
{
    [Header("数据存储")]
    public Main_Date dataStore;

    [Header("UDP设置")]
    public int port = 8888;

    [Header("回传UDP设置")]
    [Tooltip("Python 回传监听地址")]
    public string sendTargetIP = "127.0.0.1";
    [Tooltip("Python 回传监听端口")]
    public int sendPort = 8890;
    [Tooltip("每个UDP分片大小（字节）")]
    public int sendChunkSize = 1024;

    [Header("UI 事件")]
    [Tooltip("UI_sampling 引用，用于刷新传输完成文本")]
    public UI_sampling ui;

    // ---------- 内部 ----------
    private UdpClient _udp;
    private Thread _thread;
    private bool _running;

    // 回传
    private UdpClient _udpSender;
    private volatile bool _uploadActive;
    private volatile bool _transferCompletePending;
    private volatile string _bleStatusPending;
    private readonly object _sendLock = new object();

    private void Update()
    {
        // 蓝牙状态（后台线程派发到主线程）
        if (_bleStatusPending != null)
        {
            string status = _bleStatusPending;
            _bleStatusPending = null;
            switch (status)
            {
                case "searching": ui?.BluetoothSearching(); break;
                case "connected": ui?.BluetoothConnected(); break;
                case "failed":    ui?.BluetoothFailed();    break;
            }
        }
        if (_transferCompletePending)
        {
            _transferCompletePending = false;
            ui?.TransferringOver();   // UI: 传输完成
        }
    }

    // 格式: M=模式 C=当前角度 T=目标角度 A=静息1(float) B=静息2(float)
    private static readonly Regex _pattern = new Regex(@"^M(\d+)C(\d+)T(\d+)A([-\d.]+)B([-\d.]+)$",
        RegexOptions.Compiled);

    // ======================================================================
    // 生命周期
    // ======================================================================

    private void OnEnable()
    {
        if (dataStore == null)
        {
            UnityEngine.Debug.LogError("Main_UDP: dataStore (Main_Date) not assigned");
            return;
        }

        // 启动 UDP 接收
        _udp = new UdpClient(port);
        _running = true;
        _thread = new Thread(ReceiveLoop) { IsBackground = true };
        _thread.Start();
    }

    private void OnDisable()
    {
        _running = false;
        _udp?.Close();
        _thread?.Join(50);
        AbortModelUpload();
    }

    // ======================================================================
    // UDP 后台线程
    // ======================================================================

    private void ReceiveLoop()
    {
        IPEndPoint remoteEP = new IPEndPoint(IPAddress.Any, 0);

        while (_running)
        {
            try
            {
                byte[] bytes = _udp.Receive(ref remoteEP);
                string msg = Encoding.UTF8.GetString(bytes).Trim();

                // 蓝牙状态消息：BLE_STATUS:searching/connected/failed
                if (msg.StartsWith("BLE_STATUS:"))
                {
                    _bleStatusPending = msg.Substring("BLE_STATUS:".Length);
                    continue;
                }

                Match m = _pattern.Match(msg);
                if (!m.Success) continue;

                int mode         = int.Parse(m.Groups[1].Value);
                int currentAngle = int.Parse(m.Groups[2].Value);
                int targetAngle  = int.Parse(m.Groups[3].Value);
                float rest1      = float.Parse(m.Groups[4].Value, CultureInfo.InvariantCulture);
                float rest2      = float.Parse(m.Groups[5].Value, CultureInfo.InvariantCulture);

                // 写入 Main_Date
                dataStore.WriteData(mode, currentAngle, targetAngle, rest1, rest2);

                // 若正在记录，则采样一帧双通道数据
                if (dataStore.isRecording)
                    dataStore.RecordSample(rest1, rest2);
            }
            catch { break; }
        }
    }

    // ======================================================================
    // 模型回传 UDP（Unity -> Python -> BLE -> ESP32）
    // ======================================================================

    /// <summary>启用回传 UDP 发送通道（可被按钮调用）</summary>
    public void EnableModelUpload()
    {
        lock (_sendLock)
        {
            if (_udpSender != null) return;
            _udpSender = new UdpClient();
            _uploadActive = true;
            Debug.Log($"Main_UDP: 回传已启用 → {sendTargetIP}:{sendPort}");
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
        EnableModelUpload();
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
            _transferCompletePending = true;   // UI: 传输完成（主线程派发）
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

    private void SendRaw(byte[] data)
    {
        lock (_sendLock)
        {
            if (_udpSender == null || !_uploadActive) return;
            try
            {
                _udpSender.Send(data, data.Length, sendTargetIP, sendPort);
            }
            catch { /* 发送通道可能已被关闭 */ }
        }
    }
}