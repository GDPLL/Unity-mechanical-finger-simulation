using UnityEngine;
using UnityEngine.Events;
using System.Threading;
using System.IO;
using System.Text;
using System.Globalization;
using System.Collections.Generic;

/// <summary>
/// 管理机器状态值与其历史记录，提供管理方法
/// <para>存储当前接收机器状态值，提供写入数据方法</para>
/// <para>提供开始记录数据方法，存入目标路径CSV</para>
/// <para>提供读取数据方法</para>
/// </summary>
public class Main_Date : MonoBehaviour
{
    // 解析后设备状态值，对外展示
    public int mode { get; private set; }
    public int currentAngle { get; private set; }
    public int targetAngle { get; private set; }
    public float rest1 { get; private set; }   // 通道A基准值（float）
    public float rest2 { get; private set; }   // 通道B基准值（float）
    public bool hasData { get; private set; }

    // Py进程日志存储
    public Queue<string> Recevie_Log;   
    private const int MAX_COUNT = 100;

    // 允许同时读，锁定写入独占
    public readonly ReaderWriterLockSlim rwLock = new ReaderWriterLockSlim();

    [Header("数据记录")]
    [Tooltip("记录目标行数，达到后自动保存并触发完成回调")]
    public int targetRows = 10000;
    [Tooltip("CSV 存储目录（相对于项目根目录）")]
    public string recordFolder = "Assets/ninapro_DB2/data";

    [Tooltip("记录完成回调（可在 Inspector 中绑定按钮/事件）")]
    public UnityEvent onRecordingComplete;

    [Header("UI 事件")]
    [Tooltip("UI_sampling 引用，用于刷新记录状态文本")]
    public UI_sampling ui;


    private bool _recording;    // 记录中 状态
    private int _recordCount;
    private readonly StringBuilder _csvBuf = new StringBuilder();
    private volatile bool _completionPending;

    public bool isRecording => _recording;

    /// <summary>由UDP线程调用：写入数据</summary>
    public void WriteData(int mode, int currentAngle, int targetAngle, float rest1, float rest2)
    {
        rwLock.EnterWriteLock();
        try
        {
            this.mode = mode;
            this.currentAngle = currentAngle;
            this.targetAngle = targetAngle;
            this.rest1 = rest1;
            this.rest2 = rest2;
            this.hasData = true;
        }
        finally { rwLock.ExitWriteLock(); }
    }

    /// <summary>
    /// 由UDP线程调用：保证 MAX_COUNT = 100 的日志写入方法
    /// </summary>
    /// <param name="str">日志</param>
    public void WritLog(string str)
    {
        if (Recevie_Log.Count >= MAX_COUNT)
        {
            Recevie_Log.Dequeue();   // 满了，丢掉最旧的一条
        }
        Recevie_Log.Enqueue(str);
    }

    /// <summary>
    /// 读取最新日志
    /// </summary>
    /// <returns></returns>
    public string ReadLog()
    {
        if (Recevie_Log.Count == 0)
            return null;
        return Recevie_Log.Dequeue();
    }

    /// <summary>由主线程调用：读取数据</summary>
    public void ReadData(out int mode, out int currentAngle, out int targetAngle,
                         out float rest1, out float rest2, out bool hasData)
    {
        rwLock.EnterReadLock();
        try
        {
            mode = this.mode;
            currentAngle = this.currentAngle;
            targetAngle = this.targetAngle;
            rest1 = this.rest1;
            rest2 = this.rest2;
            hasData = this.hasData;
        }
        finally { rwLock.ExitReadLock(); }
    }


    /// <summary>开始记录：清空 data 目录下的 CSV，重置计数器</summary>
    public void StartRecording()
    {
        _recording = true;
        _recordCount = 0;
        _completionPending = false;
        _csvBuf.Clear();
        _csvBuf.AppendLine("emg_col0,emg_col1");
        ClearRecordFolder();
        Debug.Log($"Main_Date: 开始记录（目标 {targetRows} 行）...");
        ui?.TextStart();   // UI: 记录开始
    }

    /// <summary>中止记录</summary>
    public void StopRecording()
    {
        _recording = false;
        Debug.Log($"Main_Date: 记录已中止，当前 {_recordCount} 行");
    }

    /// <summary>由 UDP 线程每包调用：记录一帧双通道数据</summary>
    public void RecordSample(float r1, float r2)
    {
        if (!_recording) return;

        _csvBuf.Append(r1.ToString("R", CultureInfo.InvariantCulture))
               .Append(',')
               .Append(r2.ToString("R", CultureInfo.InvariantCulture))
               .Append('\n');
        _recordCount++;

        if (_recordCount >= targetRows)
        {
            _recording = false;
            SaveCsv();
            _completionPending = true;   // 主线程 Update 中触发回调
        }
    }


    private void Update()
    {
        if (_completionPending)
        {
            _completionPending = false;
            Debug.Log("Main_Date: 记录完成！");
            onRecordingComplete?.Invoke();
            ui?.TextOver();   // UI: 记录完成
        }
    }

    /// <summary>
    /// 清空CSV目录
    /// </summary>
    private void ClearRecordFolder()
    {
        string folder = GetRecordFolderPath();
        if (Directory.Exists(folder))
        {
            foreach (string f in Directory.GetFiles(folder, "*.csv"))
                File.Delete(f);
            Debug.Log($"Main_Date: 已清空 CSV 目录: {folder}");
        }
    }

    /// <summary>
    /// 生成目标CSV在文件路径下
    /// </summary>
    private void SaveCsv()
    {
        string folder = GetRecordFolderPath();
        Directory.CreateDirectory(folder);      //创建文件夹
        string fileName = System.DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".csv";
        string path = Path.Combine(folder, fileName);
        File.WriteAllText(path, _csvBuf.ToString(), Encoding.UTF8);
        Debug.Log($"Main_Date: 已保存 {_recordCount} 行 → {path}");
    }

    /// <summary>
    /// 获取记录路径
    /// </summary>
    /// <returns></returns>
    private string GetRecordFolderPath()
    {
        string folder = Path.Combine(Application.dataPath, "..", recordFolder);
        return Path.GetFullPath(folder);
    }

    private void OnDestroy()
    {
        rwLock?.Dispose();
    }
}
