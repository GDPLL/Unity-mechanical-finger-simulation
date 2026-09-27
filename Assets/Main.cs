using UnityEngine;
using System.Diagnostics;
using System.IO;
using System.Text;


/// <summary>
/// PY进程与功能启动器
/// <para>负责Py进程数据对外展示</para>
/// <para>脚本开始时启用Py中转进程</para>
/// <para>提供对外方法开始训练，启用训练进程，完成后调用UDP回传程序开始回传</para>
/// </summary>
public class Main : MonoBehaviour
{
    [Header("Python中转")]
    [Tooltip("PY_UDP/Main.py 的路径（相对于项目根目录）")]
    public string pythonScriptPath = "Assets/PY_UDP/Main.py";
    [Tooltip("Python 解释器路径，留空自动查找")]
    string pythonExePath = @"C:\Users\ZhuanZ1\AppData\Local\Programs\Python\Python312\python.exe";

    [Header("手势识别训练")]
    [Tooltip("训练管线脚本路径（相对于项目根目录）")]
    public string trainScriptPath = "Assets/ninapro_DB2/run_pipeline.py";
    [Tooltip("训练输出目录（相对于项目根目录）")]
    public string trainOutputDir = "Assets/ninapro_DB2/ModelExport";
    [Tooltip("Unity 采集的双通道 CSV 数据目录（相对于项目根目录）")]
    public string trainDataDir = "Assets/ninapro_DB2/data";

    [Header("模型回传")]
    [Tooltip("Main_UDP 引用，用于回传模型")]
    public Main_UDP udpBridge;

    private Process _pythonProcess; //Py中转进程进程
    private Process _trainProcess;  //Py训练进程
    private bool _subscribed;       //模式事件订阅状态

    private void OnEnable()
    {
        LaunchPythonBridge();
        TrySubscribe();
    }

    private void Start()
    {
        TrySubscribe();
    }

    private void OnDisable()
    {
        Unsubscribe();
        KillPythonBridge();
        KillTraining();
    }

    /// <summary>订阅模式切换事件</summary>
    private void TrySubscribe()
    {
        if (_subscribed) return;
        AppEvents events = AppEvents.Instance;
        if (events == null) return;
        events.ModeRequested += OnModeRequested;
        _subscribed = true;
    }

    /// <summary>退订模式切换事件</summary>
    private void Unsubscribe()
    {
        if (!_subscribed) return;
        AppEvents events = AppEvents.Instance;
        if (events != null) events.ModeRequested -= OnModeRequested;
        _subscribed = false;
    }

    /// <summary>把模式切换请求交给回传通道</summary>
    private void OnModeRequested(int mode)
    {
        if (udpBridge == null)
        {
            UnityEngine.Debug.LogError("Main|OnModeRequested|udpBridge 未指定");
            return;
        }
        udpBridge.SendModeCommand(mode);
    }

    /// <summary>
    /// <para>启动对应路径Py，开启进程</para>
    /// <para>设置Py输出事件回调，接管输出</para>
    /// _pythonProcess为目标进程字段
    /// </summary>
    private void LaunchPythonBridge()
    {
        // 构建脚本完整路径
        string scriptPath = ResolveInputPath(pythonScriptPath);
        if (scriptPath == null)
        {
            UnityEngine.Debug.LogWarning("Main: Python script not found, bridge will not start");
            return;
        }

        // 自动查找 Python 解释器
        string pyExe = ResolvePythonExe();
        if (string.IsNullOrEmpty(pyExe))
        {
            UnityEngine.Debug.LogWarning("Main: Python interpreter not found, specify pythonExePath manually");
            return;
        }

        try
        {
            ProcessStartInfo psi = new ProcessStartInfo     //c#启动外部进程配置
            {
                FileName = pyExe,                           //程序名称
                Arguments = $"\"{scriptPath}\"",            //脚本完整路径
                UseShellExecute = false,                    //直接启动可执行文件，重定向输出
                CreateNoWindow = true,
                RedirectStandardOutput = true,              //父程序接管进程
                RedirectStandardError = true,               //错误信息接管
                StandardOutputEncoding = Encoding.UTF8,     //输出程序
                StandardErrorEncoding = Encoding.UTF8,
            };
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

            _pythonProcess = new Process { StartInfo = psi, EnableRaisingEvents = true };   //创建进程对象
            _pythonProcess.OutputDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    UnityEngine.Debug.Log($"[Python] {e.Data}");        //接管正常输出
            };
            _pythonProcess.ErrorDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    UnityEngine.Debug.LogError($"[Python] {e.Data}");   //接管错误输出
            };

