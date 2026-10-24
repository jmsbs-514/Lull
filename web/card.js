const POLL_MS = 250;

const body = document.body;
const $ = (id) => document.getElementById(id);

let S = {};
let media = null;
let playing = false;
let basePos = 0;
let baseAt = 0;
let lastKey = "";
let duration = 0;
let dragging = false;
let dragRatio = 0;
let coverKey = "";
let ignoreBlurUntil = 0;
let busy = false;

const cover = $("cover");
cover.addEventListener("error", () => cover.classList.add("hidden"));
cover.addEventListener("load", () => cover.classList.remove("hidden"));

function applyStyle(name) {
  body.classList.remove("t-glow", "t-capsule", "t-editorial");
  const cardStyle = name === "editorial" ? "editorial" : "glow";
  body.classList.add("t-" + cardStyle);
}

function applyPalette(s) {
  const st = body.style;
  const C = window.LullColor;
  const ink = typeof s.ink === "string" ? s.ink : "";
  const accent = typeof s.accent === "string" ? s.accent : "";
  const surface = typeof s.surface === "string" ? s.surface : "";
  const contrast = surface && C
    ? (C.lum(surface) > 0.55 ? "#1a1814" : "#ffffff")
    : "";
  const effectiveInk = ink || contrast;

  if (effectiveInk && C) {
    st.setProperty("--fg", effectiveInk);
    st.setProperty("--dim", C.rgba(effectiveInk, 0.55));
    st.setProperty("--line", C.rgba(effectiveInk, 0.12));
    st.setProperty("--hover", C.rgba(effectiveInk, 0.07));
  } else {
    st.removeProperty("--fg");
    st.removeProperty("--dim");
    st.removeProperty("--line");
    st.removeProperty("--hover");
  }

  if (accent && C) {
    st.setProperty("--accent", accent);
    st.setProperty("--accent-fg", C.accentFg(accent));
  } else {
    st.removeProperty("--accent");
    st.removeProperty("--accent-fg");
  }

  if (surface && C) {
    st.setProperty("--bg", surface);
    const tint = effectiveInk || (C.lum(surface) > 0.55 ? "#1a1814" : "#ffffff");
    st.setProperty("--cover-a", C.mix(surface, tint, 0.10));
    st.setProperty("--cover-b", surface);
    st.setProperty("--cover-ink", C.rgba(tint, 0.35));
    st.setProperty("--danger", C.danger(surface));
  } else {
    st.removeProperty("--bg");
    st.removeProperty("--cover-a");
    st.removeProperty("--cover-b");
    st.removeProperty("--danger");
    if (effectiveInk && C) {
      st.setProperty("--cover-ink", C.rgba(effectiveInk, 0.42));
    } else {
      st.removeProperty("--cover-ink");
    }
  }
}

function fmt(sec) {
  sec = Number(sec);
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m + ":" + String(s).padStart(2, "0");
}

function nowPos(m) {
  const cur = m || media;
  if (!cur || !cur.available) return 0;
  if (!playing) return Number(cur.position) || 0;
  const lu = Number(cur.last_updated) || 0;
  if (lu > 0) {
    const elapsed = Date.now() / 1000 - lu;
    if (elapsed >= -0.5 && elapsed <= 3.0) {
      return (Number(cur.position) || 0) + elapsed;
    }
  }
  return basePos + (performance.now() - baseAt) / 1000;
}

function setPlaying(value) {
  playing = !!value;
  body.classList.toggle("playing", playing);
}

function setCover(m) {
  const key = m && m.available ? String(m.song_id || m.title || "") : "";
  if (key === coverKey) return;
  coverKey = key;
  if (!key) {
    cover.removeAttribute("src");
    cover.classList.add("hidden");
    return;
  }
  cover.classList.remove("hidden");
  cover.src = "/api/cover?k=" + encodeURIComponent(key);
}

function paint() {
  if (!media || !media.available) return;
  const total = duration;
  let pos = dragging ? dragRatio * total : nowPos(media);
  if (total > 0) pos = Math.min(pos, total);
  pos = Math.max(0, pos);
  const frac = total > 0 ? Math.min(1, Math.max(0, pos / total)) : 0;
  $("fill").style.width = (frac * 100).toFixed(2) + "%";
  $("cur").textContent = fmt(dragging ? dragRatio * total : pos);
  $("dur").textContent = total > 0 ? fmt(total) : "--:--";
}

