# Lull · 开发笔记

> 一个贴在桌面上的歌词层。跟着网易云唱，鼠标点穿，不影响你正在做的事。

---

## 当前交接（2026-10-23）

> 给下一个接手的 agent：先读这一节，再读下面的设计和踩坑记录。

### 当前目标

修复**设置面板里的歌词预览有延迟**的问题。桌面歌词层目前工作正常，
网易云歌词直连链路也必须保留，不要改回其他歌词来源。

**状态：已修复（2026-10-23）。** 下面保留原因记录，修复细节见本节末尾“修复结果”。

### 已确认的代码位置和原因

1. `web/panel.js` 的面板预览每 `900ms` 才请求一次 `/api/state`，
   轮询等待本身最多就会带来接近一秒的延迟。
2. `web/panel.js` 直接用 `m.position` 查找当前歌词，没有使用
   `m.last_updated` 做进度补偿。SMTC 的原始 `position` 本身只约每秒更新一次，
   读到时通常已经滞后 `0.35 ~ 1.3` 秒。
3. `web/lyric.js` 的桌面歌词层已经是 `400ms` 轮询，并在 `nowPos()` 中使用
   `position + (Date.now() / 1000 - last_updated)` 补偿；暂停时直接使用
   `media.position`。面板没有复用这套逻辑，所以两个页面表现不一致。
4. 面板目前没有监听 `visibilitychange`。面板重新显示时不会立刻刷新，
   可能先显示隐藏前的旧歌词，再等下一次轮询。

因此延迟是两层叠加：**面板轮询等待 + SMTC 原始时间戳滞后**。

### 建议修改

- 在 `web/panel.js` 增加与 `web/lyric.js` 等价的 `panelNowPos(m)`。
- 保存 `playing`、当前歌曲身份、`basePos`、`baseAt`；相同歌曲持续播放时
  用 `last_updated` 补偿，时间戳异常时用本地单调时钟续推，暂停时使用原始
  `position`。
- 把面板轮询从 `900ms` 缩到约 `250ms`。
- 监听 `visibilitychange`，面板重新可见时立即执行一次 `tick()`。
- 用补偿后的时间查找 `ly.lines`，翻译匹配和下一句仍以当前歌词行的 `t` 为准。
- 不要改动桌面歌词层的既有行为，只修面板预览。

### 验收标准

- 构造 `position=9.7`、`last_updated=now-0.5`、当前歌词时间 `10.0` 的状态时，
  面板应显示 `10.0` 对应的歌词，而不是上一句。
- 暂停时面板歌词不能继续按时间前进。
- 面板隐藏后重新打开，应立即显示当前歌词，不必等下一次轮询。
- 桌面歌词层、翻译/下一句开关、切歌无歌词清空等既有行为不能回归。
- 实际页面测试后清理只带 `lull-edge-` 标识的无头 Edge 测试进程，
  不要结束用户正在使用的 Edge。

### 修复结果（2026-10-23）

只改了 `web/panel.js`，桌面歌词层未动。

- 轮询 `900ms → 250ms`（`POLL_MS`），用 `busy` 标志防止请求叠加。
- 新增与 `lyric.js` 等价的 `nowPos(m)`：`last_updated` 有效时做
  `position + (now - last_updated)` 补偿；时间戳异常时用
  `basePos + (performance.now() - baseAt) / 1000` 本地续推；暂停返回原始 `position`。
- 记录歌曲身份与 `basePos/baseAt`，切歌或与原始 `position` 偏差超过 2 秒时重置基准。
- `renderPreview()` 统一处理：无歌词清空、纯音乐显示歌名/歌手、翻译和下一句仍按当前行 `t`。
- 监听 `visibilitychange`，面板回到可见时清掉旧定时器并立刻 `tick()`。
- 设置写入加 1.2 秒本地优先窗口，避免 250ms 轮询把正在拖的滑块弹回去。

