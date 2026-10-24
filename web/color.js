/* 调色板用的纯函数：解析、混色、亮度、描边。 */
window.LullColor = (function () {
  function parse(hex) {
    if (typeof hex !== "string") return null;
    const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function rgba(hex, alpha) {
    const c = parse(hex);
    if (!c) return "";
    return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${alpha})`;
  }

  function lum(hex) {
    const c = parse(hex);
    if (!c) return 1;
    const v = c.map((x) => {
      const n = x / 255;
      return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
  }

  function mix(a, b, t) {
    const ca = parse(a);
    const cb = parse(b);
    if (!ca || !cb) return a || b || "";
    const out = ca.map((x, i) => Math.round(x + (cb[i] - x) * t));
    return "#" + out.map((x) => x.toString(16).padStart(2, "0")).join("");
  }

  // 浅色字配黑描边，深色字配白描边。
  function shadows(hex) {
    if (lum(hex) <= 0.55) {
      return {
        main: "0 1px 2px rgba(255,255,255,.95), 0 0 12px rgba(255,255,255,.7), 0 0 30px rgba(255,255,255,.4)",
        sub: "0 1px 2px rgba(255,255,255,.9), 0 0 10px rgba(255,255,255,.55)",
        medium: "0 1px 2px rgba(255,255,255,.95), 0 0 14px rgba(255,255,255,.7), 0 0 32px rgba(255,255,255,.35)",
        mediumSub: "0 1px 2px rgba(255,255,255,.9), 0 0 10px rgba(255,255,255,.55)",
        tight: "0 1px 2px rgba(255,255,255,.9), 0 0 8px rgba(255,255,255,.42)",
        tightSub: "0 1px 2px rgba(255,255,255,.85), 0 0 6px rgba(255,255,255,.34)",
        quiet: "0 1px 2px rgba(255,255,255,.9), 0 0 6px rgba(255,255,255,.35)",
        quietSub: "0 1px 2px rgba(255,255,255,.85), 0 0 5px rgba(255,255,255,.28)",
      };
    }
    return {
      main: "0 1px 2px rgba(0,0,0,.95), 0 0 10px rgba(0,0,0,.85), 0 0 26px rgba(0,0,0,.62), 0 0 52px rgba(0,0,0,.35)",
      sub: "0 1px 2px rgba(0,0,0,.95), 0 0 9px rgba(0,0,0,.8), 0 0 20px rgba(0,0,0,.5)",
      medium: "0 1px 2px rgba(0,0,0,.95), 0 0 14px rgba(0,0,0,.7), 0 0 32px rgba(0,0,0,.35)",
      mediumSub: "0 1px 2px rgba(0,0,0,.9), 0 0 10px rgba(0,0,0,.55)",
      tight: "0 1px 2px rgba(0,0,0,.9), 0 0 8px rgba(0,0,0,.42)",
      tightSub: "0 1px 2px rgba(0,0,0,.85), 0 0 6px rgba(0,0,0,.34)",
      quiet: "0 1px 2px rgba(0,0,0,.9), 0 0 6px rgba(0,0,0,.4)",
      quietSub: "0 1px 2px rgba(0,0,0,.85), 0 0 5px rgba(0,0,0,.32)",
    };
  }

  function accentFg(hex) {
    return lum(hex) > 0.6 ? "#14121c" : "#ffffff";
  }

  function danger(hex) {
    return lum(hex) > 0.55 ? "#a3372f" : "#ff8b8b";
  }

  return { parse, rgba, lum, mix, shadows, accentFg, danger };
})();
