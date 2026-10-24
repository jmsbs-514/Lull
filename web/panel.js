const STYLES = [
  { id: "glow", name: "光影", glyph: "光" },
  { id: "editorial", name: "排版", glyph: "文" },
  { id: "quiet", name: "留白", glyph: "白" },
  { id: "rail", name: "细线", glyph: "线" },
];

const PRESETS = [
  {
    id: "night", name: "夜航", style: "glow",
    ink: "#f5f3ff", accent: "#a996ff", surface: "#0a0910",
    rhythm: "wave", rhythm_opacity: 1.0,
  },
  {
    id: "paper", name: "纸上", style: "editorial",
    ink: "#1a1814", accent: "#1a1814", surface: "#f3efe7",
    rhythm: "off", rhythm_opacity: 1.0,
  },
  {
    id: "quiet", name: "留白", style: "quiet",
    ink: "#f5f3ff", accent: "#a996ff", surface: "#0a0910",
    rhythm: "breath", rhythm_opacity: 0.5,
  },
  {
    id: "rail", name: "线", style: "rail",
    ink: "#f5f3ff", accent: "#a996ff", surface: "#0a0910",
    rhythm: "mirror", rhythm_opacity: 0.78,
  },
];

const PALETTES = [
  { name: "夜紫", ink: "#f5f3ff", accent: "#a996ff", surface: "#0a0910" },
  { name: "纸白", ink: "#1a1814", accent: "#1a1814", surface: "#f3efe7" },
  { name: "暮橙", ink: "#fff1e6", accent: "#ff9e6d", surface: "#1a1210" },
  { name: "青瓷", ink: "#eaf7f4", accent: "#6fd3c7", surface: "#0e1817" },
  { name: "樱", ink: "#fff0f4", accent: "#ff9db6", surface: "#1c1116" },
  { name: "海盐", ink: "#edf4ff", accent: "#7fb7ff", surface: "#0d1420" },
];

const BASE_COLORS = { ink: "#ffffff", accent: "#a996ff", surface: "#16141f" };

const RHYTHMS = [
  { id: "off", name: "关闭" },
  { id: "wave", name: "波形" },
  { id: "steps", name: "阶梯" },
  { id: "hairline", name: "细线" },
  { id: "breath", name: "呼吸" },
  { id: "mirror", name: "密集" },
];

const RHYTHM_GLYPHS = {
  off: [2],
  wave: [8, 14, 22, 14, 8],
  steps: [8, 16, 10, 16, 8],
  hairline: [6, 10, 14, 8, 12, 6],
  breath: [12, 12, 12, 12, 12],
  mirror: [8, 14, 10, 18, 12, 16, 9, 13, 7],
};

let pvRhythmType = "";

const POLL_MS = 250;
const DRIFT_LIMIT = 2.0;
const TRUST_WINDOW = 3.0;
const PENDING_MS = 1200;

let S = {};
let media = null;
let playing = false;
let basePos = 0;
let baseAt = 0;
let pending = {};
let pollTimer = null;
let busy = false;

const $ = (id) => document.getElementById(id);

document.querySelector(".bar").addEventListener("mousedown", (e) => {
  if (e.target.closest(".x")) return;
  post("/api/panel", { action: "drag" });
});

function post(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  }).then((r) => r.json());
}

function buildStyles() {
  const box = $("styles");
  box.innerHTML = "";
  STYLES.forEach((s) => {
    const el = document.createElement("div");
    el.className = "style-card" + (S.style === s.id ? " on" : "");
    el.dataset.id = s.id;
    el.innerHTML = `<div class="glyph">${s.glyph}</div><div class="name">${s.name}</div>`;
    el.addEventListener("click", () => save({ style: s.id }));
    box.appendChild(el);
  });
}

function buildPresets() {
  const box = $("presets");
  box.innerHTML = "";
  PRESETS.forEach((p) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "preset" + (activePreset() === p ? " on" : "");
    btn.dataset.id = p.id;
    const styleName = (STYLES.find((s) => s.id === p.style) || {}).name || "";
    const rhythmName = (RHYTHMS.find((r) => r.id === p.rhythm) || {}).name || "";
    btn.innerHTML =
      `<span class="pdots">` +
      `<i style="background:${p.ink}"></i>` +
      `<i style="background:${p.accent}"></i>` +
      `<i style="background:${p.surface}"></i>` +
      `</span><span class="ptext"><b>${p.name}</b>` +
      `<em>${styleName} · ${rhythmName}</em></span>`;
    btn.addEventListener("click", () => save(presetPatch(p)));
    box.appendChild(btn);
  });
}

