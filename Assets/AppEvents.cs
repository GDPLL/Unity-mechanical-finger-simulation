using System;
using System.Collections.Concurrent;
using UnityEngine;

// ============================================================================
// AppEvents — 全局事件中枢（UI 系统唯一触点）
// ----------------------------------------------------------------------------
// 职责：
//   1. 命令转发：按钮 -> OnXxxButton() -> 业务脚本订阅的 XxxRequested
//   2. 状态广播：业务脚本从任意线程 Publish -> 主线程派发给 UI
//   3. 主线程派发：后台线程事件入队，Update 中统一派发（Unity UI 只能在主线程访问）
//   4. 日志转发：订阅 Application.logMessageReceived，转成主线程事件
//
// 约定：业务脚本只与 AppEvents 交互，不直接引用任何 UI 脚本；
//       UI 脚本只订阅 AppEvents 事件并显示，不含业务逻辑、不绑按钮回调。
// ============================================================================
public class AppEvents : MonoBehaviour
{
    public static AppEvents Instance { get; private set; }

    [Header("派发节奏")]
    [Tooltip("每帧最多派发多少条待处理日志，避免日志刷屏卡帧")]
    [SerializeField] int logPerFrame = 50;
    [Tooltip("待派发日志队列上限，超出丢弃最旧的，防止后台线程刷屏撑爆内存")]
    [SerializeField] int maxPendingLogs = 500;

    // ---------------- 命令事件（按钮 -> 业务） ----------------
    public event Action TrainRequested;
    public event Action TransferRequested;
    public event Action RecordStartRequested;
    public event Action RecordStopRequested;

    // ---------------- 状态事件（业务 -> UI，均在主线程触发） ----------------
    public event Action<RecordStatus> RecordStatusChanged;
    public event Action<TrainingStatus> TrainingStatusChanged;
    public event Action<TransferStatus> TransferStatusChanged;
    public event Action<BleStatus> BleStatusChanged;
    public event Action<TelemetryData> TelemetryChanged;
    public event Action<LogEntry> LogAppended;

    // ---------------- 按钮入口（Inspector 里绑到 Button.OnClick） ----------------
    public void OnTrainButton() { TrainRequested?.Invoke(); }
    public void OnTransferButton() { TransferRequested?.Invoke(); }
    public void OnRecordStartButton() { RecordStartRequested?.Invoke(); }
    public void OnRecordStopButton() { RecordStopRequested?.Invoke(); }

    // ---------------- 状态发布接口（可从任意线程调用） ----------------
    public void PublishRecordStatus(RecordStatus status)
        => Enqueue(() => RecordStatusChanged?.Invoke(status));

    public void PublishTrainingStatus(TrainingStatus status)
        => Enqueue(() => TrainingStatusChanged?.Invoke(status));

    public void PublishTransferStatus(TransferStatus status)
        => Enqueue(() => TransferStatusChanged?.Invoke(status));

    public void PublishBleStatus(BleStatus status)
        => Enqueue(() => BleStatusChanged?.Invoke(status));

    /// <summary>遥测高频调用：只保留最新一帧，每帧最多派发一次（不排队，不丢帧率）</summary>
    public void PublishTelemetry(int mode, int currentAngle, int targetAngle, float rest1, float rest2)
    {
        lock (_telemetryGate)
        {
            _pendingTelemetry = new TelemetryData(mode, currentAngle, targetAngle, rest1, rest2);
            _hasPendingTelemetry = true;
        }
    }

    /// <summary>手动插入一条日志（可选，业务脚本也可用）</summary>
    public void PublishLog(string message, LogType type = LogType.Log)
    {
        EnqueueLog(new LogEntry(message, type, DateTime.Now));
    }

    // ---------------- 内部 ----------------
    private readonly ConcurrentQueue<Action> _mainQueue = new ConcurrentQueue<Action>();
    private readonly ConcurrentQueue<LogEntry> _logQueue = new ConcurrentQueue<LogEntry>();

