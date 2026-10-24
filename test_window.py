import sys
import webview

mode = sys.argv[1] if len(sys.argv) > 1 else "transparent"

html = """
<html><body style="margin:0;background:transparent;display:flex;align-items:center;
justify-content:center;height:100vh;font-family:sans-serif;">
<div style="font-size:56px;color:#fff;text-shadow:0 2px 10px #000;">测试 TEST 123</div>
</body></html>
"""

if mode == "transparent":
    webview.create_window("probe", html=html, width=700, height=160,
                          x=900, y=1150, frameless=True, transparent=True,
                          on_top=True, shadow=False, background_color="#000000")
else:
    webview.create_window("probe", html=html, width=700, height=160,
                          x=900, y=1150, frameless=True, transparent=False,
                          on_top=True, background_color="#123456")

webview.start()
