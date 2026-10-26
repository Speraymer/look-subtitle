// viewer.js —— 注入到本机字幕列表页（127.0.0.1:8765/view）。
// 只做一件事：点某一行，让另一个标签页里的课程视频跳到那个时间。

document.documentElement.dataset.lookViewer = "1";

document.addEventListener(
  "click",
  (e) => {
    const row = e.target.closest(".row");
    if (!row) return;
    const t = parseFloat(row.dataset.t);
    if (isNaN(t)) return;
    chrome.runtime.sendMessage({ type: "seekRequest", t }, (resp) => {
      if (chrome.runtime.lastError) return;
      if (resp && !resp.ok) {
        const hint = document.getElementById("hint");
        if (hint) hint.textContent = "没找到打开着的课程页——先在另一个标签页播课程，再回来点。";
      }
    });
  },
  true
);