    private readonly object _telemetryGate = new object();
    private TelemetryData _pendingTelemetry;
    private volatile bool _hasPendingTelemetry;

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Debug.LogWarning("AppEvents: 场景中存在多个 AppEvents，仅第一个生效");
            return;
        }
        Instance = this;
    }

    private void OnEnable()
    {
        // 日志可能在任意线程触发，这里只入队，绝不在此回调中调用 Debug.Log（会无限递归）
        Application.logMessageReceived += HandleUnityLog;
    }

    private void OnDisable()
    {
        Application.logMessageReceived -= HandleUnityLog;
    }

    private void OnDestroy()
    {
        if (Instance == this) Instance = null;
    }

    /// <summary>注意：可能运行在后台线程，只允许做入队操作</summary>
    private void HandleUnityLog(string condition, string stackTrace, LogType type)
    {
        EnqueueLog(new LogEntry(condition, type, DateTime.Now));
    }

    private void EnqueueLog(LogEntry entry)
    {
        _logQueue.Enqueue(entry);
        while (_logQueue.Count > maxPendingLogs && _logQueue.TryDequeue(out _)) { }
    }

    private void Enqueue(Action action)
    {
        _mainQueue.Enqueue(action);
    }

    private void Update()
    {
        // 1) 状态类事件：FIFO，不丢
        while (_mainQueue.TryDequeue(out Action action))
        {
            try { action(); }
            catch (Exception e) { Debug.LogError($"AppEvents: 事件处理异常 {e}"); }
        }

        // 2) 遥测：最新值覆盖，每帧最多一次
        if (_hasPendingTelemetry)
        {
            TelemetryData data;
            lock (_telemetryGate)
            {
                data = _pendingTelemetry;
                _hasPendingTelemetry = false;
            }
            try { TelemetryChanged?.Invoke(data); }
            catch (Exception e) { Debug.LogError($"AppEvents: 遥测事件处理异常 {e}"); }
        }

        // 3) 日志：限流派发
        for (int i = 0; i < logPerFrame && _logQueue.TryDequeue(out LogEntry entry); i++)
        {
            try { LogAppended?.Invoke(entry); }
            catch (Exception e)
            {
                // 处理失败时立刻跳出，避免"报错 -> 又产生日志 -> 再报错"自我循环
                Debug.LogError($"AppEvents: 日志事件处理异常 {e}");
                break;
            }
        }
    }
}

// ============================================================================
// 事件载荷类型
// ============================================================================

/// <summary>记录（CSV 采集）状态</summary>
public enum RecordStatus { Idle, Recording, Completed }

/// <summary>训练管线状态</summary>
public enum TrainingStatus { Idle, Running, Completed, Failed }

/// <summary>模型回传状态</summary>
public enum TransferStatus { Idle, Running, Completed }

/// <summary>蓝牙连接状态</summary>
public enum BleStatus { Searching, Connected, Failed, Disconnected }

/// <summary>遥测一帧：模式 / 当前角度 / 目标角度 / 双通道静息值</summary>
public readonly struct TelemetryData
{
    public readonly int Mode;
    public readonly int CurrentAngle;
    public readonly int TargetAngle;
    public readonly float Rest1;
    public readonly float Rest2;

    public TelemetryData(int mode, int currentAngle, int targetAngle, float rest1, float rest2)
    {
        Mode = mode;
        CurrentAngle = currentAngle;
        TargetAngle = targetAngle;
        Rest1 = rest1;
        Rest2 = rest2;
    }
}

/// <summary>一条日志</summary>
public readonly struct LogEntry
{
    public readonly string Message;
    public readonly LogType Type;
    public readonly DateTime Time;

    public LogEntry(string message, LogType type, DateTime time)
    {
        Message = message;
        Type = type;
        Time = time;
    }
}
