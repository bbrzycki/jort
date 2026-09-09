"""Local, authenticated monitoring dashboard for Jort tracked jobs."""

import hmac
import json
import os
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config
from . import database
from . import datetime_utils


DEFAULT_HISTORY_LIMIT = 100
MAX_HISTORY_LIMIT = 500
MAX_TAIL_BYTES = 64 * 1024
MAX_TAIL_LINES = 200


def _public_job(payload):
    """Return the fields the local UI needs; no file paths or argv are exposed."""
    metrics = payload.get("metrics") or {}
    return {
        "job_id": payload.get("job_id"),
        "name": payload.get("name"),
        "session_name": payload.get("session_name"),
        "status": payload.get("status"),
        "date_created": payload.get("date_created"),
        "date_modified": payload.get("date_modified"),
        "runtime": payload.get("runtime") or 0.0,
        "pid": payload.get("pid"),
        "exit_code": payload.get("exit_code"),
        "error_message": payload.get("error_message"),
        "has_output": bool(payload.get("stdout_fn")),
        "metrics": {
            "rss_bytes": metrics.get("rss_bytes") or 0,
            "peak_rss_bytes": metrics.get("peak_rss_bytes") or 0,
            "cpu_user_seconds": metrics.get("cpu_user_seconds") or 0.0,
            "cpu_system_seconds": metrics.get("cpu_system_seconds") or 0.0,
            "child_process_count": metrics.get("child_process_count") or 0,
        },
    }


def snapshot(history_limit=DEFAULT_HISTORY_LIMIT):
    """Return a bounded, redacted view of active jobs and recent history."""
    jobs = database.list_dashboard_jobs(limit=history_limit)
    active_statuses = {"queued", "running"}
    active = [_public_job(job) for job in jobs if job.get("status") in active_statuses]
    history = [_public_job(job) for job in jobs if job.get("status") not in active_statuses]
    return {
        "generated_at": datetime_utils.get_iso_date(),
        "active": active,
        "history": history,
    }


def _tail_path(payload):
    """Resolve only Jort-managed captured output files for dashboard reading."""
    filename = payload.get("stdout_fn")
    if not filename or os.path.isabs(filename):
        return None
    data_dir = os.path.realpath(config._get_data_dir())
    path = os.path.realpath(os.path.join(data_dir, filename))
    if not path.startswith(data_dir + os.sep):
        return None
    return path


def output_tail(job_id, max_bytes=MAX_TAIL_BYTES, max_lines=MAX_TAIL_LINES):
    """Return a bounded, end-of-file output tail for a tracked job."""
    payload = database.get_job(job_id)
    if payload is None:
        return None
    path = _tail_path(payload)
    if path is None:
        return {"available": False, "text": "No captured output is available for this job."}
    try:
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - max_bytes), os.SEEK_SET)
            data = stream.read(max_bytes)
    except FileNotFoundError:
        return {"available": False, "text": "Captured output has not been written yet."}
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if size > max_bytes:
        lines.insert(0, "[jort] showing the most recent output only")
    return {"available": True, "text": "\n".join(lines[-max_lines:])}