验证：`node --check` 两个 JS 通过；8 项 Python 测试通过；Node 假 DOM 用例 21 项全过
（补偿、暂停、恢复、无歌词、纯音乐、开关、时间戳异常、隐藏重开、滑块保护）；
无头 Edge 实页四态：`new → NEW`、`paused → OLD / 下一句 NEW`、`empty → 空`、
`pure → 歌名/歌手`。测试用 `lull-edge-panel-test` 进程已清理。

### 环境与测试基线

- 项目没有 Git 仓库，修改前先读文件，不要假设可以回滚。
- 默认的 `python.exe` 目前是 Python 3.14，且没有 `winrt`，**不能用于完整测试**。
- 项目实际环境是：
  `C:\Users\jmsbs\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
  （Python 3.13.14）。
- 完整 Python 测试命令：

  ```powershell
  & 'C:\Users\jmsbs\.workbuddy\binaries\python\envs\default\Scripts\python.exe' -m unittest -v test_backend test_core
  ```

- 2026-10-23 更新本笔记前实测：**8 项测试全部通过**。
- JS 语法检查：

  ```powershell
  node --check web\panel.js
  node --check web\lyric.js
  ```

- 本轮两个 JS 文件均通过语法检查。

---

## 托盘播放卡片（2026-10-24）

一句话：左键托盘切歌词，右键弹一张紧凑横向卡片，能播控，也不抢歌词的风头。

### 结构

- `core/tray.py`：继承 `pystray.Icon`，只覆写 `_on_notify`，左键切歌词、右键开卡片；
  NIM 生命周期和 Explorer 重启仍由 pystray 负责。
- `web/card.html/.css/.js`：360×148 卡片，封面 + 歌名/歌手 + 进度 +
  上一首/播放暂停/下一首 + 主页键 + `⋯`。
- `POST /api/control`：toggle / prev / next / seek。
- `POST /api/card`、`POST /api/visibility`、`POST /api/quit`：卡片开关、歌词显隐、退出。
- `main.py`：card 窗口、`card_position()`（放在托盘光标上方，避开任务栏）、圆角、
  工具窗口、失焦收起。

### 行为

- 右键托盘开/关卡片；左键切歌词显隐。
- 卡片显示时抢焦点，点外面或 Esc 收起；主页键打开设置面板并收起卡片。
- `⋯` 是卡片内菜单：显示/隐藏歌词、锁定（点击穿透）、退出；菜单顶部有“返回”，
  也可以按 Esc 回到播放视图。
- 进度条可点击/拖动，松手才 seek；暂停时用原始 position。
- 卡片跟随 `style` 设置，但只认光影/排版；新歌词样式统一落到光影。
- 重复启动不再静默退出：会把已有实例的主页叫出来；已有实例无响应时弹提示，
  让用户去任务管理器结束 `pythonw.exe`。

### 这次踩的坑

1. **pywebview 的初始窗口尺寸会少一截**：360×148 实际只有 344×109
   （`GetWindowRect` 和 `GetClientRect` 都是），页面被裁。
   解决：`win.show()` 之后调 `win.resize(CARD_W, CARD_H)`；并且**位置要在 resize 之后**
   再放，因为 `BrowserView.resize` 会读 WinForms 的 `Location`，提前 `SetWindowPos`
   会被它拉回 (0,0)。
2. **winrt 的 seek 要 100ns tick**：`try_change_playback_position_async(timedelta)`
   会抛 `TypeError`，要传 `int(seconds * 10_000_000)`。InfLink 的会话支持这个调用。
3. **pystray 没有左右键回调**：默认左右键都走菜单。覆写 `_on_notify` 是最小改动，
   但这是私有 API，所以 `requirements.txt` 锁 0.19.5；升级时要重新验证。
4. **卡片是独立 WebView2**：启动时隐藏，显示/隐藏走 pywebview；失焦由页面
   `blur` 调 `/api/card hide`。
5. **原生 tooltip 会在深色卡片上弹白框**：去掉卡片里所有 `title`，只留 `aria-label`。
6. **卡片不能盖住托盘**：位置按光标（托盘图标）上方算，不按工作区底部。

### 验证

- `node --check web/card.js` 通过；Python 10 项测试通过。
- 无头 Edge：card 在 capsule / editorial / empty 三种状态下的 DOM 和截图正确。
- 真机（网易云 + InfLink）：右键开卡片、左键切歌词、播放/暂停、seek、主页键打开面板、
  菜单显隐歌词/锁定、点外面收起、`/api/quit` 退出，全部实测通过。
- 卡片实测尺寸 360×148，位置在托盘上方。

---

## 调色板（2026-10-24）

目标：让颜色成为可调的一层，但不破坏“默认就好看”。

### 模型

- 三个可空颜色：`ink`（文字/歌词）、`accent`（进度/播放键/编辑框）、
  `surface`（胶囊/卡片底色）。
- **null = 跟随外观**：不写任何 CSS 变量，保持每套 style 原本的颜色。
  老用户升级不受影响；想恢复默认也只需要写回三个 null。
- 6 套预设：夜紫、纸白、暮橙、青瓷、樱、海盐；另有三个自定义取色器。
- 调色板作用于桌面歌词和播放卡片；设置面板保持深色。

### 实现

- `web/color.js`：纯函数（hex 解析、rgba、相对亮度、混色、描边、accent 前景色）。
- `lyric.js`：`ink` 覆盖 `--fg/--fg-sub`，按亮度自动在黑描边/白描边之间切换；
  `accent` 给编辑态边框；`surface` 给 capsule 底色。
- `card.js`：`ink` 覆盖文字/次要文字/分隔线/悬停色；`surface` 覆盖卡片底和封面占位渐变；
  `accent` 覆盖进度和播放键；播放键图标颜色按 accent 亮度自动取黑/白。
  只改背景色没改文字色时，卡片会自动按背景亮度选黑字或白字，避免不可读。
- `settings.py`：三个字段允许 `null` 或 `#rrggbb`，其余一律拒绝。
- 面板：预设色块显示 surface + “Aa” + accent 点；下面三个取色器；
  “恢复默认”写回三个 null。

