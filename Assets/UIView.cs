using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// ============================================================================
// UIView — 唯一 UI 脚本
// ----------------------------------------------------------------------------
// 职责：只做「接收数据 -> 显示」。不含业务逻辑，不绑按钮回调，不引用任何业务脚本。
// 数据来源：AppEvents 的事件（在 AppEvents.Update 主线程派发，因此这里可直接操作 UI）
// 分区：
//   状态区：业务状态行（记录/训练/传输共用）+ 蓝牙状态行（独立，不覆盖业务状态）
//   数值区：模式 / 当前角度 / 目标角度
//   日志区：预制体列表 + 上限裁剪
// ============================================================================
public class UIView : MonoBehaviour
{
    [Header("状态区")]
    [Tooltip("业务状态（记录/训练/传输共用）")]
    [SerializeField] TextMeshProUGUI txtStatus;
    [Tooltip("蓝牙状态（独立一行，不会被业务状态覆盖）")]
    [SerializeField] TextMeshProUGUI txtBluetooth;

    [Header("数值区")]
    [SerializeField] TextMeshProUGUI txtMode;
    [SerializeField] TextMeshProUGUI txtCurrent;
    [SerializeField] TextMeshProUGUI txtTarget;

    [Header("日志区")]
    [Tooltip("日志条目预制体（需带 TextMeshProUGUI）")]
    [SerializeField] GameObject logPrefab;
    [Tooltip("日志条目父节点，留空则使用本物体")]
    [SerializeField] Transform logContainer;
    [Tooltip("最大保留条数，超出后删除最早的")]
    [SerializeField] int maxEntries = 200;
    [Tooltip("是否在日志前加时间戳")]
    [SerializeField] bool showTimestamp = true;

    [Header("业务状态文案")]
    [SerializeField] string textIdle = "Idle";
    [SerializeField] string textRecording = "Recording in progress";
    [SerializeField] string textRecordDone = "Record completed";
    [SerializeField] string textTraining = "Training in progress";
    [SerializeField] string textTrainDone = "Train completed";
    [SerializeField] string textTrainFailed = "Train failed";
    [SerializeField] string textTransferring = "Transferring in progress";
    [SerializeField] string textTransferDone = "Transferring completed";

    [Header("蓝牙状态文案")]
    [SerializeField] string textBleSearching = "Searching for Bluetooth...";
    [SerializeField] string textBleConnected = "Bluetooth connected";
    [SerializeField] string textBleFailed = "Bluetooth connection failed";
    [SerializeField] string textBleDisconnected = "Bluetooth disconnected";

    private readonly List<GameObject> _logEntries = new List<GameObject>();
    private bool _subscribed;

    // ======================================================================
    // 订阅生命周期
    // ======================================================================

    private void OnEnable()
    {
        TrySubscribe();
    }

    private void Start()
    {
        // 兜底：保证在所有 Awake 之后至少订阅一次（AppEvents.Instance 在 Awake 里赋值）
        TrySubscribe();
    }

    private void OnDisable()
    {
        Unsubscribe();
    }

    private void TrySubscribe()
    {
        if (_subscribed) return;

        AppEvents events = AppEvents.Instance;
        if (events == null)
        {
            Debug.LogWarning("UIView: 场景中找不到 AppEvents，UI 不会更新");
            return;
        }

        events.RecordStatusChanged += OnRecordStatusChanged;
        events.TrainingStatusChanged += OnTrainingStatusChanged;
        events.TransferStatusChanged += OnTransferStatusChanged;
        events.BleStatusChanged += OnBleStatusChanged;
        events.TelemetryChanged += OnTelemetryChanged;
        events.LogAppended += OnLogAppended;

        _subscribed = true;
    }