function presetPatch(p) {
  return {
    style: p.style,
    ink: p.ink,
    accent: p.accent,
    surface: p.surface,
    rhythm: p.rhythm,
    rhythm_opacity: p.rhythm_opacity,
    rhythm_color: null,
  };
}

function activePreset() {
  return PRESETS.find((p) =>
    S.style === p.style &&
    sameColor(S.ink, p.ink) &&
    sameColor(S.accent, p.accent) &&
    sameColor(S.surface, p.surface) &&
    S.rhythm === p.rhythm &&
    !S.rhythm_color &&
    Math.abs((S.rhythm_opacity ?? 1) - p.rhythm_opacity) < 0.005) || null;
}

function buildPalettes() {
  const box = $("palettes");
  box.innerHTML = "";
  PALETTES.forEach((p, idx) => {
    const cell = document.createElement("div");
    cell.className = "palette-cell";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "palette";
    btn.dataset.idx = String(idx);
    btn.style.background = p.surface;
    btn.style.color = p.ink;
    btn.innerHTML =
      `<span>Aa</span><span class="pdot" style="background:${p.accent}"></span>`;
    btn.setAttribute("aria-label", p.name);
    btn.addEventListener("click", () =>
      save({ ink: p.ink, accent: p.accent, surface: p.surface }));

    const name = document.createElement("div");
    name.className = "pname";
    name.textContent = p.name;

    cell.appendChild(btn);
    cell.appendChild(name);
    box.appendChild(cell);
  });
}

function currentColors() {
  return {
    ink: S.ink || BASE_COLORS.ink,
    accent: S.accent || BASE_COLORS.accent,
    surface: S.surface || BASE_COLORS.surface,
  };
}

function sameColor(a, b) {
  return String(a || "").toLowerCase() === String(b || "").toLowerCase();
}

function activePalette() {
  return PALETTES.find((p) =>
    sameColor(S.ink, p.ink) &&
    sameColor(S.accent, p.accent) &&
    sameColor(S.surface, p.surface)) || null;
}

function buildRhythms() {
  const box = $("rhythms");
  box.innerHTML = "";
  RHYTHMS.forEach((r) => {
    const el = document.createElement("div");
    el.className = "rhythm-card" + (S.rhythm === r.id ? " on" : "");
    el.dataset.id = r.id;

    const glyph = document.createElement("div");
    glyph.className = "rhythm-glyph";
    (RHYTHM_GLYPHS[r.id] || []).forEach((height) => {
      const bar = document.createElement("i");
      bar.style.height = height + "px";
      if (r.id === "off") bar.style.width = "14px";
      if (r.id === "hairline") bar.style.width = "1px";
      glyph.appendChild(bar);
    });

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = r.name;

    el.appendChild(glyph);
    el.appendChild(name);
    el.addEventListener("click", () => save({ rhythm: r.id }));
    box.appendChild(el);
  });
}

function buildPreviewRhythm() {
  const type = S.rhythm || "off";
  const box = $("pvRhythm");
  if (type === pvRhythmType) return;
  pvRhythmType = type;
  box.innerHTML = "";
  if (type === "off") {
    box.style.display = "none";
    return;
  }
  box.style.display = "flex";
  (RHYTHM_GLYPHS[type] || []).forEach((height, i) => {
    const bar = document.createElement("i");
    bar.style.height = Math.max(6, height * 0.6) + "px";
    bar.style.animationDelay = (i * 0.08) + "s";
    if (type === "hairline") bar.style.width = "1px";
    box.appendChild(bar);
  });
}

function updatePreviewArea(width, height) {
  const frame = $("pvFrame");
  const box = $("preview");
  if (!frame || !box) return;
  const bw = Math.max(80, box.clientWidth - 16);
  const bh = Math.max(50, box.clientHeight - 16);
  const scale = Math.min(bw / width, bh / height, 1);
  frame.style.width = width + "px";
  frame.style.height = height + "px";
  frame.style.transform = `scale(${scale})`;
}

