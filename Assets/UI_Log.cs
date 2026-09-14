using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System.Collections.Generic;

public class UI_Log : MonoBehaviour
{
    [Header("日志预制体")]
    public GameObject logPrefab;

    [Header("设置")]
    [Tooltip("最大保留条数，超出后删除最早的")]
    public int maxEntries = 200;
    [Tooltip("是否在日志前加时间戳")]
    public bool showTimestamp = true;

    private readonly List<GameObject> _entries = new List<GameObject>();

    private void OnEnable()
    {
        Application.logMessageReceived += HandleLog;
    }

    private void OnDisable()
    {
        Application.logMessageReceived -= HandleLog;
    }

    /// <summary>转义富文本特殊字符</summary>
    private static string EscapeRichText(string text)
    {
        return text.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;");
    }

    private void HandleLog(string logString, string stackTrace, LogType type)
    {
        if (logPrefab == null) return;

        string color = type switch
        {
            LogType.Error or LogType.Exception => "#fc0000",
            LogType.Warning => "#ffd900",
            LogType.Assert => "#ff8800",
            _ => "#FFFFFF"
        };

        string time = showTimestamp ? $"[{System.DateTime.Now:HH:mm:ss}] " : "";
        string escaped = EscapeRichText(logString);

        // 单条生成预制体
        GameObject go = Instantiate(logPrefab, transform);
        TextMeshProUGUI tmp = go.GetComponent<TextMeshProUGUI>();
        if (tmp != null)
            tmp.text = $"<color={color}>{time}{escaped}</color>";

        _entries.Add(go);

        // 超过上限，删除最早的
        while (_entries.Count > maxEntries)
        {
            Destroy(_entries[0]);
            _entries.RemoveAt(0);
        }

        // 强制刷新布局，确保新条目立即显示
        LayoutRebuilder.MarkLayoutForRebuild((RectTransform)transform);
    }
}
