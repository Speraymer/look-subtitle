// ppt.js —— 从平台取「每页 PPT 的时间点 + 图」，并试一下课件能不能导出。
// 只读：调自有接口，把结果送到本机。

(function () {
  if (window.__LOOK_PPT__) return;
  window.__LOOK_PPT__ = true;

  const q = new URLSearchParams(location.search);
  const courseId = q.get("course_id");
  const subId = q.get("sub_id");
  const tenant = q.get("tenant_code") || "222";
  if (!courseId || !subId) return;

  const send = (p) => {
    p.course_id = courseId;
    p.sub_id = subId;
    chrome.runtime.sendMessage({ type: "report", payload: p }, () => void chrome.runtime.lastError);
  };

  async function j(u, opts) {
    const r = await fetch(u, Object.assign({ credentials: "include" }, opts || {}));
    const t = await r.text();
    try {
      return { status: r.status, json: JSON.parse(t) };
    } catch (e) {
      return { status: r.status, text: t.slice(0, 300) };
    }
  }

  function deepFind(obj, keys, depth = 0, path = "") {
    const hits = [];
    if (!obj || typeof obj !== "object" || depth > 6) return hits;
    for (const k of Object.keys(obj)) {
      const v = obj[k];
      if (keys.includes(k) && (typeof v === "string" || typeof v === "number")) {
        hits.push({ path: path + "." + k, value: String(v).slice(0, 80) });
      } else if (v && typeof v === "object") {
        hits.push(...deepFind(v, keys, depth + 1, path + "." + k));
      }
    }
    return hits;
  }

  async function run() {
    const sub = await j(
      `/courseapi/v3/portal-home-setting/get-sub-info?course_id=${courseId}&sub_id=${subId}&tenant_code=${tenant}`
    );
    const data = (sub.json && sub.json.data) || {};
    const rid = String(data.resource_id || "");
    send({
      kind: "ppt-subinfo",
      status: sub.status,
      rid,
      is_export: data.is_export,
      sub_title: data.sub_title,
      lecturer: data.lecturer_name,
      duration: data.duration,
      is_open_note: data.is_open_note,
      course_type: data.course_type,
    });
    if (!rid) return;

    // 1) 全量 PPT 页：imgurl + timestamp(ms)
    const pd = await j(`/spidermaterial/spider-material/web/aitask/async/getPPTData?id=${rid}`);
    const arr = Array.isArray(pd.json && pd.json.data) ? pd.json.data : [];
    send({
      kind: "ppt-pages",
      status: pd.status,
      count: arr.length,
      pages: arr.map((x) => ({
        t: x.timestamp,
        img: x.imgurl,
        type: x.type,
        desc: x.describe || "",
      })),
    });

    // 2) 能不能导出原始课件（type=4 是 PPT）
    for (const [label, qs, opts] of [
      ["ppt", "type=4", null],
      ["ppt_src", "type=4&get_source_url=1", null],
    ]) {
      const ex = await j(`/courseapi/v2/export/get-courseware-status?${qs}&sub_id=${subId}`, opts);
      send({
        kind: "ppt-export",
        which: label,
        status: ex.status,
        code: ex.json && ex.json.code,
        msg: ex.json && ex.json.msg,
        dataKeys: ex.json && ex.json.data ? Object.keys(ex.json.data) : null,
        file_name: ex.json && ex.json.data && ex.json.data.file_name,
        path_name: ex.json && ex.json.data && ex.json.data.path_name,
      });
    }

    // 3) 顺便看看有没有笔记/字幕类的现成资源
    const note = await j(`/courseapi/v2/export/get-courseware-status?type=3&sub_id=${subId}`);
    send({
      kind: "ppt-export",
      which: "note_type3",
      status: note.status,
      code: note.json && note.json.code,
      dataKeys: note.json && note.json.data ? Object.keys(note.json.data) : null,
      file_name: note.json && note.json.data && note.json.data.file_name,
      path_name: note.json && note.json.data && note.json.data.path_name,
    });
  }

  setTimeout(() => {
    run().catch((e) => send({ kind: "ppt-error", msg: String(e) }));
  }, 4000);
})();