### 验证

- `node --check` 四个 JS 通过；Python 12 项测试通过
  （新增颜色校验和调色板接口测试）。
- 真机面板：六套色块、选中环、取色器、恢复默认正常；纸白下预览和卡片都变浅色。
- 无头 Edge 计算样式：
  - 纸白：文字 `rgb(26,24,20)`，描边变白；
  - 夜紫：文字 `rgb(245,243,255)`，描边变黑；
  - 青瓷 capsule：`#stage` 背景 `rgb(14,24,23)`；
  - 默认：文字回到白色，surface 回到原 rgba。
- 注意：无头 iframe 里 CSS transition 不推进，`background` 会读到过渡起始值；
  测试时临时禁用 transition 才看到最终色，这是测试现象，不是产品问题。

### 没做

- 设置面板本身不跟随调色板（保持深色工具感）。
- 托盘图标现在是粗体 L，跟随当前 accent；调色板变化时实时重画，不用重启。

---

## 歌词样式（2026-10-24）

- 保留：`glow` 光影、`editorial` 排版。
- 删除：`capsule` 卡片。色键透明下只能用实心块，会盖住壁纸和律动条；
  `surface` 仍留给播放卡片，不再用于歌词。
- 新增：
  - `quiet` 留白：轻阴影、副行退后、字距略开；`--shadow-quiet` 按 ink 亮度自动黑/白。
  - `rail` 细线：`#stage.s-rail` 宽 100%，左对齐，顶部一条 38px accent 线；
    主行宋体 400，副行 0.9 倍字距 0.12em。
- 旧设置里的 `capsule` 会被校验丢弃，回落到默认 `glow`。
- 播放卡片不认新样式，`card.js` 把 `quiet/rail` 映射回 `glow`，不影响遥控器。

### 验证

- 面板四张样式卡正常；留白预览、选中环、主窗口切换正常。
- 真机歌词：留白阴影明显变轻；细线整行左对齐、顶线；面板预览改成直接嵌入
  `lyric.html`，样式和实际窗口同步。
- 17 项 Python 测试、四个 JS 语法通过。

---