function apply() {
  document.querySelectorAll(".style-card").forEach((el) => {
    el.classList.toggle("on", el.dataset.id === S.style);
  });

  $("fontSize").value = S.font_size;
  $("fontSizeVal").textContent = S.font_size;
  $("subSize").value = S.sub_size;
  $("subSizeVal").textContent = S.sub_size;
  $("opacity").value = Math.round((S.opacity || 0.92) * 100);
  $("opacityVal").textContent = Math.round((S.opacity || 0.92) * 100) + "%";
  $("showTranslation").checked = !!S.show_translation;
  $("showNext").checked = !!S.show_next;
  $("areaWidth").value = S.width || 804;
  $("areaHeight").value = S.height || 100;
  $("areaWidthVal").textContent = (S.width || 804) + "px";
  $("areaHeightVal").textContent = (S.height || 100) + "px";
  updatePreviewArea(S.width || 804, S.height || 100);

  const main = $("pvMain");
  const sub = $("pvSub");
  main.style.fontSize = Math.min(S.font_size, 26) + "px";
  sub.style.fontSize = Math.min(S.sub_size, 13) + "px";
  document.querySelector(".preview-inner").style.opacity = S.opacity || 0.92;

  const colors = currentColors();
  $("inkColor").value = colors.ink;
  $("accentColor").value = colors.accent;
  $("surfaceColor").value = colors.surface;
  $("inkVal").textContent = colors.ink.toUpperCase();
  $("accentVal").textContent = colors.accent.toUpperCase();
  $("surfaceVal").textContent = colors.surface.toUpperCase();
  const rhythmColor = typeof S.rhythm_color === "string"
    ? S.rhythm_color : colors.accent;
  $("rhythmColor").value = rhythmColor;
  $("rhythmColorVal").textContent = rhythmColor.toUpperCase();
  $("rhythmColorHint").textContent = S.rhythm_color ? "自定义" : "跟随强调色";
  $("rhythmColorReset").disabled = !S.rhythm_color;

  const active = activePalette();
  document.querySelectorAll(".palette").forEach((el) => {
    el.classList.toggle("on", !!active && PALETTES[Number(el.dataset.idx)] === active);
  });
  $("paletteHint").textContent = active
    ? active.name
    : (S.ink || S.accent || S.surface ? "自定义" : "跟随外观");

  document.querySelectorAll(".rhythm-card").forEach((el) => {
    el.classList.toggle("on", el.dataset.id === (S.rhythm || "off"));
  });
  const rhythmAlpha = Math.round(
    (typeof S.rhythm_opacity === "number" ? S.rhythm_opacity : 1) * 100);
  $("rhythmOpacity").value = rhythmAlpha;
  $("rhythmOpacityVal").textContent = rhythmAlpha + "%";
  const preset = activePreset();
  document.querySelectorAll(".preset").forEach((el) => {
    el.classList.toggle("on", !!preset && el.dataset.id === preset.id);
  });
  buildPreviewRhythm();
  if ((S.rhythm || "off") !== "off") {
    document.querySelectorAll("#pvRhythm i").forEach((bar) => {
      bar.style.background = S.accent || "";
    });
  }

  main.style.color = colors.ink;
  sub.style.color = LullColor.rgba(colors.ink, 0.72);
  const shadow = LullColor.shadows(colors.ink);
  let mainShadow = shadow.main;
  let subShadow = shadow.sub;
  if (S.style === "quiet") {
    mainShadow = shadow.quiet;
    subShadow = shadow.quietSub;
  }
  main.style.textShadow = mainShadow;
  sub.style.textShadow = subShadow;
  sub.style.opacity = S.style === "quiet" ? "0.64" : "1";
  sub.style.letterSpacing = S.style === "rail" ? "0.12em" : "0.03em";

  const preview = $("preview");
  if (S.surface) {
    const light = LullColor.lum(S.surface) > 0.55;
    const overlay = light
      ? "radial-gradient(120% 140% at 20% 10%, rgba(255,255,255,0.55), transparent 55%), " +
        "radial-gradient(100% 120% at 85% 90%, rgba(255,255,255,0.32), transparent 60%)"
      : "radial-gradient(120% 140% at 20% 10%, rgba(255,255,255,0.06), transparent 55%), " +
        "radial-gradient(100% 120% at 85% 90%, rgba(169,150,255,0.12), transparent 60%)";
    preview.style.background = overlay + ", " + S.surface;
  } else {
    preview.style.removeProperty("background");
  }

  const tag = $("previewTag");
  if (S.ink || S.surface) {
    const tagInk = S.ink ||
      (LullColor.lum(S.surface) > 0.55 ? "#1a1814" : "#ffffff");
    tag.style.color = LullColor.rgba(tagInk, 0.42);
  } else {
    tag.style.removeProperty("color");
  }

  const serif = S.style === "editorial" || S.style === "rail";
  main.style.fontFamily = serif
    ? '"Songti SC","Noto Serif SC","Source Han Serif SC","SimSun",serif'
    : "inherit";
  main.style.letterSpacing = S.style === "editorial" ? "0.09em"
    : S.style === "rail" ? "0.07em"
    : S.style === "quiet" ? "0.018em" : "0.012em";
  main.parentElement.style.background = "transparent";
  main.parentElement.style.padding = S.style === "rail" ? "0 0 0 24px" : "0";
  main.parentElement.style.textAlign = S.style === "rail" ? "left" : "center";
  main.parentElement.style.borderRadius = "0";
  main.parentElement.style.setProperty("--accent", colors.accent);
  $("pvRule").style.display = S.style === "rail" ? "block" : "none";
  const frame = $("pvFrame");
  if (frame && frame.dataset.style !== S.style) {
    frame.dataset.style = S.style;
    frame.src = "/lyric.html?preview=" + encodeURIComponent(S.style) + "&t=" + Date.now();
  }
  main.parentElement.classList.remove("pv-glow", "pv-editorial", "pv-quiet", "pv-rail");
  main.parentElement.classList.add("pv-" + S.style);

  $("posHint").textContent = S.locked
    ? "当前锁定，鼠标可以穿过歌词层。"
    : "已解锁，可以直接拖动桌面上的歌词。";
  $("unlock").textContent = S.locked ? "调整位置" : "锁定";
  $("unlock").classList.toggle("primary", !S.locked);
}

