using UnityEngine;


public class Camera_ctrl : MonoBehaviour
{
    [Header("目标对象")]
    public Transform target;

    [Header("旋转设置")]
    [Tooltip("鼠标旋转灵敏度")]
    public float rotateSpeed = 3f;
    [Tooltip("旋转平滑时间")]
    public float smoothTime = 0.12f;

    [Header("距离设置")]
    public float distance = 5f;
    public float minDistance = 1f;
    public float maxDistance = 30f;
    [Tooltip("滚轮缩放速度")]
    public float zoomSpeed = 3f;
    [Tooltip("缩放平滑时间")]
    public float zoomSmoothTime = 0.08f;

    [Header("角度限制")]
    public float minYAngle = -80f;
    public float maxYAngle = 80f;

    // 当前角度与目标角度
    private float currentX, currentY;
    private float targetX, targetY;
    // SmoothDamp 速度变量
    private float xVelocity, yVelocity;
    // 距离平滑
    private float currentDistance;
    private float targetDistance;
    private float distanceVelocity;

    void Start()
    {
        if (target == null)
        {
            Debug.LogWarning("Camera_ctrl: target not set");
            return;
        }

        // 根据相机当前位置计算初始角度
        Vector3 dir = transform.position - target.position;
        distance = Mathf.Max(dir.magnitude, 0.1f);

        Vector3 angles = Quaternion.LookRotation(-dir, Vector3.up).eulerAngles;
        currentX = angles.y;
        currentY = angles.x;
        if (currentY > 180f) currentY -= 360f;
        currentY = Mathf.Clamp(currentY, minYAngle, maxYAngle);

        targetX = currentX;
        targetY = currentY;
        targetDistance = distance;
        currentDistance = distance;

        xVelocity = yVelocity = distanceVelocity = 0f;
    }

    void LateUpdate()
    {
        if (target == null) return;

        // 左键按下时，鼠标移动控制旋转
        if (Input.GetMouseButton(0))
        {
            targetX += Input.GetAxis("Mouse X") * rotateSpeed;
            targetY -= Input.GetAxis("Mouse Y") * rotateSpeed;
            targetY = Mathf.Clamp(targetY, minYAngle, maxYAngle);
        }

        // 滚轮控制距离
        float scroll = Input.GetAxis("Mouse ScrollWheel");
        if (Mathf.Abs(scroll) > 0.001f)
        {
            targetDistance -= scroll * zoomSpeed;
            targetDistance = Mathf.Clamp(targetDistance, minDistance, maxDistance);
        }

        // 平滑插值
        currentX = Mathf.SmoothDampAngle(currentX, targetX, ref xVelocity, smoothTime);
        currentY = Mathf.SmoothDampAngle(currentY, targetY, ref yVelocity, smoothTime);
        currentDistance = Mathf.SmoothDamp(currentDistance, targetDistance, ref distanceVelocity, zoomSmoothTime);

        // 计算球面坐标位置，始终朝向目标
        Quaternion rot = Quaternion.Euler(currentY, currentX, 0);
        transform.position = target.position + rot * new Vector3(0, 0, -currentDistance);
        transform.LookAt(target);
    }
}
