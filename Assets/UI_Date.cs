using UnityEngine;
using TMPro;

public class UI_Date : MonoBehaviour
{
    [Header("数据源")]
    public Main_Date dataStore;

    [Header("UI文本(3个)")]
    public TextMeshProUGUI txtMode;
    public TextMeshProUGUI txtCurrent;
    public TextMeshProUGUI txtTarget;

    void Update()
    {
        if (dataStore == null || !dataStore.hasData) return;

        if (txtMode    != null) txtMode.text    = $"{dataStore.mode}";
        if (txtCurrent != null) txtCurrent.text  = $"{dataStore.currentAngle}°";
        if (txtTarget  != null) txtTarget.text   = $"{dataStore.targetAngle}°";
    }
}