function save(patch) {
  Object.assign(S, patch);
  const until = Date.now() + PENDING_MS;
  for (const key of Object.keys(patch)) pending[key] = { value: patch[key], until };
  apply();
  post("/api/settings", patch);
}

// 本地刚改过的值在服务器回包前优先，免得 250ms 轮询把滑块弹回去。
function mergeSettings(incoming) {
  const merged = Object.assign({}, incoming || {});
  const t = Date.now();
  for (const key of Object.keys(pending)) {
    if (pending[key].until > t) merged[key] = pending[key].value;
    else delete pending[key];
  }
  return merged;
}

function sameSong(a, b) {
  if (!a || !b) return false;
  return a.song_id === b.song_id && a.title === b.title;
}

// 与 lyric.js 的 nowPos 等价：SMTC 的 position 每秒才更新一次，
// 用 last_updated 做进度补偿；时间戳异常时靠本地单调时钟续推；暂停用原始值。
function nowPos(m) {
  const cur = m || media;
  if (!cur || !cur.available) return 0;
  if (!playing) return cur.position;
  const lu = cur.last_updated;
  if (lu > 0) {
    const elapsed = Date.now() / 1000 - lu;
    if (elapsed >= -0.5 && elapsed <= TRUST_WINDOW) {
      return cur.position + elapsed;
    }
  }
  return basePos + (performance.now() - baseAt) / 1000;
}

function indexAt(arr, t) {
  let lo = 0, hi = arr.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid].t <= t) { ans = mid; lo = mid + 1; }
    else hi = mid - 1;
  }
  return ans;
}

function renderPreview(m, ly) {
  const main = $("pvMain");
  const sub = $("pvSub");

  // 播放器退出时保留最后一屏，和桌面歌词层一致。
  if (!m || !m.available) return;

  const lines = (ly && ly.lines) || [];
  if (!lines.length) {
    main.textContent = ly && ly.pure_music ? (m.title || "") : "";
    sub.textContent = ly && ly.pure_music ? (m.artist || "") : "";
    return;
  }

  const i = indexAt(lines, nowPos(m));
  if (i < 0) {
    main.textContent = "";
    sub.textContent = "";
    return;
  }

  const cur = lines[i];
  const tr = (ly.trans || []).find((x) => Math.abs(x.t - cur.t) < 0.25);
  const nx = lines[i + 1];
  main.textContent = cur.s;
  sub.textContent =
    (S.show_translation && tr) ? tr.s :
    (S.show_next && nx && nx.s !== cur.s) ? nx.s : "";
}

