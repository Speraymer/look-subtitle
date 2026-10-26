// background.js —— 所有网络动作都在这儿做（扩展上下文不受页面 CSP/CORS 约束）。

const SERVER = "http://127.0.0.1:8765";

function post(payload) {
  return fetch(SERVER + "/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch(() => {});
}

// 每次 service worker 醒来都留个记号
chrome.runtime.onInstalled.addListener(() =>
  post({ kind: "sw-installed", ts: new Date().toISOString() })
);
post({ kind: "sw-start", ts: new Date().toISOString() });

function subIdFromUrl(u) {
  try {
    return new URL(u).searchParams.get("sub_id");
  } catch (e) {
    return null;
  }
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (!msg) return;

  if (msg.type === "report") {
    const p = msg.payload || {};
    if (sender && sender.tab) p.tabId = sender.tab.id;
    post(p);
    reply({ ok: true });
    return true;
  }

  if (msg.type === "fetchM3U8") {
    fetch(msg.url, { credentials: "include" })
      .then((r) => r.text().then((t) => reply({ ok: r.ok, status: r.status, text: t })))
      .catch((e) => reply({ ok: false, status: 0, text: String(e) }));
    return true;
  }

  if (msg.type === "seekRequest") {
    chrome.tabs.query({ url: "*://look.tongji.edu.cn/*" }, (tabs) => {
      if (!tabs || !tabs.length) {
        reply({ ok: false, msg: "no look tab" });
        return;
      }
      for (const t of tabs) {
        chrome.tabs.sendMessage(t.id, { type: "seekTo", t: msg.t }, () => void chrome.runtime.lastError);
      }
      reply({ ok: true, tabs: tabs.length });
    });
    return true;
  }

  if (msg.type === "getSubtitles") {
    let id = msg.subId;
    if (!id && sender && sender.tab) id = subIdFromUrl(sender.tab.url || "");
    if (!id) {
      reply({ ok: false, msg: "no sub_id" });
      return true;
    }
    fetch(`${SERVER}/subtitles?sub_id=${encodeURIComponent(id)}`)
      .then((r) => (r.ok ? r.json() : r.json().then((j) => ({ ok: false, ...j }))))
      .then((d) => reply({ ok: !!d.ok, subId: id, data: d.ok ? d : null, msg: d.msg }))
      .catch((e) => reply({ ok: false, msg: String(e) }));
    return true;
  }
});