    private void Unsubscribe()
    {
        if (!_subscribed) return;

        AppEvents events = AppEvents.Instance;
        if (events != null)
        {
            events.RecordStatusChanged -= OnRecordStatusChanged;
            events.TrainingStatusChanged -= OnTrainingStatusChanged;
            events.TransferStatusChanged -= OnTransferStatusChanged;
            events.BleStatusChanged -= OnBleStatusChanged;
            events.TelemetryChanged -= OnTelemetryChanged;
            events.LogAppended -= OnLogAppended;
        }

        _subscribed = false;
    }

    // ======================================================================
    // 状态区
    // ======================================================================

    private void OnRecordStatusChanged(RecordStatus status)
    {
        switch (status)
        {
            case RecordStatus.Recording: SetStatusText(textRecording); break;
            case RecordStatus.Completed: SetStatusText(textRecordDone); break;
            // Idle 视为「无状态变化」，不覆盖当前文案
        }
    }

    private void OnTrainingStatusChanged(TrainingStatus status)
    {
        switch (status)
        {
            case TrainingStatus.Running: SetStatusText(textTraining); break;
            case TrainingStatus.Completed: SetStatusText(textTrainDone); break;
            case TrainingStatus.Failed: SetStatusText(textTrainFailed); break;
        }
    }

    private void OnTransferStatusChanged(TransferStatus status)
    {
        switch (status)
        {
            case TransferStatus.Running: SetStatusText(textTransferring); break;
            case TransferStatus.Completed: SetStatusText(textTransferDone); break;
        }
    }

    private void OnBleStatusChanged(BleStatus status)
    {
        string text = status switch
        {
            BleStatus.Searching => textBleSearching,
            BleStatus.Connected => textBleConnected,
            BleStatus.Failed => textBleFailed,
            BleStatus.Disconnected => textBleDisconnected,
            _ => null,
        };
        SetBluetoothText(text);
    }

    private void SetStatusText(string text)
    {
        if (string.IsNullOrEmpty(text)) return;
        if (txtStatus != null) txtStatus.text = text;
    }

    private void SetBluetoothText(string text)
    {
        if (string.IsNullOrEmpty(text)) return;
        if (txtBluetooth != null) txtBluetooth.text = text;
    }

    // ======================================================================
    // 数值区
    // ======================================================================

    private void OnTelemetryChanged(TelemetryData data)
    {
        if (txtMode != null) txtMode.text = data.Mode.ToString();
        if (txtCurrent != null) txtCurrent.text = data.CurrentAngle + "°";
        if (txtTarget != null) txtTarget.text = data.TargetAngle + "°";
    }

    // ======================================================================
    // 日志区
    // ======================================================================

    private void OnLogAppended(LogEntry entry)
    {
        if (logPrefab == null) return;

        Transform parent = logContainer != null ? logContainer : transform;
        GameObject go = Instantiate(logPrefab, parent);

        if (go.TryGetComponent(out TextMeshProUGUI tmp))
            tmp.text = $"<color={ColorOf(entry.Type)}>{TimePrefix(entry.Time)}{EscapeRichText(entry.Message)}</color>";

        _logEntries.Add(go);

        while (_logEntries.Count > maxEntries)
        {
            if (_logEntries[0] != null) Destroy(_logEntries[0]);
            _logEntries.RemoveAt(0);
        }

        // 强制刷新布局，确保新条目立即显示
        if (parent is RectTransform rect)
            LayoutRebuilder.MarkLayoutForRebuild(rect);
    }

    private string TimePrefix(System.DateTime time)
    {
        return showTimestamp ? $"[{time:HH:mm:ss}] " : string.Empty;
    }

    private static string ColorOf(LogType type)
    {
        return type switch
        {
            LogType.Error or LogType.Exception => "#fc0000",
            LogType.Warning => "#ffd900",
            LogType.Assert => "#ff8800",
            _ => "#FFFFFF",
        };
    }

    /// <summary>转义富文本特殊字符</summary>
    private static string EscapeRichText(string text)
    {
        if (string.IsNullOrEmpty(text)) return string.Empty;
        return text.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;");
    }
}
