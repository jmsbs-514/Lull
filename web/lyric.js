const POLL_MS = 400;

const stage = document.getElementById("stage");
const mainEl = document.getElementById("main");
const mainShadowEl = document.getElementById("mainShadow");
const subEl = document.getElementById("sub");
const subShadowEl = document.getElementById("subShadow");
const rhythmEl = document.getElementById("rhythm");

let media = null;
let lines = [];
let transIndex = [];
let basePos = 0;
let baseAt = 0;
let playing = false;
let editing = false;
let lastMain = "";
let lastSub = "";
let hasLyric = false;
let pureMusic = false;
let pollTimer = null;
let showTranslation = true;
let showNext = true;
let rhythmType = "off";
let rhythmActive = false;
let rhythmLevel = 0;
let rhythmDisplay = 0;
let rhythmOpacity = 1;
let rhythmBands = [];
let rhythmSpectrum = false;
let rhythmBarDisplay = [];
let rhythmBars = [];
let levelTimer = null;
let levelBusy = false;

function nowPos() {
  if (!media || !media.available) return 0;
  if (!playing) return media.position;
  const lu = media.last_updated;
  if (lu > 0) {
    const elapsed = Date.now() / 1000 - lu;
    if (elapsed >= -0.5 && elapsed <= 3.0) return media.position + elapsed;
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

function transAt(t) {
  if (!transIndex.length) return "";
  const i = indexAt(transIndex, t + 0.001);
  for (const j of [i, i + 1, i - 1]) {
    const item = transIndex[j];
    if (item && Math.abs(item.t - t) < 0.25) return item.s;
  }
  return "";
}

function swapText(el, text, cls) {
  if (el.textContent === text) return false;
  el.textContent = text;
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
  return true;
}

let probeEl = null;

function measureWidth(text, size, font, weight, spacing) {
  if (!probeEl) {
    probeEl = document.createElement("span");
    probeEl.style.cssText =
      "position:absolute;left:-9999px;top:0;white-space:nowrap;visibility:hidden;";
    document.body.appendChild(probeEl);
  }
  probeEl.style.fontFamily = font;
  probeEl.style.fontWeight = weight;
  probeEl.style.letterSpacing = spacing;
  probeEl.style.fontSize = size + "px";
  probeEl.textContent = text;
  return probeEl.offsetWidth;
}

function fitText() {
  const base = parseFloat(getComputedStyle(document.documentElement)
    .getPropertyValue("--main-size")) || 30;
  mainEl.style.fontSize = base + "px";
  mainShadowEl.style.fontSize = base + "px";
  const text = mainEl.textContent;
  if (!text) return;

  const cs = getComputedStyle(stage);
  const boxW = stage.clientWidth
    - parseFloat(cs.paddingLeft || 0) - parseFloat(cs.paddingRight || 0);
  if (boxW <= 0) return;

  const ms = getComputedStyle(mainEl);
  let size = base;
  let guard = 0;
  while (size > 11 && guard < 60 &&
         measureWidth(text, size, ms.fontFamily, ms.fontWeight, ms.letterSpacing) > boxW) {
    size -= 1;
    guard++;
  }
  mainEl.style.fontSize = size + "px";
  mainShadowEl.style.fontSize = size + "px";
  positionRhythm();
}

function setStyle(name) {
  stage.className = "s-" + name;
}

let baseFont = 0;
let baseStyle = "";

const RHYTHM_SPECS = {
  wave: { count: 48, width: 5, smooth: 0.55 },
  steps: { count: 32, width: 8, steps: 3, smooth: 0.55 },
  hairline: { count: 64, width: 2, smooth: 0.5 },
  breath: { count: 24, width: 10, smooth: 0.18 },
  mirror: { count: 56, width: 4, smooth: 0.5 },
};

let rhythmMax = 40;

function positionRhythm() {
  if (!rhythmBars.length) return;
  rhythmMax = Math.max(16, stage.clientHeight);
}

function buildRhythm(type) {
  rhythmEl.innerHTML = "";
  rhythmBars = [];
  const spec = RHYTHM_SPECS[type];
  if (!spec) {
    rhythmEl.style.display = "none";
    return;
  }
  rhythmEl.style.display = "flex";
  rhythmEl.style.gap = "0px";
  for (let i = 0; i < spec.count; i++) {
    const bar = document.createElement("span");
    bar.style.width = spec.width + "px";
    rhythmEl.appendChild(bar);
    rhythmBars.push(bar);
  }
  rhythmBarDisplay = new Array(rhythmBars.length).fill(0);
  positionRhythm();
}

function setRhythm(type) {
  const next = RHYTHM_SPECS[type] ? type : "off";
  if (next === rhythmType) return;
  rhythmType = next;
  if (next === "off") {
    rhythmBars = [];
    rhythmBarDisplay = [];
    rhythmBands = [];
    rhythmSpectrum = false;
    rhythmEl.innerHTML = "";
    rhythmEl.style.display = "none";
    rhythmEl.style.opacity = "0";
    rhythmDisplay = 0;
    rhythmLevel = 0;
  } else {
    buildRhythm(next);
  }
}

function setRhythmActive(active) {
  active = !!active && rhythmType !== "off";
  if (active === rhythmActive) return;
  rhythmActive = active;
  if (!active) {
    if (levelTimer !== null) {
      clearTimeout(levelTimer);
      levelTimer = null;
    }
    rhythmLevel = 0;
  } else {
    startLevel();
  }
}

async function pollLevel() {
  levelTimer = null;
  if (!rhythmActive) return;
  levelBusy = true;
  try {
    const response = await fetch("/api/level", { cache: "no-store" });
    const data = await response.json();
    rhythmLevel = Math.max(0, Math.min(1, Number(data.v) || 0));
    rhythmSpectrum = !!data.spectrum;
    if (Array.isArray(data.bands) && data.bands.length >= 4) {
      rhythmBands = data.bands.map((v) =>
        Math.max(0, Math.min(1, Number(v) || 0)));
    } else {
      rhythmBands = [];
    }
  } catch (e) {
    rhythmLevel = 0;
  } finally {
    levelBusy = false;
    if (rhythmActive) levelTimer = setTimeout(pollLevel, 50);
  }
}

function startLevel() {
  if (levelTimer !== null || levelBusy) return;
  pollLevel();
}

function bandAt(position) {
  if (!rhythmBands.length) return 0;
  const last = rhythmBands.length - 1;
  const pos = Math.max(0, Math.min(1, position)) * last;
  const lo = Math.floor(pos);
  const hi = Math.min(last, lo + 1);
  const t = pos - lo;
  return rhythmBands[lo] * (1 - t) + rhythmBands[hi] * t;
}

function drawRhythm() {
  if (rhythmType === "off" || !rhythmBars.length) return;
  const overall = rhythmActive ? Math.min(1, rhythmLevel * 1.2) : 0;
  rhythmDisplay += (overall - rhythmDisplay) * 0.6;
  if (rhythmDisplay < 0.001) rhythmDisplay = 0;

  const spec = RHYTHM_SPECS[rhythmType];
  const n = rhythmBars.length;
  if (rhythmBarDisplay.length !== n) {
    rhythmBarDisplay = new Array(n).fill(0);
  }
  const useBands = rhythmBands.length >= 4;
  const t = performance.now() / 1000;
  const smooth = spec.smooth || 0.55;

  rhythmBars.forEach((bar, i) => {
    const p = n > 1 ? i / (n - 1) : 0;
    let targetBar = 0;
    if (rhythmActive) {
      targetBar = useBands ? bandAt(p) : rhythmDisplay;
    }
    rhythmBarDisplay[i] += (targetBar - rhythmBarDisplay[i]) * smooth;

    let value = rhythmBarDisplay[i];
    if (!useBands && !rhythmSpectrum) {
      value *= 0.9 + 0.1 * Math.sin(t * 5.2 + i * 0.75);
    }
    let height = value * rhythmMax;
    if (spec.steps) {
      const unit = rhythmMax / spec.steps;
      height = Math.round(height / unit) * unit;
    }
    bar.style.height = Math.max(0, height).toFixed(1) + "px";
  });

  const fade = rhythmDisplay > 0.015
    ? Math.min(1, rhythmDisplay * 4)
    : 0;
  rhythmEl.style.opacity = String(fade * rhythmOpacity);
}

function applyPalette(s) {
  const root = document.documentElement.style;
  const C = window.LullColor;
  const ink = typeof s.ink === "string" ? s.ink : "";
  if (ink && C) {
    root.setProperty("--fg", ink);
    root.setProperty("--fg-sub", C.rgba(ink, 0.72));
    const sh = C.shadows(ink);
    root.setProperty("--shadow-main", sh.main);
    root.setProperty("--shadow-sub", sh.sub);
    root.setProperty("--shadow-quiet", sh.quiet);
    root.setProperty("--shadow-quiet-sub", sh.quietSub);
    root.setProperty("--shadow-medium", sh.medium);
    root.setProperty("--shadow-medium-sub", sh.mediumSub);
    root.setProperty("--shadow-tight", sh.tight);
    root.setProperty("--shadow-tight-sub", sh.tightSub);
  } else {
    root.removeProperty("--fg");
    root.removeProperty("--fg-sub");
    root.removeProperty("--shadow-main");
    root.removeProperty("--shadow-sub");
    root.removeProperty("--shadow-quiet");
    root.removeProperty("--shadow-quiet-sub");
    root.removeProperty("--shadow-medium");
    root.removeProperty("--shadow-medium-sub");
    root.removeProperty("--shadow-tight");
    root.removeProperty("--shadow-tight-sub");
  }
  if (typeof s.accent === "string" && s.accent) {
    root.setProperty("--accent", s.accent);
  } else {
    root.removeProperty("--accent");
  }
  if (typeof s.rhythm_color === "string" && s.rhythm_color) {
    root.setProperty("--rhythm-color", s.rhythm_color);
  } else {
    root.removeProperty("--rhythm-color");
  }
  if (typeof s.surface === "string" && s.surface) {
    root.setProperty("--surface", s.surface);
  } else {
    root.removeProperty("--surface");
  }
}

function applySettings(s) {
  if (!s) return;
  try {
    const sel = window.getSelection();
    if (sel) sel.removeAllRanges();
  } catch (e) { /* 透明窗口下清掉可能的文本选择高亮 */ }
  const styleName = s.style || "glow";
  setStyle(styleName);
  const f = s.font_size || 30;
  document.documentElement.style.setProperty("--main-size", f + "px");
  document.documentElement.style.setProperty("--sub-size", (s.sub_size || 15) + "px");
  document.body.style.setProperty("--user-opacity", String(s.opacity ?? 0.92));
  showTranslation = s.show_translation !== false;
  showNext = s.show_next !== false;
  const ro = s.rhythm_opacity;
  rhythmOpacity = typeof ro === "number"
    ? Math.max(0, Math.min(1, ro)) : 1;
  setRhythm(s.rhythm || "off");
  applyPalette(s);
  if (f !== baseFont || styleName !== baseStyle) {
    baseFont = f;
    baseStyle = styleName;
    requestAnimationFrame(fitText);
  }
}

function render() {
  const pos = nowPos();
  const silent = !media || !media.available;

  // 暂停、停止或播放器退出时保留最后一屏歌词。
  document.body.classList.remove("idle");

  if (!silent) {
    if (pureMusic && !hasLyric) {
      swapText(mainEl, media.title || "", "enter");
      swapText(mainShadowEl, media.title || "", "enter");
      swapText(subEl, media.artist || "", "swap");
      swapText(subShadowEl, media.artist || "", "swap");
      fitText();
    } else {
      const i = indexAt(lines, pos);
      if (i >= 0) {
        const cur = lines[i];
        const tr = transAt(cur.t);
        const next = lines[i + 1];
        let subText = "";
        if (showTranslation && tr) subText = tr;
        else if (showNext && next && next.s !== cur.s) subText = next.s;
        const changed = swapText(mainEl, cur.s, "enter");
        swapText(mainShadowEl, cur.s, "enter");
        swapText(subEl, subText, "swap");
        swapText(subShadowEl, subText, "swap");
        if (changed) fitText();
      } else {
        swapText(mainEl, "", "enter");
        swapText(mainShadowEl, "", "enter");
        swapText(subEl, "", "swap");
        swapText(subShadowEl, "", "swap");
      }
    }
  }

  drawRhythm();
  requestAnimationFrame(render);
}

async function poll() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    const data = await r.json();
    const m = data.media;

    if (m.song_id !== (media && media.song_id) ||
        m.title !== (media && media.title)) {
      basePos = m.position;
      baseAt = performance.now();
    } else {
      const drift = Math.abs(nowPos() - m.position);
      if (drift > 2.0) {
        basePos = m.position;
        baseAt = performance.now();
      }
    }

    media = m;
    playing = !!m.playing;
    if (data.settings && typeof data.settings.locked === "boolean") {
      window.setEditing(!data.settings.locked);
    }
    const ly = data.lyrics;
    if (ly) {
      pureMusic = !!ly.pure_music;
      lines = ly.lines || [];
      transIndex = ly.trans || [];
      hasLyric = lines.length > 0;
    } else {
      lines = [];
      transIndex = [];
      hasLyric = false;
    }
    applySettings(data.settings);
    setRhythmActive(rhythmType !== "off" && m.available && m.playing);
  } catch (e) {
    /* 服务还没起来，下次再说 */
  }
  pollTimer = setTimeout(poll, POLL_MS);
}