## 预设与启动稳定性（2026-10-24）

### 预设

- 4 套：夜航（光影/夜紫/波形）、纸上（排版/纸白/关闭）、
  留白（留白/夜紫/呼吸/50%）、线（细线/夜紫/密集/78%）。
- 一个 patch 同时写 style、ink、accent、surface、rhythm、rhythm_opacity，
  并把 `rhythm_color` 复位为 null（跟随预设的 accent）。
- 面板 2×2 卡片，三个色点 + “样式 · 律动”；六项完全一致才高亮，
  手动改任一项就回到“自定义”。
- 预览仍由实际 `lyric.html` iframe 提供，点预设立即看到效果。

### 启动

- 单实例互斥体在失败时正确 CloseHandle，不再泄漏句柄。
- 启动最多重试 6 次 × 0.4s：先叫现有实例，叫不到就等它释放互斥体后接管；
  解决快速退出/重开时新进程误以为“已有实例”而退出的问题。
- 30 秒启动看门狗：WebView2 窗口仍未就绪时写 `error.log` 并退出，
  避免永久 Not Responding。
- 实测：退出后 1 秒立刻启动，能正常接管并响应。

---

## 窗口与托盘（2026-10-24）

- pywebview 的 frameless 窗口会固定少 16×32。设置里现在存**实际尺寸 804×100**，
  创建时补回 16×32（请求 820×132），实际窗口与设置一致。
- 启动阶段不要强制 `SetWindowPos` 改尺寸；`apply_window_style` 也延迟 2.5 秒，
  否则可能触发 WebView2 启动死锁/Not Responding。
- 运行中整体缩放走 `/api/resize`：保持左上角，`SetWindowPos` 直接改宽高，
  实测安全。面板“区域”宽/高滑杆和歌词右下角拖拽都走它；预览 iframe 按宽高等比缩放。
- 托盘图标改成手工绘制的粗体 L：64×64，圆头，深/浅描边按 accent 亮度切换，
  16px 下仍可辨认；启动时取 `settings.accent`，之后每次 accent 变化都重新生成并赋给
  `tray.icon`，不需要重启。
- 启动链加入阶段日志 `startup.log`、互斥体重试、旧实例退出缓冲和 30 秒看门狗。

---

## 律动条（2026-10-24）

### 观感

- 文字覆盖在声浪上：竖线以**副行和主行之间**为对称轴上下展开，
  满幅时铺满整个歌词矩形高度、到顶到底，文字本体在最上层。
- 6 个选项：关闭 / 波形 / 阶梯 / 细线 / 呼吸 / 镜像；默认关闭，老用户不受影响。
- 播放时跟系统输出响度走；暂停或静音时向中线收缩并淡出，歌词不动。

### 数据

- `core/audio_helper.py` 独立子进程：soundcard + WASAPI loopback 抓系统输出，
  numpy 做 2048 点 FFT，按对数切 **32 段**（30–12000Hz），每行输出 `{v, bands, spectrum}`。
  只读系统输出，不录麦克风。
- `core/audio.py` 只负责启动子进程、读 JSON 行和看门狗；WASAPI/COM/numpy 都不进 pywebview 进程。
  没有 soundcard 时子进程退回 pycaw 总峰值，bands 全填同一个值。
- 参考两个现成实现：
  - 当前壁纸（Wallpaper Engine 3817518265）用 `g_AudioSpectrum16Left/Right[16]`，
    柱子高度 `mix(lower_bound, upper_bound, volume)`，固定 0～0.5，不做逐段 AGC；
    脚本只做 `smoothValue += delta * frametime * smoothingRate`，默认 20。
  - CatBot3 Audio Visualizer 是**一整行对数频谱**：每根柱子直接采一个对数频率点对应的
    FFT bin，`energy = byte / 255`，`height = energy * h`，没有对称、没有逐段增益。
- 我们对应改成：固定 dB 映射（-65～-20dB）、32 段、轻微高频倾斜、无逐段 AGC；
  每根柱子直接用中心频率对应的 FFT bin，不再按区间平均，避免低频段出现空洞。
  总响度映射到 -45～0dB，只控制淡入淡出；上升 0.8、回落 0.25。
