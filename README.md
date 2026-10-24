# Lull

贴在 Windows 桌面上的歌词层。默认鼠标穿透、不抢焦点，只显示当前歌词和翻译。

## 环境

- Windows 10/11
- Python 3.13
- WebView2 Runtime
- 网易云音乐
- BetterNCM 1.2.0
- InfLink-rs 3.4.0

网易云原版不向 Windows 上报媒体状态，因此需要 BetterNCM 和 InfLink-rs 将播放信息发布到 SMTC。

> **使用前必读：用网易云必须先装插件。**
> 只装 Lull 是不够的。没有 BetterNCM + InfLink-rs，Lull 在 Windows 里看不到网易云的媒体会话，
> 表现就是完全没有歌词。
>
> 新版网易云设置里可能已经有“开启 SMTC”选项，但它通常只提供歌名/歌手/进度等基础信息；
> Lull 的网易云歌词和翻译依赖 InfLink 提供的 `NCM-歌曲ID`。如果开了原生 SMTC 仍然读不到，
> 先关掉它，再重启网易云，让 InfLink 发布会话。两个不要同时开。
>
> 其他播放器（Spotify 等）原生支持 SMTC，不需要这套插件。


## 安装

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

也可以设置 `LULL_PYTHON` 指向其他带完整依赖的 `pythonw.exe`。

## 启动

双击 `启动.bat`。启动脚本依次查找：

1. `LULL_PYTHON`
2. 项目内的 `.venv\Scripts\pythonw.exe`
3. 当前开发环境
4. 系统 `pythonw.exe` 或 `pyw.exe`

启动失败时查看项目根目录的 `error.log`。

## 使用

- 左键单击托盘图标：显示或隐藏桌面歌词。
- 右键单击托盘图标：弹出正在播放卡片，可以上一首、播放/暂停、下一首、拖动进度。
- 卡片右上角的主页键打开设置面板；`⋯` 里可以显示/隐藏歌词、切换锁定和退出，
  菜单里的“返回”或 Esc 回到播放视图。
- 设置面板可以切换四种歌词样式（光影、排版、留白、细线），调整字号和不透明度、
  控制翻译和下一句。
- “预设”可以一次设好样式、配色、律动和律动透明度（夜航 / 纸上 / 留白 / 线）。
- 在面板“区域”里可以调歌词区域宽高；解锁后也可以直接拖动歌词右下角整体缩放。
- “调色板”提供 6 套预设，也可以单独调文字色、强调色和背景色；
  默认“跟随外观”，不选配色时保持每套外观原本的颜色。
- “律动”里可选关闭/波形/阶梯/细线/呼吸/密集；开启后歌词底部会出现一整行频谱，
  从左到右对应 32 段低频到高频，没有声音时会慢慢收缩隐藏。面板里还可以单独调律动透明度和颜色；
  默认跟随强调色。
- 点击“调整位置”后拖动歌词，再点“锁定”恢复鼠标穿透。
- “回到屏幕中央”会把歌词层移到主显示器中央。

播放控制通过 Windows SMTC 发送给网易云，需要 InfLink-rs 提供播放/暂停和跳转支持；
进度条在播放器不支持跳转时会自动回弹。

## 数据来源

歌词优先通过 SMTC 中 InfLink-rs 提供的网易云歌曲 ID 精确获取，取不到时按歌名和歌手回退到 LRCLIB。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_backend test_core
```

## 打包

构建说明见 [PACKAGING.md](PACKAGING.md)。当前发布包是 onedir 版本，
解压后运行 `Lull.exe`，需要保留同目录的 `_internal`。