stage.addEventListener("mousedown", (e) => {
  if (!editing) return;
  e.preventDefault();
  fetch("/api/drag", { method: "POST", body: "{}" }).catch(() => {});
});

window.setEditing = function (v) {
  editing = !!v;
  document.body.classList.toggle("editing", editing);
};

const resizeHandle = document.getElementById("resizeHandle");
let resizeTimer = null;
let resizePending = null;

function flushResize() {
  if (!resizePending) return;
  const size = resizePending;
  resizePending = null;
  fetch("/api/resize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(size),
  }).catch(() => {});
}

resizeHandle.addEventListener("pointerdown", (e) => {
  if (!editing) return;
  e.preventDefault();
  e.stopPropagation();
  const startX = e.screenX;
  const startY = e.screenY;
  const startW = window.innerWidth;
  const startH = window.innerHeight;
  try { resizeHandle.setPointerCapture(e.pointerId); } catch (err) { /* noop */ }

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(v)));
  const move = (ev) => {
    resizePending = {
      width: clamp(startW + ev.screenX - startX, 420, 1800),
      height: clamp(startH + ev.screenY - startY, 100, 600),
    };
    if (!resizeTimer) {
      resizeTimer = setTimeout(() => {
        resizeTimer = null;
        flushResize();
      }, 50);
    }
  };
  const up = (ev) => {
    if (resizeTimer) {
      clearTimeout(resizeTimer);
      resizeTimer = null;
    }
    resizePending = {
      width: clamp(startW + ev.screenX - startX, 420, 1800),
      height: clamp(startH + ev.screenY - startY, 100, 600),
    };
    flushResize();
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  window.addEventListener("pointercancel", up);
});

window.applySettingsPatch = applySettings;

let resizeRaf = 0;
window.addEventListener("resize", () => {
  if (resizeRaf) return;
  resizeRaf = requestAnimationFrame(() => {
    resizeRaf = 0;
    fitText();
    positionRhythm();
  });
});

poll();
requestAnimationFrame(render);
requestAnimationFrame(positionRhythm);