- **COM 坑（重要）**：pycaw/comtypes 不能在主线程导入；若退回峰值方案，音频线程必须用
  `CoInitializeEx(COINIT_MULTITHREADED)`。现在主路径是独立子进程，主进程完全隔离。

### 渲染

- **不再左右对称**：一整行从 30Hz 到 12kHz 铺满歌词宽度，柱子从底部向上长，低频在左、高频在右。
- 32 段插值成 48 根波形柱；阶梯 32 根、细线 64 根、呼吸 24 根、密集 56 根。
- 每根柱子高度就是该频段的原始能量 × 歌词层高度，不再乘总响度，也不加固定底；
  没有信号的频段直接是 0（和 CatBot3 一样）。
- `rhythm_opacity` 默认 1.0，范围 0.1–1.0；它乘在容器淡入淡出上，
  各样式自己的基础透明度（0.35–0.68）不变。面板滑杆范围 10–100%。
- `rhythm_color` 可空：`null` 跟随强调色，自定义 hex 时写 `--rhythm-color`，
  律动条和光影的 bar glow 都用它；面板“跟随强调色”可复位。
- 阴影按样式拆，避免光影的重阴影串到其他外观：
  - `glow`：52px 大黑晕
  - `editorial`：32px 中等阴影
  - `quiet`：6px 轻阴影
  - `rail`：8px 紧阴影
  - 基础层用 32px medium，未知样式也不会退回光影。
- 文字阴影拆成独立层：shadow `z-index:0` → 律动条 `z-index:1` → 文字 `z-index:2`。
- **影框坑（已修）**：阴影层继承了 `.line { overflow:hidden }`，52px 大模糊会被裁成
  文字行框大小的矩形，看起来像在字上盖了一个影框。阴影层单独设 `overflow:visible`，
  只让主文字继续裁切。
- 面板预览直接嵌入 `lyric.html`，和实际歌词层同步；选择实时保存。
  默认 `rhythm: "off"`；色调取 accent。

### 验证

- 17 项 Python 测试通过；四个 JS 语法通过。
- 区域缩放：面板 804→900 宽、100→160 高的预览同步；拖拽右下角实测到 904×150。
- 真机 app `/api/level` 返回 32 段；通知音 `v=0.572`，低频段有值、高频段为 0。
- 面板“律动透明度”滑杆实测 40% 正常保存、重载后保持；默认 100%。
- “律动颜色”实测自定义 `#ff6b6b` 后条子变色，点“跟随强调色”恢复 null。
- 假数据 32 段铺满 820px 歌词层截图：柱子从左到右独立变化，左侧低频高、右侧高频低，
  不再是一整排同高，也不是左右镜像。
- 独立合成鼓点此前验证过：`v` 平均 0.635、最高 0.844，没有一帧 ≥0.95；
  现在柱子高度由频段直接决定，总响度只影响淡入淡出。

### 没做

- 频段增益/灵敏度还没有面板开关，先看实际听感再调。
- 子进程在强制结束应用（非正常退出）时可能留一个音频 helper，需要后续加父进程守护。

---

## 为什么做这个

网易云自带的桌面歌词：黄色字、黑色描边、飘在屏幕中下、二十年没怎么变过。
能调的东西只有颜色和字号，调半天也调不出好看的。

所以想做一个**只有两件事做得好**的：好看，以及不打扰。

不是做一个功能更全的歌词软件（Lyricify、TaskbarLyrics 已经很全了），
是把「好看」这一件事做到位。

---

## 核心设计

### 三层

| 层 | 做什么 |
|---|---|
| 引擎 | 问系统在放什么、去网上找歌词、算出现在该唱哪句 |
| 窗口 | 一层透明浮层，只负责画画，不占地方不抢焦点 |
| 外观 | 决定它长什么样（这是还没做完的部分） |

### 双行结构

```
      上面小字：有翻译放翻译 / 没翻译放下一句
      下面大字：原文当前句
```

