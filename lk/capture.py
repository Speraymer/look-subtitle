"""本地服务：接扩展上报、给页面发字幕、提供字幕全文页。

  POST /report                    扩展上报（落 captures/*.jsonl）
  GET  /subtitles?sub_id=...      返回该小节字幕 JSON（扩展叠字幕用）
  GET  /view?sub_id=...           字幕全文页（可搜索、点行跳转）
  GET  /download?sub_id=..&fmt=   下载 srt/vtt
  GET  /health
"""

import glob
import json
import os
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .paths import CAPTURES, WORKS

PORT = 8765

PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
 :root{color-scheme:dark}*{box-sizing:border-box}
 body{margin:0;background:#12161c;color:#dfe6ee;font-family:'Microsoft YaHei',system-ui,sans-serif}
 header{position:sticky;top:0;z-index:5;background:#12161c;border-bottom:1px solid #253040;padding:14px 20px 10px}
 h1{margin:0 0 4px;font-size:16px;font-weight:600;color:#eaf3ff}
 .meta{font-size:12px;color:#7f8fa3}
 .tools{display:flex;gap:10px;align-items:center;margin-top:10px}
 input{flex:1;max-width:420px;padding:7px 11px;border-radius:6px;border:1px solid #2b3646;
       background:#1a2129;color:#dfe6ee;font-size:13px;outline:none}
 input:focus{border-color:#3d7fd6}
 .count{font-size:12px;color:#7f8fa3}
 main{padding:10px 20px 60px}
 .row{display:flex;gap:14px;padding:4px 8px;border-radius:5px;cursor:pointer;align-items:flex-start}
 .row:hover{background:#1a2230}.row.hit{background:#1d2b3f}
 .t{flex:0 0 62px;color:#5fb0ff;font-variant-numeric:tabular-nums;font-family:Consolas,monospace;
    font-size:12px;padding-top:2px}
 .x{flex:1;font-size:14px;line-height:1.6}
 .x em{background:#3a2f00;color:#ffd777;font-style:normal;border-radius:2px}
 .toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);background:#2a6fd6;color:#fff;
        padding:8px 16px;border-radius:20px;font-size:13px;opacity:0;transition:opacity .2s;pointer-events:none}
 .toast.on{opacity:.95}
 .hint{font-size:12px;color:#5d6b7d;margin-top:6px}
</style></head><body>
<header><h1>__TITLE__</h1><div class="meta">__META__</div>
<div class="tools"><input id="q" placeholder="搜全文…" autofocus><span class="count" id="count"></span></div>
<div class="hint" id="hint">点一行跳到视频那个位置（需要扩展在场）；没扩展就复制时间</div></header>
<main id="list"></main><div class="toast" id="toast"></div>
<script>window.__DATA__ = __DATASET__;</script>
<script>
(function(){
 var D=window.__DATA__,list=document.getElementById('list'),q=document.getElementById('q'),
     count=document.getElementById('count'),toastEl=document.getElementById('toast');
 function pad(n){return String(n).padStart(2,'0')}
 function fmt(t){var h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=Math.floor(t%60);
   return h?h+':'+pad(m)+':'+pad(s):pad(m)+':'+pad(s)}
 function render(f){
  f=(f||'').trim(); var frag=document.createDocumentFragment(),n=0;
  for(var i=0;i<D.segments.length;i++){var s=D.segments[i];
   if(f&&s.text.indexOf(f)===-1)continue;
   var row=document.createElement('div');row.className='row';row.dataset.t=s.start;
   var t=document.createElement('span');t.className='t';t.textContent=fmt(s.start);
   var x=document.createElement('span');x.className='x';
   if(f){var k=s.text.indexOf(f);
     x.appendChild(document.createTextNode(s.text.slice(0,k)));
     var em=document.createElement('em');em.textContent=f;x.appendChild(em);
     x.appendChild(document.createTextNode(s.text.slice(k+f.length)));}
   else{x.textContent=s.text;}
   row.appendChild(t);row.appendChild(x);frag.appendChild(row);n++;}
  list.replaceChildren(frag);count.textContent=n+' / '+D.segments.length+' 段';}
 var timer=null;q.addEventListener('input',function(){clearTimeout(timer);
   timer=setTimeout(function(){render(q.value)},120)});
 var tt=null;function toast(m){toastEl.textContent=m;toastEl.classList.add('on');
   clearTimeout(tt);tt=setTimeout(function(){toastEl.classList.remove('on')},1100)}
 list.addEventListener('click',function(e){
  var row=e.target.closest('.row');if(!row)return;
  document.querySelectorAll('.row.hit').forEach(function(r){r.classList.remove('hit')});
  row.classList.add('hit');var t=parseFloat(row.dataset.t);
  if(document.documentElement.dataset.lookViewer){toast('已跳到 '+fmt(t));return}
  navigator.clipboard.writeText(fmt(t)).then(function(){toast('已复制 '+fmt(t))}).catch(function(){})});
 render('');
})();
</script></body></html>"""


def _find_subtitles(sub_id):
    """works/<id>/segments.json 优先，其次 sub_<id>.json（旧格式）。"""
    from .paths import Work

    w = Work(sub_id)
    for p in (w.segments, w.dir / f"sub_{sub_id}.json"):
        if p.exists():
            return p
    for f in glob.glob(str(WORKS / "*" / "segments.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            if str(d.get("sub_id")) == str(sub_id):
                return f
        except Exception:
            continue
    return None


def _find_sub_file(sub_id, fmt):
    from .paths import Work

    w = Work(sub_id)
    p = w.srt if fmt == "srt" else w.vtt
    return p if p.exists() else None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        sub_id = (qs.get("sub_id") or [""])[0]

        if u.path == "/health":
            return self._send(200, {"ok": True, "port": PORT})

        if u.path == "/subtitles":
            p = _find_subtitles(sub_id) if sub_id else None
            if not p:
                return self._send(404, {"ok": False, "msg": f"no subtitles for {sub_id}"})
            d = json.load(open(p, encoding="utf-8"))
            d["ok"] = True
            d["source"] = os.path.basename(p)
            return self._send(200, d)

        if u.path in ("/view", "/"):
            p = _find_subtitles(sub_id) if sub_id else None
            if not p:
                return self._send(404, {"ok": False, "msg": f"no subtitles for {sub_id}"})
            d = json.load(open(p, encoding="utf-8"))
            segs = d.get("segments") or []
            dur = float(d.get("duration") or 0)
            meta = f"sub_id {sub_id} · {int(dur//3600)} 小时 {int(dur%3600//60):02d} 分 · {len(segs)} 段"
            html = (
                PAGE.replace("__TITLE__", f"课程字幕 · {sub_id}")
                .replace("__META__", meta)
                .replace("__DATASET__", json.dumps({"segments": segs}, ensure_ascii=False).replace("</", "<\\/"))
            )
            return self._send(200, html.encode("utf-8"), "text/html")

        if u.path == "/download":
            fmt = (qs.get("fmt") or ["srt"])[0].lower()
            if fmt not in ("srt", "vtt"):
                return self._send(400, {"ok": False, "msg": "fmt must be srt or vtt"})
            p = _find_sub_file(sub_id, fmt)
            if not p:
                return self._send(404, {"ok": False, "msg": f"no {fmt}"})
            return self._send(200, open(p, "rb").read(), "text/plain")

        return self._send(404, {"ok": False})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            payload = {"kind": "raw", "raw": raw[:2000].decode("utf-8", "replace")}
        f = CAPTURES / (datetime.now().strftime("probe-%Y%m%d-%H%M") + ".jsonl")
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        tag = payload.get("url") or payload.get("sub_id") or ""
        print(f"[{datetime.now():%H:%M:%S}] {payload.get('kind'):<14} {str(tag)[:100]}", flush=True)
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


def serve(port=PORT, block=True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"look capture on http://127.0.0.1:{port}", flush=True)
    print("  扩展已装的话，去课程页按 F5，等 10 秒；Ctrl+C 结束。", flush=True)
    if block:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
    else:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else PORT)
