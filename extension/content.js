// content.js —— 只读观察：不改播放器、不拦截用户操作。
// 所有上报都交给 background 代发，避免被页面的 CSP / CORS 挡住。

const MEDIA_RE = /\.(m3u8|mp4|flv|ts|m4s|key)(\?|#|$)/i;
const COURSE_API_RE = /\/(courseapi|portal|schedule)\//i;
const sent = new Set();
let helloed = false;

function report(payload) {
  payload.page = location.href;
  payload.frame = window.top === window ? "top" : "iframe";
  payload.ts = new Date().toISOString();
  try {
    chrome.runtime.sendMessage({ type: "report", payload }, () => void chrome.runtime.lastError);
  } catch (e) {}
}

// 先打个招呼：这样一眼能看出 content script 到底有没有注入
if (!helloed && window.top === window) {
  helloed = true;
  report({ kind: "hello", title: document.title, ready: document.readyState });
}

// ---- 1) 资源时间线 ----
function scanResources() {
  let entries = [];
  try {
    entries = performance.getEntriesByType("resource");
  } catch (e) {
    return;
  }
  for (const e of entries) {
    const u = e.name;
    if (!MEDIA_RE.test(u) && !COURSE_API_RE.test(u)) continue;
    if (sent.has(u)) continue;
    sent.add(u);
    if (!MEDIA_RE.test(u)) {
      report({ kind: "course-api", url: u, initiatorType: e.initiatorType });
      continue;
    }
    report({ kind: "resource", url: u, initiatorType: e.initiatorType, size: e.transferSize });
    if (/\.m3u8(\?|#|$)/i.test(u)) {
      chrome.runtime.sendMessage({ type: "fetchM3U8", url: u }, (resp) => {
        if (chrome.runtime.lastError) return;
        report({ kind: "m3u8-body", url: u, ok: !!(resp && resp.ok), status: resp && resp.status, body: (resp && resp.text) || null });
      });
    }
  }
}

// ---- 2) Vue 实例上的 liveInfo ----
function findVueRoot() {
  const app = document.querySelector("#app");
  if (!app) return null;
  if (app.__vue__) return app.__vue__;
  const kids = app.children || [];
  for (const k of kids) if (k.__vue__) return k.__vue__;
  return null;
}

function digLiveInfo() {
  const root = findVueRoot();
  if (!root) return null;
  const seen = new Set();
  const queue = [[root, 0]];
  let hit = null;
  while (queue.length && !hit) {
    const [v, d] = queue.shift();
    if (!v || d > 8 || seen.has(v)) continue;
    seen.add(v);
    try {
      if (v.liveInfo && (v.liveInfo.playurl || v.liveInfo.content || v.liveInfo.live_url)) {
        hit = v.liveInfo;
        break;
      }
    } catch (e) {}
    for (const k of Object.keys(v)) {
      let c;
      try {
        c = v[k];
      } catch (e) {
        continue;
      }
      if (c && typeof c === "object") queue.push([c, d + 1]);
    }
  }
  if (!hit) return null;
  const sp = hit.content && hit.content.save_playback;
  return {
    sub_id: hit.sub_id,
    course_id: hit.course_id,
    course_type: hit.course_type,
    sub_type: hit.sub_type,
    room_type: hit.room_type,
    is_m3u8: hit.is_m3u8,
    playurl: hit.playurl || null,
    start_at: hit.start_at || null,
    content_keys: hit.content ? Object.keys(hit.content) : null,
    save_playback: sp
      ? {
          is_m3u8: sp.is_m3u8,
          keys: Object.keys(sp),
          play_addres_arr: sp.play_addres_arr || null,
          contents: sp.contents || null,
          mpc: sp.mpc || null,
          pgc: sp.pgc || null,
        }
      : null,
  };
}

let liveInfoSent = false;
function tick() {
  scanResources();
  if (!liveInfoSent) {
    const info = digLiveInfo();
    if (info) {
      liveInfoSent = true;
      report({ kind: "liveinfo", data: info });
    }
  }
}

tick();
const timer = setInterval(tick, 1500);
setTimeout(() => clearInterval(timer), 300000);