一行空间两用，不浪费高度。

### 两种状态

- **锁定**：`WS_EX_TRANSPARENT` 点穿，色键透明，屏幕上只剩文字。常态。
- **编辑**：切半透明模式，整块变成半透明深灰，看得见边界，整块能按住拖。

---

## 技术栈

```
Python 3.13
pywebview 6.2.1       窗口壳（WebView2）
winrt-*               读 Windows 媒体会话（SMTC）
pystray + Pillow      托盘
requests              歌词接口

前端 HTML / CSS / JS，不打包不构建
界面和 Python 之间走本地 HTTP：127.0.0.1:48710
```

为什么不用 pywebview 的 `js_api`：pythonnet 序列化 WinForms 控件属性会无限递归，
报 `maximum recursion depth exceeded`，刷屏。改走 HTTP 反而更简单可控。

---

## 前置依赖（重要）

**网易云原版根本不向 Windows 上报播放状态。** 实测：

- 监控 SMTC 15 秒，会话数一直是 0
- 用 UI Automation 读它的控件树，窗口 ClassName 是 `OrpheusBrowserHost`，
  整块界面是自绘的，一个控件都读不到
- 只有窗口标题是干净的 `歌名 - 歌手`

所以必须装社区插件让它开口说话：

1. **BetterNCM Installer 1.2.0** —— 往网易云安装目录写 `msimg32.dll`（DLL 劫持）
2. **InfLink-rs 3.4.0** —— BetterNCM 插件，把播放状态发布到 SMTC

InfLink-rs 官方测试过的网易云版本是 **V3 3.1.20 ~ 3.1.41**，
本机 `3.1.41.205529` 正好在范围内。

装完之后能拿到：歌名、多歌手（`/` 分隔）、专辑、封面 JPEG、播放状态、
播放进度（每秒一次）、**歌曲 ID（藏在 genres 字段，格式 `NCM-{id}`）**、
播放/暂停/上一首/下一首/跳转 控制。

> 那个歌曲 ID 是关键。有它，找歌词是按 ID 精确查，不会出现"同名歌匹配到别人翻唱"。
> 没有它，只能拿歌名去猜。

---

## 数据链路

```
SMTC（InfLink 上报）
  → 歌名 / 歌手 / 专辑 / 封面 / 进度 / last_updated / NCM-ID
  → 网易云歌词接口  https://music.163.com/api/song/lyric?id={id}&lv=1&kv=1&tv=-1
      需要 Referer: https://music.163.com/ 和 Cookie: appver=8.9.70; os=pc
      返回 LRC 原文 + tlyric 翻译
      纯音乐会返回 pureMusic: true、歌词为空
  → LRC 解析成 [{t, s}] 数组
  → 前端按进度二分查找当前行
```

拿不到歌词时降级到 LRCLIB（`https://lrclib.net/api/get`，按歌名+歌手+时长查）。

---

## 踩过的坑（下次别再踩）

### 1. WebView2 整块黑屏

GPU 加速在这台机器上（RTX 5070）和 WebView2 不对付，窗口纯黑、内容不渲染。

```
WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--disable-gpu --no-sandbox
```
必须**在 import webview 之前**设置。

### 2. pywebview 的透明不完整

`transparent=True` 只让 WebView2 不画背景，WinForms 的窗体背景仍是 Control 色
`#F0F0F0`，露出一块灰底。

`window.native` 是 `None`，`BrowserView.instances` 也取不到窗体。能拿到的是：

```python
from System.Windows.Forms import Application
for form in Application.OpenForms:
    if form.Text == "Lull":     # 必须按标题过滤，否则会把面板窗口也涂黑
        form.BackColor = Color.Black
```

然后把纯黑当色键抠掉：

```python
SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
SetLayeredWindowAttributes(hwnd, 0x000000, 255, LWA_COLORKEY)
```

得到真正的 per-pixel 透明。**代价**：页面里所有半透明元素都会被"混黑后抠掉"，
所以胶囊背景只能做实心色。

### 3. 色键透明的地方点不到

