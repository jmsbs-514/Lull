# 打包说明

## 环境

- Windows 10/11 x64
- Python 3.13
- 项目依赖已安装：`pip install -r requirements.txt`
- PyInstaller：`pip install pyinstaller`

## 构建

```powershell
cd C:\Users\jmsbs\Desktop\Lull
python -m PyInstaller --noconfirm --clean Lull.spec
```

产物：

```text
dist\Lull\Lull.exe
dist\Lull\_internal\
```

这是 **onedir** 版本，必须保留整个 `Lull` 文件夹；不要只拷 `Lull.exe`。

## 关键点

- 入口是 `launcher.py`，无控制台。
- `web/` 会打进 `_internal/web`，服务端通过 `sys._MEIPASS` 读取。
- 音频采集以 `Lull.exe --audio-helper` 子进程运行，入口会先分派这个参数，
  不会创建窗口或申请单实例互斥体。
- `settings.json`、`startup.log`、`error.log` 写在 exe 同目录，方便便携使用。
- WebView2 的 .NET DLL、winrt、soundcard、pycaw、pystray 由 `Lull.spec`
  里的 `collect_all` 收进去。
- 图标：`assets/lull.ico`。

## 发布 zip

```powershell
Remove-Item dist\Lull\settings.json, dist\Lull\startup.log, dist\Lull\error.log -ErrorAction SilentlyContinue
Compress-Archive -Path dist\Lull\* -DestinationPath Lull-0.1.0-win64.zip -Force
```

不要把个人 `settings.json` 打进发布包。

## 已验证

- 打包版能启动，`/api/debug` 返回正常
- 窗口 804×100
- `audio_available=true`、`audio_spectrum=true`
- 音频 helper 进程为 `Lull.exe --audio-helper`
- 无 `error.log`