async function tick() {
  if (busy) return;
  busy = true;
  try {
    const d = await (await fetch("/api/state", { cache: "no-store" })).json();
    S = mergeSettings(d.settings);
    apply();

    const m = d.media;
    if (m) {
      if (!sameSong(m, media)) {
        basePos = m.position || 0;
        baseAt = performance.now();
      } else if (Math.abs(nowPos(media) - m.position) > DRIFT_LIMIT) {
        basePos = m.position;
        baseAt = performance.now();
      }
      media = m;
      playing = !!m.playing;
      renderPreview(m, d.lyrics);

      $("now").textContent = m.available
        ? `正在播放  ${m.title}  ·  ${m.artist}` +
          (m.song_id ? `  ·  ID ${m.song_id}` : "")
        : "没有检测到正在播放的音乐";
    }
  } catch (e) {
    /* 服务还没起来或页面正在隐藏，下一轮再试 */
  } finally {
    busy = false;
    pollTimer = setTimeout(tick, POLL_MS);
  }
}

// 面板隐藏再打开时立刻拉一次，不等下一次轮询。
function refreshNow() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  tick();
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshNow();
});

["fontSize", "subSize", "opacity"].forEach((id) => {
  $(id).addEventListener("input", () => {
    if (id === "fontSize") save({ font_size: +$("fontSize").value });
    else if (id === "subSize") save({ sub_size: +$("subSize").value });
    else save({ opacity: +$("opacity").value / 100 });
  });
});

$("rhythmOpacity").addEventListener("input", () => {
  const value = +$("rhythmOpacity").value;
  $("rhythmOpacityVal").textContent = value + "%";
  save({ rhythm_opacity: value / 100 });
});

function areaSize() {
  return {
    width: +$("areaWidth").value,
    height: +$("areaHeight").value,
  };
}

function updateAreaLabels() {
  const size = areaSize();
  $("areaWidthVal").textContent = size.width + "px";
  $("areaHeightVal").textContent = size.height + "px";
  updatePreviewArea(size.width, size.height);
}

let areaTimer = null;
function commitArea() {
  areaTimer = null;
  fetch("/api/resize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(areaSize()),
  }).catch(() => {});
}

["areaWidth", "areaHeight"].forEach((id) => {
  $(id).addEventListener("input", () => {
    updateAreaLabels();
    if (!areaTimer) areaTimer = setTimeout(commitArea, 120);
  });
  $(id).addEventListener("change", () => {
    if (areaTimer) {
      clearTimeout(areaTimer);
      areaTimer = null;
    }
    commitArea();
  });
});

const COLOR_INPUTS = {
  inkColor: "ink",
  accentColor: "accent",
  surfaceColor: "surface",
};

Object.keys(COLOR_INPUTS).forEach((id) => {
  $(id).addEventListener("input", () => {
    save({ [COLOR_INPUTS[id]]: $(id).value });
  });
});

$("rhythmColor").addEventListener("input", (e) => {
  save({ rhythm_color: e.target.value });
});
$("rhythmColorReset").addEventListener("click", () => {
  save({ rhythm_color: null });
});

$("paletteReset").addEventListener("click", () =>
  save({ ink: null, accent: null, surface: null }));

$("showTranslation").addEventListener("change", (e) =>
  save({ show_translation: e.target.checked }));
$("showNext").addEventListener("change", (e) =>
  save({ show_next: e.target.checked }));

$("unlock").addEventListener("click", () => save({ locked: !S.locked }));
$("recenter").addEventListener("click", () => post("/api/recenter"));
$("close").addEventListener("click", () => post("/api/panel", { action: "hide" }));

async function init() {
  try {
    const d = await (await fetch("/api/state", { cache: "no-store" })).json();
    S = d.settings || {};
  } catch (e) {
    S = {};
  }
  buildStyles();
  buildPalettes();
  buildRhythms();
  buildPresets();
  apply();
  tick();
}

init();