同理，抠成透明的像素鼠标直接穿过去。等于整个窗口**只有文字笔画能点**，没法拖。

解锁时切换成 `LWA_ALPHA`(132) 半透明模式，整块变成半透明深灰，整块可点。
锁定再切回 colorkey。

### 4. 系统拖动循环用不了

`ReleaseCapture` + `WM_NCLBUTTONDOWN` 要求那一刻左键还在按下。
但从页面 mousedown 到 Python 拿到请求隔了一次 HTTP 往返，手常常已经松了。

改成自己跟着鼠标走：起线程，`GetCursorPos` 轮询 + `SetWindowPos` 跟随，
用 `GetAsyncKeyState(0x01)` 判断左键是否还按着，间隔 8ms。

### 5. 歌词慢半拍、每秒跳一格

SMTC 的 `position` **每秒才更新一次**，读到的值滞后 0.35 ~ 1.3 秒：

```
现在时刻      进度值      这条进度的测量时间    相差
470.979      46.67       470.138              0.84 秒
471.779      46.67       470.138              1.64 秒
472.580      48.65       472.132              0.45 秒
```

但每条进度都带一个 `last_updated_time`。用它补偿：

```
真实进度 = position + (现在 - last_updated)
```

补偿后每 0.4 秒采样精确前进 0.400，误差 2 毫秒级。

### 6. Windows 允许一个端口被多个进程绑定

`SO_REUSEADDR` 在 Windows 上的行为和 Linux 不同，靠"端口是否被占用"判断单实例
完全失效，双击两次就是两个程序在跑、两行字叠在一起。

用命名互斥体：

```python
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
h = kernel32.CreateMutexW(None, False, "LullDesktopLyrics")
already = ctypes.get_last_error() == 183   # ERROR_ALREADY_EXISTS
```

