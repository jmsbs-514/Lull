# 鎵撳寘璇存槑

## 鐜

- Windows 10/11 x64
- Python 3.13
- 椤圭洰渚濊禆宸插畨瑁咃細`pip install -r requirements.txt`
- PyInstaller锛歚pip install pyinstaller`

## 鏋勫缓

```powershell
cd C:\Users\jmsbs\Desktop\Lull
python -m PyInstaller --noconfirm --clean Lull.spec
```

浜х墿锛?
```text
dist\Lull\Lull.exe
dist\Lull\_internal\
```

杩欐槸 **onedir** 鐗堟湰锛屽繀椤讳繚鐣欐暣涓?`Lull` 鏂囦欢澶癸紱涓嶈鍙嫹 `Lull.exe`銆?
## 鍏抽敭鐐?
- 鍏ュ彛鏄?`launcher.py`锛屾棤鎺у埗鍙般€?- `web/` 浼氭墦杩?`_internal/web`锛屾湇鍔＄閫氳繃 `sys._MEIPASS` 璇诲彇銆?- 闊抽閲囬泦浠?`Lull.exe --audio-helper` 瀛愯繘绋嬭繍琛岋紝鍏ュ彛浼氬厛鍒嗘淳杩欎釜鍙傛暟锛?  涓嶄細鍒涘缓绐楀彛鎴栫敵璇峰崟瀹炰緥浜掓枼浣撱€?- `settings.json`銆乣startup.log`銆乣error.log` 鍐欏湪 exe 鍚岀洰褰曪紝鏂逛究渚挎惡浣跨敤銆?- WebView2 鐨?.NET DLL銆亀inrt銆乻oundcard銆乸ycaw銆乸ystray 鐢?`Lull.spec`
  閲岀殑 `collect_all` 鏀惰繘鍘汇€?- 鍥炬爣锛歚assets/lull.ico`銆?
## 鍙戝竷 zip

```powershell
Remove-Item dist\Lull\settings.json, dist\Lull\startup.log, dist\Lull\error.log -ErrorAction SilentlyContinue
Compress-Archive -Path dist\Lull\* -DestinationPath Lull-0.1.1-win64.zip -Force
```

涓嶈鎶婁釜浜?`settings.json` 鎵撹繘鍙戝竷鍖呫€?
## 宸查獙璇?
- 鎵撳寘鐗堣兘鍚姩锛宍/api/debug` 杩斿洖姝ｅ父
- 绐楀彛 804脳100
- `audio_available=true`銆乣audio_spectrum=true`
- 闊抽 helper 杩涚▼涓?`Lull.exe --audio-helper`
- 鏃?`error.log`

