using UnityEngine;

public class Joint_Control : MonoBehaviour
{
    [Header("对象引用")]
    public Main_Date dataStore;

    public Transform A;
    public Transform B;

    [Header("旋转参数")]
    public float rotationParam = 0f;
    [Tooltip("旋转K值（缩放系数）")]
    public float rotationK = 1f;

    [Header("旋转偏移参数")]
    public float rotationOffsetParam = 0f;
    [Tooltip("旋转偏移K值（缩放系数）")]
    public float rotationOffsetK = 1f;

    [Header("限制")]
    public float minX = -50f;

    void Update()
    {
        if(dataStore==null)return;
        // 从 Main_Date 读取当前角度
        float rotationParam   = dataStore.currentAngle;
        float anlge = rotationParam * rotationK;
        float anlge2 = anlge*rotationOffsetParam * rotationOffsetK;
        // A旋转 = 当前角度 × 通道A基准值，沿X-方向，最小-50°
        if (A != null)
        {
            float aX = -Mathf.Abs(anlge);
            aX = Mathf.Max(aX, minX);
            Vector3 rot = A.localEulerAngles;
            rot.x = aX;
            A.localEulerAngles = rot;
        }

        // B旋转 = 当前角度 × 通道B基准值，沿X-方向，最小-50°
        if (B != null)
        {
            float bX = -Mathf.Abs(anlge2);
            bX = Mathf.Max(bX, minX);
            Vector3 rot = B.localEulerAngles;
            rot.x = bX;
            B.localEulerAngles = rot;
        }
    }
}