function render(m) {
  const ok = !!(m && m.available);
  $("title").textContent = ok ? (m.title || "未知曲目") : "没有正在播放的音乐";
  $("artist").textContent = ok ? (m.artist || "") : "打开网易云，Lull 会跟着亮";
  document.querySelector(".controls").classList.toggle("disabled", !ok);
  $("seek").style.pointerEvents = ok && duration > 0 ? "auto" : "none";

  if (!ok) {
    $("fill").style.width = "0%";
    $("cur").textContent = "0:00";
    $("dur").textContent = "--:--";
    return;
  }

  const key = `${m.song_id || 0}|${m.title || ""}|${m.artist || ""}`;
  if (key !== lastKey) {
    lastKey = key;
    basePos = Number(m.position) || 0;
    baseAt = performance.now();
  }
  paint();
}

async function tick() {
  if (busy) return;
  busy = true;
  try {
    const d = await (await fetch("/api/state", { cache: "no-store" })).json();
    S = d.settings || {};
    applyStyle(S.style);
    applyPalette(S);
    updateMenu();

    const m = d.media;
    if (m) {
      if (media && m.song_id === media.song_id && m.title === media.title) {
        if (Math.abs(nowPos(media) - (Number(m.position) || 0)) > 2.0) {
          basePos = Number(m.position) || 0;
          baseAt = performance.now();
        }
      }
      media = m;
      setPlaying(!!m.playing);
      duration = Number(m.duration) || 0;
      render(m);
      setCover(m);
    }
  } catch (e) {
    /* 服务还没起来或卡片正在隐藏 */
  } finally {
    busy = false;
    setTimeout(tick, POLL_MS);
  }
}

function post(path, payload) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  }).then((r) => r.json()).catch(() => ({ ok: false }));
}

function control(action, extra) {
  return post("/api/control", Object.assign({ action }, extra || {}));
}

$("play").addEventListener("click", async () => {
  if (!media || !media.available) return;
  setPlaying(!playing);
  const r = await control("toggle");
  if (!r.ok) setPlaying(!playing);
});

$("prev").addEventListener("click", () => control("prev"));
$("next").addEventListener("click", () => control("next"));

const seekEl = $("seek");
const trackEl = document.querySelector(".track");

function ratioAt(event) {
  const rect = trackEl.getBoundingClientRect();
  if (rect.width <= 0) return 0;
  return Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
}

seekEl.addEventListener("pointerdown", (event) => {
  if (!duration || !media || !media.available) return;
  dragging = true;
  dragRatio = ratioAt(event);
  seekEl.setPointerCapture(event.pointerId);
  paint();
});

seekEl.addEventListener("pointermove", (event) => {
  if (!dragging) return;
  dragRatio = ratioAt(event);
  paint();
});

function finishSeek() {
  if (!dragging) return;
  dragging = false;
  const target = dragRatio * duration;
  if (media) {
    media.position = target;
    basePos = target;
    baseAt = performance.now();
  }
  paint();
  control("seek", { position: target });
}

seekEl.addEventListener("pointerup", finishSeek);
seekEl.addEventListener("pointercancel", () => {
  dragging = false;
  paint();
});

function hide() {
  post("/api/card", { action: "hide" });
}

$("home").addEventListener("click", () => {
  post("/api/panel", { action: "show" });
  hide();
});

$("more").addEventListener("click", () => {
  body.classList.toggle("menu-open");
  updateMenu();
});

$("mBack").addEventListener("click", () => {
  body.classList.remove("menu-open");
});

function updateMenu() {
  $("mLockLabel").textContent = S.locked ? "锁定（点击穿透）" : "解锁（可拖动）";
}

$("mVisible").addEventListener("click", () => {
  post("/api/visibility", { action: "toggle" });
});

$("mLock").addEventListener("click", () => {
  S.locked = !S.locked;
  updateMenu();
  post("/api/settings", { locked: S.locked });
});

$("mQuit").addEventListener("click", () => post("/api/quit", {}));

window.addEventListener("blur", () => {
  setTimeout(() => {
    if (Date.now() < ignoreBlurUntil) return;
    hide();
  }, 180);
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (body.classList.contains("menu-open")) {
    body.classList.remove("menu-open");
  } else {
    hide();
  }
});

window.cardShown = function () {
  ignoreBlurUntil = Date.now() + 500;
  body.classList.remove("menu-open");
  const card = $("card");
  card.classList.remove("enter");
  void card.offsetWidth;
  card.classList.add("enter");
  tick();
};

function loop() {
  paint();
  requestAnimationFrame(loop);
}

tick();
requestAnimationFrame(loop);
