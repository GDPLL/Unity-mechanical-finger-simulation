using UnityEngine;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Collections;

public class UDPTestSender : MonoBehaviour
{
    [Header("发送设置")]
    public string targetIP = "127.0.0.1";   // 发送目标IP（本机回环）
    public int targetPort = 8888;           // 目标端口（与接收端一致）
    public float stepDuration = 0.1f;       // 每个方向停留时间（秒）
    public bool logEnabled = true;          // 是否打印日志

    private UdpClient _udpClient;
    private float _angle=0;                  // 当前航向角（度）
    private int _stepIndex;                // 当前所处的边（0~3）
    private float _timer;

    void Start()
    {
        _udpClient = new UdpClient();
        // 开始循环发送协程
        StartCoroutine(SendLoop());
    }

    IEnumerator SendLoop()
    {
        while (true)
        {
            // 计算当前航向角：0, 90, 180, 270 循环
            _angle += 1f ;
            // 构造数据：E,航向,横滚,俯仰（横滚和俯仰固定为0）
            string message = $"E,{_angle:F1},0,0";
            // 发送UDP
            byte[] data = Encoding.UTF8.GetBytes(message);
            _udpClient.Send(data, data.Length, targetIP, targetPort);

            if (logEnabled)
                Debug.Log($"Send test data: {message}");

            // 等待 stepDuration 秒后切换到下一个方向
            yield return new WaitForSeconds(stepDuration);
        }
    }

    void OnDestroy()
    {
        _udpClient?.Close();
    }
}