            _pythonProcess.Start();
            _pythonProcess.BeginOutputReadLine();   //.NET内部启动循环
            _pythonProcess.BeginErrorReadLine();

            UnityEngine.Debug.Log($"Main: Python bridge started (PID: {_pythonProcess.Id})");
        }
        catch (System.Exception ex)
        {
            UnityEngine.Debug.LogError($"Main: Failed to start Python: {ex.Message}");
        }
    }

    /// <summary>
    /// <para> 中止py进程并释放资源</para>
    /// </summary>
    private void KillPythonBridge()
    {
        if (_pythonProcess != null && !_pythonProcess.HasExited)
        {
            try
            {
                _pythonProcess.Kill();      //中止进程
                _pythonProcess.WaitForExit(2000);
                UnityEngine.Debug.Log("Main: Python bridge stopped");
            }
            catch (System.Exception ex)
            {
                UnityEngine.Debug.LogWarning($"Main: Error stopping Python: {ex.Message}");
            }
            _pythonProcess.Dispose();       //释放资源
            _pythonProcess = null;
        }
    }

    /// <summary>
    /// 返回可用py命令名
    /// </summary>
    /// <returns></returns>
    private static string FindPython()
    {
        // Windows: py, 再查 python3 / python
        string[] candidates = { "py", "python3", "python" };
        foreach (var name in candidates)
        {
            try
            {
                using (Process p = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = name,
                        Arguments = "--version",
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                    }
                })
                {
                    p.Start();
                    p.WaitForExit(1000);
                    if (p.ExitCode == 0)
                        return name;
                }
            }
            catch { }
        }
        return null;
    }

    /// <summary>查找必须已存在的输入文件/目录，找不到返回 null 并打印所有尝试过的路径</summary>
    private static string ResolveInputPath(string relativePath)
    {
        string[] candidates = BuildPathCandidates(relativePath);

        foreach (string candidate in candidates)
        {
            if (File.Exists(candidate) || Directory.Exists(candidate))
                return candidate;
        }

        UnityEngine.Debug.LogError(
            $"[Path] 未找到 {relativePath}，已尝试:\n  " + string.Join("\n  ", candidates));
        return null;
    }

    /// <summary>输出目录：与输入查找的第一候选保持一致（项目根 / 构建产物根），不要求已存在</summary>
    private static string ResolveOutputPath(string relativePath)
    {
        return Path.GetFullPath(Path.Combine(Application.dataPath, "..", relativePath));
    }

    private static string[] BuildPathCandidates(string relativePath)
    {
        return new[]
        {
            // 项目根 / 构建产物根
            Path.GetFullPath(Path.Combine(Application.dataPath, "..", relativePath)),
            // 随包分发：Assets/StreamingAssets/PY_UDP/...
            Path.GetFullPath(Path.Combine(Application.streamingAssetsPath, TrimAssetsPrefix(relativePath))),
        };
    }

    private static string TrimAssetsPrefix(string relativePath)
    {
        const string prefix = "Assets";
        if (relativePath.StartsWith(prefix, System.StringComparison.OrdinalIgnoreCase)
            && relativePath.Length > prefix.Length
            && (relativePath[prefix.Length] == '/' || relativePath[prefix.Length] == '\\'))
        {
            return relativePath.Substring(prefix.Length + 1);
        }
        return relativePath;
    }

    /// <summary>解析可用的 Python 解释器：配置的完整路径失效时回退到 PATH 查找</summary>
    private string ResolvePythonExe()
    {
        string pyExe = pythonExePath;

        bool looksLikePath = !string.IsNullOrEmpty(pyExe)
                             && (pyExe.IndexOf('/') >= 0 || pyExe.IndexOf('\\') >= 0);
        if (looksLikePath && !File.Exists(pyExe))
        {
            UnityEngine.Debug.LogWarning($"Main: 配置的 Python 不存在，回退到 PATH 查找: {pyExe}");
            pyExe = null;
        }

        if (string.IsNullOrEmpty(pyExe))
            pyExe = FindPython();

        return string.IsNullOrEmpty(pyExe) ? null : pyExe;
    }

    /// <summary>
    /// 启动训练进程，根据目标路径完成模型输出到目标位置
    /// </summary>
    public void TrainGestureModel()
    {
        string scriptPath = ResolveInputPath(trainScriptPath);   //程序路径
        if (scriptPath == null)
        {
            UnityEngine.Debug.LogError("Train: Training script not found, pipeline will not start");
            return;
        }

        string outDir = ResolveOutputPath(trainOutputDir);       //输出路径
        string dataDir = ResolveOutputPath(trainDataDir);        //训练数据路径

        string pyExe = ResolvePythonExe();                       //解释器路径
        if (string.IsNullOrEmpty(pyExe))
        {
            UnityEngine.Debug.LogError("Train: Python interpreter not found");
            return;
        }

        UnityEngine.Debug.Log($"Train: Starting pipeline...\n  Script: {scriptPath}\n  Data: {dataDir}\n  Output: {outDir}");

        // 如果已有训练在运行，先关闭
        KillTraining();

        try
        {
            UnityEngine.Debug.Log($"Train: Using Python: {pyExe}");
            ProcessStartInfo psi = new ProcessStartInfo     //配置进程
            {
                FileName = pyExe,
                Arguments = $"\"{scriptPath}\" --data-dir \"{dataDir}\" --output-dir \"{outDir}\"",
                UseShellExecute = false,        //重定向
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

            _trainProcess = new Process { StartInfo = psi, EnableRaisingEvents = true };
            _trainProcess.OutputDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    UnityEngine.Debug.Log($"[Train] {e.Data}");
            };
            _trainProcess.ErrorDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    UnityEngine.Debug.LogError($"[Train] {e.Data}");
            };
            _trainProcess.Exited += (s, e) =>
            {
                if (_trainProcess != null && _trainProcess.HasExited)
                {
                    if (_trainProcess.ExitCode == 0)
                    {
                        UnityEngine.Debug.Log("Train: Pipeline complete!");
                        // 回调发生在后台线程，AppEvents 内部会派发到主线程
                        AppEvents.Instance?.PublishTrainingStatus(TrainingStatus.Completed);
                    }
                    else
                    {
                        UnityEngine.Debug.LogError($"Train: Pipeline failed (exit code {_trainProcess.ExitCode})");
                        AppEvents.Instance?.PublishTrainingStatus(TrainingStatus.Failed);
                    }
                    _trainProcess.Dispose();
                    _trainProcess = null;
                }
            };

            _trainProcess.Start();                  //开始训练进程
            _trainProcess.BeginOutputReadLine();
            _trainProcess.BeginErrorReadLine();

            UnityEngine.Debug.Log($"Train: Pipeline started in background (PID: {_trainProcess.Id})");
            AppEvents.Instance?.PublishTrainingStatus(TrainingStatus.Running);   // UI 事件
        }
        catch (System.Exception ex)
        {
            UnityEngine.Debug.LogError($"Train: Failed to start training: {ex.Message}");
        }
    }

    /// <summary>
    /// 把训练好的模型文件回传给 ESP32。读取 ModelExport/lda_model.bin，交给 Main_UDP 发送。
    /// </summary>
    public void SendModelToEsp32()
    {
        //模型路径
        string modelFile = ResolveInputPath(Path.Combine(trainOutputDir, "lda_model.bin"));

        if (modelFile == null)
        {
            UnityEngine.Debug.LogError("SendModel: 模型文件未找到，请先完成训练");
            return;
        }

        if (udpBridge == null)
        {
            UnityEngine.Debug.LogError("SendModel: udpBridge (Main_UDP) 未指定");
            return;
        }

        byte[] bytes = File.ReadAllBytes(modelFile);

        //由Unity端开始回传
        udpBridge.SendModelToEsp32(bytes);

        UnityEngine.Debug.Log($"SendModel: 已把 {bytes.Length} 字节模型交给 Main_UDP 回传");
        AppEvents.Instance?.PublishTransferStatus(TransferStatus.Running);   // UI 事件
    }

    /// <summary>
    /// 中止训练进程,并释放内存
    /// </summary>
    private void KillTraining()
    {
        if (_trainProcess != null && !_trainProcess.HasExited)
        {
            try
            {
                _trainProcess.Kill();
                _trainProcess.WaitForExit(3000);
                UnityEngine.Debug.Log("Main: Training process stopped");
            }
            catch (System.Exception ex)
            {
                UnityEngine.Debug.LogWarning($"Main: Error stopping training process: {ex.Message}");
            }
            _trainProcess.Dispose();
            _trainProcess = null;
        }
    }
}