def _dashboard_html(token, nonce):
    token_json = json.dumps(token)
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jort Monitor</title>
  <style nonce="{nonce}">
    :root { color-scheme: dark; --bg:#111318; --surface:#1b1f27; --surface-2:#232936; --line:#303848; --text:#f4f7fb; --muted:#a5b0c4; --accent:#78a9ff; --good:#6fdb9b; --bad:#ff8a9b; --warn:#ffd478; }
    * { box-sizing:border-box; }
    body { margin:0; background:radial-gradient(circle at top left,#1c2943 0,transparent 34rem),var(--bg); color:var(--text); font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    main { max-width:1180px; margin:0 auto; padding:40px 24px 64px; }
    header { display:flex; justify-content:space-between; gap:24px; align-items:flex-end; margin-bottom:32px; }
    h1 { font-size:28px; margin:0; letter-spacing:-.03em; }
    h2 { font-size:16px; margin:0; }
    p { color:var(--muted); margin:6px 0 0; }
    .meta { text-align:right; color:var(--muted); font-size:12px; }
    .section { margin-top:28px; }
    .section-title { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:12px; }
    .cards { display:grid; gap:12px; }
    .card, .history { border:1px solid var(--line); border-radius:14px; background:color-mix(in srgb,var(--surface) 94%,transparent); overflow:hidden; }
    .job { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:18px; padding:18px; }
    .job-title { display:flex; gap:9px; align-items:center; min-width:0; }
    .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:620; }
    .badge { flex:0 0 auto; border-radius:999px; padding:3px 8px; font-size:11px; font-weight:650; text-transform:uppercase; letter-spacing:.04em; background:#34435c; color:#dbe7ff; }
    .badge.running { background:#173d31; color:var(--good); } .badge.queued { background:#4a3b1c; color:var(--warn); } .badge.success { background:#173d31; color:var(--good); } .badge.error,.badge.terminated,.badge.timeout { background:#4b2631; color:var(--bad); }
    .stats { display:flex; flex-wrap:wrap; gap:8px 18px; margin-top:10px; color:var(--muted); font-size:12px; }
    .actions { display:flex; align-items:center; }
    button { appearance:none; border:1px solid #4b5b74; border-radius:8px; padding:7px 10px; background:var(--surface-2); color:var(--text); font:inherit; cursor:pointer; } button:hover { border-color:var(--accent); } button:disabled { opacity:.45; cursor:default; }
    .empty { padding:24px; color:var(--muted); text-align:center; }
    .history-controls { display:flex; gap:12px; align-items:center; }
    input { min-width:220px; border:1px solid var(--line); border-radius:8px; padding:8px 10px; background:var(--surface); color:var(--text); font:inherit; }
    table { width:100%; border-collapse:collapse; } th,td { padding:12px 14px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; } th { color:var(--muted); font-size:11px; letter-spacing:.06em; text-transform:uppercase; font-weight:650; } tr:last-child td { border-bottom:0; } td.command { max-width:560px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    dialog { width:min(920px,calc(100vw - 32px)); height:min(70vh,740px); padding:0; color:var(--text); background:var(--surface); border:1px solid #52617a; border-radius:14px; box-shadow:0 24px 80px #0009; } dialog::backdrop { background:#0009; } .dialog-header { display:flex; justify-content:space-between; align-items:center; padding:14px 16px; border-bottom:1px solid var(--line); } pre { margin:0; padding:16px; height:calc(100% - 58px); overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; color:#d9e6fb; font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }
    @media (max-width:700px) { main { padding:24px 14px; } header,.section-title { align-items:flex-start; flex-direction:column; } .meta { text-align:left; } .job { grid-template-columns:1fr; } .actions { justify-content:flex-start; } table th:nth-child(3), table td:nth-child(3) { display:none; } input { min-width:0; width:100%; } .history-controls { width:100%; } }
  </style>
</head>
<body>
  <main>
    <header><div><h1>Jort Monitor</h1><p>Local job activity and history. Output is loaded only when you ask for it.</p></div><div class="meta" id="updated">Connecting…</div></header>
    <section class="section"><div class="section-title"><div><h2>Active jobs</h2><p>Queued and running Jort jobs refresh every second.</p></div></div><div id="active" class="cards"></div></section>
    <section class="section"><div class="section-title"><div><h2>Recent history</h2><p>Persisted Jort jobs on this machine.</p></div><div class="history-controls"><input id="filter" type="search" placeholder="Filter commands or sessions"></div></div><div class="history"><table><thead><tr><th>Status</th><th>Command</th><th>Session</th><th>Runtime</th><th>Finished</th><th></th></tr></thead><tbody id="history"></tbody></table></div></section>
  </main>
  <dialog id="output-dialog"><div class="dialog-header"><strong id="output-title">Output</strong><button id="close-output">Close</button></div><pre id="output"></pre></dialog>
  <script nonce="{nonce}">
    const token = {token_json};
    const api = path => `${path}?token=${encodeURIComponent(token)}`;
    let latest = {active: [], history: []};
    const fmtSeconds = value => { value = Number(value || 0); if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`; const m = Math.floor(value / 60); const s = Math.floor(value % 60); return m < 60 ? `${m}m ${s}s` : `${Math.floor(m / 60)}h ${m % 60}m`; };
    const fmtBytes = value => { value = Number(value || 0); if (!value) return '—'; const units=['B','KB','MB','GB']; let index=0; while(value>=1024 && index<units.length-1) { value/=1024; index++; } return `${value.toFixed(index ? 1 : 0)} ${units[index]}`; };
    const escape = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
    const jobCard = job => { const m=job.metrics || {}; const label=job.status === 'running' ? 'Running' : 'Queued'; return `<article class="card"><div class="job"><div><div class="job-title"><span class="badge ${escape(job.status)}">${label}</span><span class="name" title="${escape(job.name)}">${escape(job.name)}</span></div><div class="stats"><span>${escape(job.session_name || 'Uncategorized')}</span><span>${fmtSeconds(job.runtime)}</span><span>CPU ${fmtSeconds((m.cpu_user_seconds || 0) + (m.cpu_system_seconds || 0))}</span><span>Memory ${fmtBytes(m.rss_bytes)}${m.peak_rss_bytes ? ` · peak ${fmtBytes(m.peak_rss_bytes)}` : ''}</span><span>${m.child_process_count || 0} child process${m.child_process_count === 1 ? '' : 'es'}</span></div></div><div class="actions"><button ${job.has_output ? `data-output-job="${escape(job.job_id)}"` : 'disabled'}>Output tail</button></div></div></article>`; };
    function render() { document.getElementById('active').innerHTML = latest.active.length ? latest.active.map(jobCard).join('') : '<div class="card empty">No tracked jobs are currently active.</div>'; const q=document.getElementById('filter').value.trim().toLowerCase(); const rows=latest.history.filter(j => !q || `${j.name} ${j.session_name || ''}`.toLowerCase().includes(q)).map(j => `<tr><td><span class="badge ${escape(j.status)}">${escape(j.status)}</span></td><td class="command" title="${escape(j.name)}">${escape(j.name)}</td><td>${escape(j.session_name || '—')}</td><td>${fmtSeconds(j.runtime)}</td><td>${escape((j.date_modified || '').replace('T',' ').replace(/\\+.*/,''))}</td><td><button ${j.has_output ? `data-output-job="${escape(j.job_id)}"` : 'disabled'}>Output</button></td></tr>`).join(''); document.getElementById('history').innerHTML = rows || '<tr><td colspan="6" class="empty">No matching job history.</td></tr>'; }
    async function refresh() { try { const r=await fetch(api('/api/status'),{cache:'no-store'}); if(!r.ok) throw new Error('status unavailable'); latest=await r.json(); render(); document.getElementById('updated').textContent=`Updated ${new Date().toLocaleTimeString()} · local only`; } catch(error) { document.getElementById('updated').textContent='Monitor unavailable; retrying…'; } }
    async function showOutput(jobId) { const dialog=document.getElementById('output-dialog'); document.getElementById('output-title').textContent='Captured output'; document.getElementById('output').textContent='Loading…'; dialog.showModal(); try { const r=await fetch(api(`/api/jobs/${encodeURIComponent(jobId)}/tail`),{cache:'no-store'}); const value=await r.json(); document.getElementById('output').textContent=value.text || 'No output available.'; } catch(error) { document.getElementById('output').textContent='Unable to read captured output.'; } }
    document.addEventListener('click', event => { const button=event.target.closest('[data-output-job]'); if (button && !button.disabled) showOutput(button.dataset.outputJob); }); document.getElementById('close-output').addEventListener('click',()=>document.getElementById('output-dialog').close()); document.getElementById('filter').addEventListener('input',render); refresh(); setInterval(refresh,1000);
  </script>
</body>
</html>"""
    return template.replace("{token_json}", token_json).replace("{nonce}", nonce)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Serve a small loopback-only monitor without request logging noise."""

    def __init__(self, *args, token, nonce, history_limit, **kwargs):
        self._token = token
        self._nonce = nonce
        self._history_limit = history_limit
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        del format, args

    def _authorized(self, query):
        token = query.get("token", [""])[0]
        return hmac.compare_digest(token, self._token)

    def _json(self, status, payload):
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorized(query):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if parsed.path == "/api/status":
            self._json(HTTPStatus.OK, snapshot(self._history_limit))
            return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/tail"):
            job_id = parsed.path[len("/api/jobs/"):-len("/tail")].rstrip("/")
            tail = output_tail(job_id)
            if tail is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "job not found"})
            else:
                self._json(HTTPStatus.OK, tail)
            return
        if parsed.path == "/":
            encoded = _dashboard_html(self._token, self._nonce).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; connect-src 'self'; "
                f"style-src 'nonce-{self._nonce}'; script-src 'nonce-{self._nonce}'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)
            return
        self.send_error(HTTPStatus.NOT_FOUND)


def create_server(host="127.0.0.1", port=0, history_limit=DEFAULT_HISTORY_LIMIT,
                  token=None):
    """Create a loopback dashboard server and its capability URL."""
    if host != "127.0.0.1":
        raise ValueError("Jort dashboard may bind only to 127.0.0.1")
    history_limit = max(1, min(int(history_limit), MAX_HISTORY_LIMIT))
    token = token or secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(16)

    def handler(*args, **kwargs):
        return DashboardRequestHandler(
            *args,
            token=token,
            nonce=nonce,
            history_limit=history_limit,
            **kwargs,
        )

    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    server_url = f"http://{host}:{server.server_address[1]}/?token={token}"
    return server, server_url


def serve(host="127.0.0.1", port=0, history_limit=DEFAULT_HISTORY_LIMIT,
          open_browser=True):
    """Run the dashboard until the caller interrupts it."""
    server, url = create_server(host=host, port=port, history_limit=history_limit)
    print(f"Jort Monitor: {url}", flush=True)
    print("Press Ctrl+C to stop the local monitor.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