注意：`Global\` 前缀会因权限失败，用不带前缀的名字。

### 7. 字号滑块没反应

自动缩放函数把字号写成了**行内样式**，盖住了 CSS 变量。改字号时 CSS 变量变了，
但行内样式还压着。

修法：每次字号变化先按新值重排，再用一个隐藏 span 精确测量文字宽度决定要不要缩
（不靠 `scrollWidth`，它对 `max-width` 约束下的元素不可靠）。

### 8. 调滑块时窗口跟着动

pywebview 对 frameless 窗口默认 `easy_drag=True`，整块都能拖，拖滑块等于拖窗口。
面板要设 `easy_drag=False`，只让标题栏那条能拖（走 `/api/panel` 的 drag）。

### 9. 开发测试时的坑

- 从这个环境启动的 GUI 进程活不过一轮对话，会被回收。
  **所以要启动程序让人手动双击 `启动.bat`**，否则托盘里留一个点不动的空壳图标。
- 强杀进程不会清理托盘图标，会留幽灵。托盘"退出"要走 `icon.stop()`。
- `GetWindowRect` 跨进程时用 `wt.HWND(hwnd)` 包装会失败返回 0，
  直接传 `ctypes.c_void_p(hwnd)`。

---

## 文件结构

```
lull/
├── launcher.py             无控制台安全入口，记录导入阶段异常
├── main.py                 主入口：窗口、托盘、单实例、透明、拖动
├── core/
│   ├── smtc.py             读系统媒体会话 + 播放控制
│   ├── audio.py            音频子进程管理（律动条用）
│   ├── audio_helper.py     子进程：WASAPI 回环 + FFT 五段频谱
│   ├── lyrics.py           网易云/LRCLIB 取词 + LRC 解析 + 缓存
│   ├── server.py           本地 HTTP + 静态文件
│   ├── tray.py             托盘图标（左键歌词、右键卡片）
│   └── settings.py         设置持久化
├── web/
│   ├── lyric.html/.css/.js 桌面歌词层
│   ├── panel.html/.css/.js 总控面板
│   ├── card.html/.css/.js  托盘播放卡片
│   └── color.js            调色板颜色工具
├── settings.json           运行时生成
├── requirements.txt        Python 依赖
├── README.md               安装、启动和使用说明
├── 启动.bat                双击启动（pythonw，无窗口）
├── test_backend.py         HTTP 与控制器回归测试
├── test_core.py            设置、LRC、SMTC 选择回归测试
├── probe.py / test_window.py 早期技术验证脚本，可删
└── engine_test.py          命令行版歌词对齐验证，可删
```

---

## 已完成

- [x] SMTC 读取（歌名/歌手/专辑/封面/进度/歌曲 ID/播放状态）
- [x] 网易云按 ID 取词，带翻译，纯音乐识别，LRCLIB 降级
- [x] 进度时间戳补偿，切句精确到几十毫秒
- [x] 透明歌词层：置顶、点穿、无边框、只剩文字
- [x] 双行：原文 + 翻译/下一句，切句淡入上移
- [x] 播放暂停、停止或播放器退出时保留最后一屏歌词
- [x] 编辑态：半透明可拖，松手保存位置
- [x] 总控面板：四套歌词样式、字号、副行字号、不透明度、翻译开关、位置调整
- [x] 歌词样式：光影/排版/留白/细线；移除卡片，播放卡片自动映射回光影
- [x] 托盘：左键歌词显隐、右键播放卡片；卡片内可显隐歌词/锁定/退出
- [x] 播放卡片：封面、歌名/歌手、进度拖动、上一首/播放暂停/下一首、主页键
- [x] 卡片跟随光影/排版；新歌词样式在卡片里统一落到光影
- [x] 调色板：6 套预设 + 自定义文字/强调/背景色，默认跟随外观
- [x] 窗口实际尺寸与设置统一：804×100（创建时补 pywebview 的 16×32）
- [x] 整体区域缩放：面板宽/高 + 右下角拖拽 + 预览等比同步
- [x] 托盘改成粗体 L，跟随 accent 实时刷新
- [x] 全屏自动隐藏：按你的意见不做
- [x] 律动颜色、律动透明度、一键预设
- [x] 启动重试 + 旧实例缓冲 + 30 秒看门狗 + `startup.log` 阶段日志
- [x] 律动条：5 种整行频谱 + 32 段真频谱 + 静音收缩 + 透明度 + 颜色，默认关闭
- [x] 一键预设：夜航/纸上/留白/线，一次写样式、配色、律动和透明度
- [x] 启动重试（6×0.4s）+ 30 秒看门狗，处理快速重启和 WebView2 卡死
- [x] 单实例、无控制台启动、异常写 `error.log`
- [x] 切歌到无歌词歌曲时清空旧歌词、翻译/下一句开关正常生效
- [x] 多播放器时优先选择正在播放的 SMTC 会话
- [x] 设置类型/范围校验与原子写入
- [x] “回到屏幕中央”移动到真正的屏幕中央
- [x] 切换外观后重新适配长歌词
- [x] 网易云/LRCLIB HTTPS 证书正常校验
- [x] 后端、设置、LRC、SMTC 自动回归测试
- [x] 设置面板预览延迟修复（250ms 轮询 + 进度补偿 + 可见即刷新）
- [x] 面向使用者的 `README.md`

## 还没做完

- [ ] **四套歌词样式继续打磨** —— 光影、排版、留白、细线已经能选，
      下一步是长句、花壁纸、浅色壁纸下的稳定性和细节。
- [ ] 律动条的频段增益/灵敏度设置（先看实际听感）
- [ ] 面板的圆角、过渡动效（现在点开关是硬跳）
- [ ] 多显示器支持 / 高 DPI
- [ ] 区域缩放的边缘吸附/最小尺寸提示
- [ ] 开机自启
- [ ] 打包成 exe（PyInstaller）——下一步
- [ ] 开 GitHub 仓库

---

## 下一步的顺序

1. ~~修复设置面板歌词预览延迟，并完成回归验证~~（已完成）
2. 把四套歌词样式做到「看一眼就想用」
3. 面板细节打磨
4. 打包 + 开 GitHub 仓库 + 发布

第 1 步已完成；之后的第 2、3 步决定它值不值得被发出去，最后一步才是发布。
