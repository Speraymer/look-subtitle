// overlay.js —— 把本机转好的字幕叠在播放器上。
// 不碰播放器内部 API；字幕位置可拖动、可调字号、位置记在 localStorage 里。

(function () {
  if (window.__LOOK_SUB_OVERLAY__) return;
  window.__LOOK_SUB_OVERLAY__ = true;

  const POS_KEY = "look-sub-pos-v2";
  const SIZE_KEY = "look-sub-size-v2";
  const DEFAULT_POS = { x: 50, y: 82 };   // 相对视口百分比

  let data = null;
  let video = null;
  let box = null;
  let lineEl = null;
  let handle = null;
  let lastText = "";
  let subId = new URLSearchParams(location.search).get("sub_id");
  let pos = loadPos();
  let fontPx = loadSize();
  let userSized = !!localStorage.getItem(SIZE_KEY);
  let dragging = false;
  let dragStart = null;

  function loadPos() {
    try {
      const p = JSON.parse(localStorage.getItem(POS_KEY));
      if (p && typeof p.x === "number") return p;
    } catch (e) {}
    return { ...DEFAULT_POS };
  }
  function savePos() {
    try {
      localStorage.setItem(POS_KEY, JSON.stringify(pos));
    } catch (e) {}
  }
  function loadSize() {
    const n = parseInt(localStorage.getItem(SIZE_KEY) || "", 10);
    return n >= 12 && n <= 48 ? n : 22;
  }
  function saveSize() {
    try {
      localStorage.setItem(SIZE_KEY, String(fontPx));
    } catch (e) {}
  }

  function pickVideo() {
    const vs = Array.from(document.querySelectorAll("video")).filter(
      (v) => v.readyState > 0 || v.currentSrc
    );
    if (!vs.length) return null;
    vs.sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight);
    return vs[0];
  }

  function applyPos() {
    if (!box) return;
    box.style.left = pos.x + "%";
    box.style.top = pos.y + "%";
  }

  function ensureBox() {
    if (box && box.isConnected) return box;
    box = document.createElement("div");
    box.id = "look-sub-overlay";
    box.style.cssText = [
      "position:fixed",
      "transform:translate(-50%,-50%)",
      "max-width:78%",
      "padding:6px 16px",
      "border-radius:8px",
      "background:rgba(0,0,0,.62)",
      "color:#fff",
      "font-size:" + fontPx + "px",
      "line-height:1.45",
      "text-align:center",
      "z-index:2147483000",
      "pointer-events:none",
      "text-shadow:0 1px 3px rgba(0,0,0,.8)",
      "font-family:'Microsoft YaHei',system-ui,sans-serif",
      "white-space:pre-wrap",
      "user-select:none",
      "display:none",
    ].join(";");
    lineEl = document.createElement("span");
    box.appendChild(lineEl);

    // 拖动手柄：只在鼠标靠近时显形，不挡字幕
    handle = document.createElement("div");
    handle.title = "拖动我移动字幕 · 滚轮调字号 · 双击复位";
    handle.style.cssText = [
      "position:absolute",
      "left:-11px",
      "top:-11px",
      "width:22px",
      "height:22px",
      "border-radius:50%",
      "background:rgba(120,200,255,.75)",
      "border:2px solid rgba(255,255,255,.9)",
      "cursor:move",
      "pointer-events:auto",
      "opacity:.35",
      "transition:opacity .15s",
      "box-sizing:border-box",
    ].join(";");
    box.appendChild(handle);

    // box 本身 pointer-events:none，收不到 hover，所以只靠手柄自己
    handle.addEventListener("mouseenter", () => (handle.style.opacity = "1"));
    handle.addEventListener("mouseleave", () => {
      if (!dragging) handle.style.opacity = ".35";
    });

    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragging = true;
      handle.setPointerCapture(e.pointerId);
      dragStart = { cx: e.clientX, cy: e.clientY, x: pos.x, y: pos.y };
    });
    handle.addEventListener("pointermove", (e) => {
      if (!dragging || !dragStart) return;
      const dx = ((e.clientX - dragStart.cx) / window.innerWidth) * 100;
      const dy = ((e.clientY - dragStart.cy) / window.innerHeight) * 100;
      pos.x = Math.min(96, Math.max(4, dragStart.x + dx));
      pos.y = Math.min(96, Math.max(4, dragStart.y + dy));
      applyPos();
    });
    handle.addEventListener("pointerup", (e) => {
      if (dragging) {
        dragging = false;
        savePos();
        handle.releasePointerCapture(e.pointerId);
      }
    });
    handle.addEventListener("wheel", (e) => {
      e.preventDefault();
      fontPx = Math.min(48, Math.max(12, fontPx + (e.deltaY > 0 ? -2 : 2)));
      box.style.fontSize = fontPx + "px";
      userSized = true;
      saveSize();
    }, { passive: false });
    handle.addEventListener("dblclick", () => {
      pos = { ...DEFAULT_POS };
      fontPx = 22;
      box.style.fontSize = fontPx + "px";
      userSized = false;
      applyPos();
      savePos();
      saveSize();
    });

    document.body.appendChild(box);
    applyPos();
    return box;
  }

  function placeBox() {
    if (!box) return;
    const fs = document.fullscreenElement;
    if (fs) {
      if (box.parentNode !== fs) fs.appendChild(box);
      box.style.position = "absolute";
    } else {
      if (box.parentNode !== document.body) document.body.appendChild(box);
      box.style.position = "fixed";
    }
    applyPos();
  }

  function findAt(t) {
    const segs = data.segments;
    let lo = 0, hi = segs.length - 1, best = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (segs[mid].start <= t) { best = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    if (best < 0) return null;
    const s = segs[best];
    return t <= s.end ? s : null;
  }

  function tick() {
    requestAnimationFrame(tick);
    if (!data || !video) return;
    if (document.fullscreenElement) placeBox();
    const seg = findAt(video.currentTime);
    const text = seg ? seg.text : "";
    if (text !== lastText) {
      lastText = text;
      lineEl.textContent = text;
      // 只在用户没手动调过字号时，才跟着视频高度自动缩放
      if (!userSized) {
        const h = video.clientHeight || 540;
        box.style.fontSize = Math.max(14, Math.min(30, Math.round(h * 0.042))) + "px";
      }
      box.style.display = text ? "block" : "none";
    }
  }

  // 从字幕列表页点时间戳跳过来
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "seekTo") {
      const v = pickVideo();
      if (v) {
        v.currentTime = msg.t;
        v.play().catch(() => {});
      }
    }
  });

  function boot() {
    video = pickVideo();
    if (!video) {
      setTimeout(boot, 1500);
      return;
    }
    ensureBox();
    const ask = (id) =>
      chrome.runtime.sendMessage({ type: "getSubtitles", subId: id }, (resp) => {
        if (chrome.runtime.lastError) return;
        if (resp && resp.ok) {
          data = resp.data;
          subId = resp.subId;
        }
      });
    ask(subId);
    tick();
  }

  const wait = setInterval(() => {
    const v = pickVideo();
    if (v) {
      clearInterval(wait);
      video = v;
      boot();
    }
  }, 1000);
  setTimeout(() => clearInterval(wait), 60000);
  document.addEventListener("fullscreenchange", () => placeBox());
})();
