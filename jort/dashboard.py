"""Local, authenticated monitoring dashboard for Jort tracked jobs."""

import hmac
import json
import os
import re
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
MAX_PROGRESS_BYTES = 128 * 1024

_ACTIVE_STATUSES = {"queued", "running"}
_SISO_PROGRESS_LINE = re.compile(
    r"^\[(?P<completed>\d+)\s*/\s*(?P<total>\d+)\]\s+"
    r"(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?"
    r"(?P<seconds>\d+(?:\.\d+)?)s\b",
    re.MULTILINE,
)


def _public_job(payload):
    """Return the fields the local UI needs; no file paths or argv are exposed."""
    metrics = payload.get("metrics") or {}
    progress = _progress_from_live_output(payload)
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
        "has_live_output": _live_tail_path(payload) is not None,
        "progress": progress,
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
    active = [_public_job(job) for job in jobs if job.get("status") in _ACTIVE_STATUSES]
    history = [_public_job(job) for job in jobs if job.get("status") not in _ACTIVE_STATUSES]
    return {
        "generated_at": datetime_utils.get_iso_date(),
        "active": active,
        "history": history,
    }


def _managed_output_path(filename):
    """Resolve a relative filename only when it stays inside Jort's data directory."""
    if not filename or os.path.isabs(filename):
        return None
    data_dir = os.path.realpath(config._get_data_dir())
    path = os.path.realpath(os.path.join(data_dir, filename))
    if not path.startswith(data_dir + os.sep):
        return None
    return path


def _tail_path(payload):
    """Resolve the bounded archive used for email and the logs command."""
    return _managed_output_path(payload.get("stdout_fn"))


def _live_tail_path(payload):
    """Resolve a temporary active-job tail without exposing its local path."""
    metadata = payload.get("metadata") or {}
    filename = metadata.get("live_output_fn")
    if payload.get("status") not in _ACTIVE_STATUSES:
        return None
    return _managed_output_path(filename)


def _read_tail(path, max_bytes):
    """Read a bounded suffix without loading an entire local output file."""
    with open(path, "rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - max_bytes), os.SEEK_SET)
        return stream.read(max_bytes), size


def _parse_siso_progress(text):
    """Parse the last trustworthy Siso/Ninja-style progress line, if present."""
    matches = list(_SISO_PROGRESS_LINE.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    completed = int(match.group("completed"))
    total = int(match.group("total"))
    if completed <= 0 or total <= completed:
        return None
    elapsed_seconds = (
        int(match.group("hours") or 0) * 3600
        + int(match.group("minutes") or 0) * 60
        + float(match.group("seconds"))
    )
    if elapsed_seconds <= 0:
        return None
    fraction = completed / total
    progress = {
        "completed": completed,
        "total": total,
        "fraction": fraction,
        "elapsed_seconds": elapsed_seconds,
    }
    # A one-line linear extrapolation is intentionally withheld until the job has
    # made enough observable progress to avoid presenting a spurious ETA.
    if fraction >= 0.01 and elapsed_seconds >= 10:
        progress["remaining_seconds"] = elapsed_seconds * (total - completed) / completed
    return progress


def _progress_from_live_output(payload):
    """Derive an explicitly approximate progress snapshot from an active live tail."""
    path = _live_tail_path(payload)
    if path is None:
        return None
    try:
        data, _ = _read_tail(path, MAX_PROGRESS_BYTES)
    except FileNotFoundError:
        return None
    return _parse_siso_progress(data.decode("utf-8", errors="replace"))


def output_tail(job_id, max_bytes=MAX_TAIL_BYTES, max_lines=MAX_TAIL_LINES):
    """Return a bounded end-of-file tail, preferring active live output."""
    payload = database.get_job(job_id)
    if payload is None:
        return None
    path = _live_tail_path(payload)
    source = "live" if path is not None else "captured"
    if path is None:
        path = _tail_path(payload)
    if path is None:
        return {"available": False, "text": "No captured output is available for this job."}
    try:
        data, size = _read_tail(path, max_bytes)
    except FileNotFoundError:
        if source == "live":
            archive = _tail_path(payload)
            if archive is not None:
                path = archive
                source = "captured"
                try:
                    data, size = _read_tail(path, max_bytes)
                except FileNotFoundError:
                    return {"available": False, "text": "Captured output has not been written yet."}
            else:
                return {"available": False, "text": "Live output has not been written yet."}
        else:
            return {"available": False, "text": "Captured output has not been written yet."}
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return {
        "available": True,
        "source": source,
        "truncated": size > max_bytes or len(lines) > max_lines,
        "text": "\n".join(lines[-max_lines:]),
    }


def _dashboard_html(token, nonce):
    token_json = json.dumps(token)
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jort — Job Monitor</title>
  <style nonce="__JORT_NONCE__">
    :root { color-scheme:dark; --page:#111214; --panel:#181a1e; --panel-raised:#1e2127; --line:#2d3139; --line-strong:#3c424d; --text:#eef0f3; --muted:#979eaa; --faint:#656c78; --focus:#8ab4f8; --success:#63c98d; --warning:#d9a441; --danger:#f1767f; }
    * { box-sizing:border-box; }
    body { margin:0; min-width:320px; background:var(--page); color:var(--text); font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    button,input { font:inherit; }
    button { color:inherit; }
    .topbar { height:52px; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; padding:0 28px; background:#15171a; }
    .brand { display:flex; align-items:center; gap:10px; font-weight:670; letter-spacing:.01em; }
    .brand-mark { width:18px; height:18px; border:2px solid #d8dce3; border-radius:4px; position:relative; } .brand-mark::after { content:""; width:5px; height:5px; position:absolute; right:-4px; bottom:-4px; border:2px solid #d8dce3; border-radius:2px; background:#15171a; }
    .product { color:var(--muted); font-size:12px; font-weight:500; border-left:1px solid var(--line-strong); padding-left:10px; }
    .connection { display:flex; align-items:center; gap:7px; color:var(--muted); font-size:12px; } .connection-dot { width:7px; height:7px; border-radius:50%; background:var(--success); box-shadow:0 0 0 3px #21372a; }
    main { max-width:1440px; margin:0 auto; padding:30px 28px 44px; }
    .page-heading { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin-bottom:20px; } h1 { margin:0; font-size:22px; line-height:1.15; letter-spacing:-.025em; font-weight:650; } .subheading { color:var(--muted); margin:5px 0 0; }
    .refresh-meta { display:flex; align-items:center; gap:12px; color:var(--muted); font-size:12px; white-space:nowrap; } .quiet-button { appearance:none; border:1px solid var(--line-strong); border-radius:6px; background:transparent; padding:6px 9px; cursor:pointer; } .quiet-button:hover { border-color:var(--focus); color:#fff; }
    .summary { display:flex; border:1px solid var(--line); border-radius:8px; background:var(--panel); margin-bottom:20px; overflow:hidden; } .metric { min-width:116px; padding:12px 16px; border-right:1px solid var(--line); } .metric-progress { min-width:184px; } .metric:last-child { border-right:0; } .metric-value { display:block; font-size:18px; line-height:1.1; font-weight:640; font-variant-numeric:tabular-nums; } .metric-label { display:block; margin-top:4px; color:var(--muted); font-size:11px; letter-spacing:.045em; text-transform:uppercase; }
    .monitor-grid { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(340px,.9fr); gap:16px; align-items:stretch; } .panel { border:1px solid var(--line); border-radius:8px; background:var(--panel); overflow:hidden; } .panel-head { height:48px; display:flex; justify-content:space-between; align-items:center; padding:0 16px; border-bottom:1px solid var(--line); } .panel-title { font-size:13px; font-weight:640; } .panel-detail { color:var(--muted); font-size:12px; }
    .job-list { min-height:202px; } .job-row { width:100%; display:grid; grid-template-columns:12px minmax(0,1fr) auto auto; gap:12px; align-items:center; padding:13px 16px; border:0; border-bottom:1px solid var(--line); background:transparent; text-align:left; cursor:pointer; } .job-row:last-child { border-bottom:0; } .job-row:hover { background:var(--panel-raised); } .job-row.is-selected { box-shadow:inset 2px 0 0 var(--focus); background:#1d232d; } .job-row:focus-visible,.history-command:focus-visible,.quiet-button:focus-visible,input:focus-visible { outline:2px solid var(--focus); outline-offset:-2px; }
    .status-dot { width:8px; height:8px; border-radius:50%; background:var(--faint); } .status-dot.running { background:var(--success); box-shadow:0 0 0 3px #20382a; } .status-dot.queued { background:var(--warning); } .status-dot.error,.status-dot.terminated,.status-dot.timeout { background:var(--danger); } .status-dot.success { background:var(--success); }
    .job-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:590; } .job-context { display:flex; gap:8px; margin-top:3px; color:var(--muted); font-size:12px; overflow:hidden; } .job-context span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; } .job-context span+span::before { content:"/"; color:var(--faint); margin-right:8px; }
    .job-stat { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; text-align:right; white-space:nowrap; } .job-runtime { min-width:58px; color:var(--text); font-size:13px; font-weight:590; font-variant-numeric:tabular-nums; text-align:right; white-space:nowrap; }
    .empty { display:grid; min-height:202px; place-items:center; padding:24px; color:var(--muted); text-align:center; }
    .inspector { display:flex; flex-direction:column; min-height:250px; } .inspector-meta { padding:14px 16px 12px; border-bottom:1px solid var(--line); } .inspector-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:600; } .inspector-summary { display:flex; gap:8px; margin-top:5px; color:var(--muted); font-size:12px; } .inspector-summary span+span::before { content:"·"; color:var(--faint); margin-right:8px; }
    .output { flex:1; min-height:218px; max-height:430px; margin:0; padding:14px 16px; overflow:auto; color:#d5dae3; background:#15171a; font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; tab-size:2; } .output-empty { display:grid; place-items:center; color:var(--muted); font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; text-align:center; }
    .history-panel { margin-top:16px; } .history-toolbar { display:flex; align-items:center; gap:12px; } input { width:248px; border:1px solid var(--line-strong); border-radius:6px; padding:6px 9px; background:#15171a; color:var(--text); } input::placeholder { color:var(--faint); }
    .history-wrap { overflow:auto; } table { width:100%; border-collapse:collapse; } th,td { padding:10px 16px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; } th { color:var(--muted); font-size:10px; font-weight:650; letter-spacing:.07em; text-transform:uppercase; } tr:last-child td { border-bottom:0; } td.command { max-width:0; width:54%; } .history-command { display:block; width:100%; padding:0; border:0; background:transparent; color:var(--text); overflow:hidden; text-align:left; text-overflow:ellipsis; white-space:nowrap; cursor:pointer; } .history-command:hover { color:#fff; text-decoration:underline; } .state { display:inline-flex; align-items:center; gap:7px; color:var(--muted); font-size:12px; } .runtime,.finished { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; white-space:nowrap; }
    @media (max-width:900px) { .monitor-grid { grid-template-columns:1fr; } .inspector { min-height:280px; } }
    @media (max-width:680px) { .topbar { padding:0 16px; } main { padding:22px 14px 34px; } .page-heading { align-items:flex-start; flex-direction:column; } .summary { overflow:auto; } .metric { min-width:104px; padding:10px 12px; } .job-row { grid-template-columns:10px minmax(0,1fr) auto; gap:9px; padding:12px; } .job-stat { display:none; } .history-toolbar { width:100%; } input { width:100%; } th:nth-child(3),td:nth-child(3),th:nth-child(5),td:nth-child(5) { display:none; } th,td { padding:10px 12px; } }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand"><span class="brand-mark" aria-hidden="true"></span><span>Jort</span><span class="product">Job monitor</span></div>
    <div class="connection"><span class="connection-dot" aria-hidden="true"></span><span>Local monitor</span></div>
  </header>
  <main>
    <div class="page-heading"><div><h1>Jobs</h1><p class="subheading">Tracked commands on this machine.</p></div><div class="refresh-meta"><span id="updated">Connecting</span><button class="quiet-button" id="refresh" type="button">Refresh</button></div></div>
    <section class="summary" aria-label="Job summary" id="summary"></section>
    <div class="monitor-grid">
      <section class="panel" aria-labelledby="active-heading"><div class="panel-head"><span class="panel-title" id="active-heading">Active jobs</span><span class="panel-detail" id="active-count"></span></div><div class="job-list" id="active"></div></section>
      <aside class="panel inspector" aria-labelledby="inspector-heading"><div class="panel-head"><span class="panel-title" id="inspector-heading">Output inspector</span><span class="panel-detail" id="output-kind">Last 200 lines</span></div><div class="inspector-meta" id="inspector-meta"></div><pre class="output output-empty" id="output">Select a job to inspect its captured output.</pre></aside>
    </div>
    <section class="panel history-panel" aria-labelledby="history-heading"><div class="panel-head"><span class="panel-title" id="history-heading">Recent history</span><div class="history-toolbar"><input id="filter" type="search" placeholder="Filter jobs or sessions" aria-label="Filter job history"></div></div><div class="history-wrap"><table><thead><tr><th>Status</th><th>Command</th><th>Session</th><th>Runtime</th><th>Completed</th></tr></thead><tbody id="history"></tbody></table></div></section>
  </main>
  <script nonce="__JORT_NONCE__">
    const token = __JORT_TOKEN__;
    const api = path => `${path}?token=${encodeURIComponent(token)}`;
    let latest = {active: [], history: []};
    let selectedJobId = null;
    let loadedOutputFor = null;
    let outputRequestFor = null;
    const fmtSeconds = value => { value = Number(value || 0); if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`; const m=Math.floor(value/60),s=Math.floor(value%60); return m<60 ? `${m}m ${s}s` : `${Math.floor(m/60)}h ${m%60}m`; };
    const fmtBytes = value => { value=Number(value||0); if (!value) return '—'; const units=['B','KB','MB','GB']; let i=0; while(value>=1024&&i<units.length-1){value/=1024;i++;} return `${value.toFixed(i?1:0)} ${units[i]}`; };
    const escape = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
    const statusLabel = status => ({running:'Running',queued:'Queued',success:'Completed',error:'Failed',terminated:'Terminated',timeout:'Timed out'}[status] || status);
    const allJobs = () => [...latest.active, ...latest.history];
    const selectedJob = () => allJobs().find(job => job.job_id === selectedJobId);
    const progressLabel = job => { const p=job.progress; if(!p)return null; const percent=`${(p.fraction*100).toFixed(p.fraction<.1?1:0)}%`; return p.remaining_seconds==null ? `${percent} · estimating` : `${percent} · ~${fmtSeconds(p.remaining_seconds)} remaining`; };
    const progressDetail = job => { const p=job.progress; if(!p)return null; const estimate=p.remaining_seconds==null ? 'estimating from build output' : `~${fmtSeconds(p.remaining_seconds)} remaining`; return `${p.completed.toLocaleString()} / ${p.total.toLocaleString()} · ${estimate}`; };
    const resourceSummary = job => { const m=job.metrics||{}; const cpu=(m.cpu_user_seconds||0)+(m.cpu_system_seconds||0); const progress=progressLabel(job); return `${progress ? `${progress} · ` : ''}CPU ${fmtSeconds(cpu)} · ${fmtBytes(m.rss_bytes)} memory${m.child_process_count ? ` · ${m.child_process_count} child` : ''}`; };
    const row = job => `<button type="button" class="job-row ${job.job_id===selectedJobId?'is-selected':''}" data-job-id="${escape(job.job_id)}"><span class="status-dot ${escape(job.status)}" aria-hidden="true"></span><span><span class="job-name" title="${escape(job.name)}">${escape(job.name)}</span><span class="job-context"><span>${escape(job.session_name||'Uncategorized')}</span><span>${escape(statusLabel(job.status))}</span></span></span><span class="job-stat">${escape(resourceSummary(job))}</span><span class="job-runtime">${fmtSeconds(job.runtime)}</span></button>`;
    function renderSummary() { const running=latest.active.filter(job=>job.status==='running').length, queued=latest.active.filter(job=>job.status==='queued').length, failed=latest.history.filter(job=>['error','terminated','timeout'].includes(job.status)).length, selected=selectedJob(), progress=selected&&progressLabel(selected); document.getElementById('summary').innerHTML=`<div class="metric"><span class="metric-value">${latest.active.length}</span><span class="metric-label">Active</span></div><div class="metric"><span class="metric-value">${running}</span><span class="metric-label">Running</span></div><div class="metric"><span class="metric-value">${queued}</span><span class="metric-label">Queued</span></div><div class="metric metric-progress"><span class="metric-value">${progress||'—'}</span><span class="metric-label">Selected-job estimate</span></div><div class="metric"><span class="metric-value">${failed}</span><span class="metric-label">Recent failures</span></div>`; }
    function renderActive() { const active=document.getElementById('active'); active.innerHTML=latest.active.length ? latest.active.map(row).join('') : '<div class="empty">No tracked jobs are currently active.</div>'; document.getElementById('active-count').textContent=latest.active.length ? `${latest.active.length} live` : 'Idle'; }
    function renderHistory() { const query=document.getElementById('filter').value.trim().toLowerCase(); const jobs=latest.history.filter(job=>!query||`${job.name} ${job.session_name||''}`.toLowerCase().includes(query)); document.getElementById('history').innerHTML=jobs.length ? jobs.map(job=>`<tr><td><span class="state"><span class="status-dot ${escape(job.status)}" aria-hidden="true"></span>${escape(statusLabel(job.status))}</span></td><td class="command"><button type="button" class="history-command" data-job-id="${escape(job.job_id)}" title="${escape(job.name)}">${escape(job.name)}</button></td><td>${escape(job.session_name||'—')}</td><td class="runtime">${fmtSeconds(job.runtime)}</td><td class="finished">${escape((job.date_modified||'').replace('T',' ').replace(/\\+.*/,''))}</td></tr>`).join('') : '<tr><td colspan="5" class="empty">No jobs match this filter.</td></tr>'; }
    function renderInspector() { const job=selectedJob(), kind=document.getElementById('output-kind'); const meta=document.getElementById('inspector-meta'), output=document.getElementById('output'); if(!job){kind.textContent='Last 200 lines'; meta.innerHTML='<div class="inspector-name">No job selected</div><div class="inspector-summary"><span>Select an active or historical job.</span></div>'; output.textContent='Select a job to inspect its captured output.'; output.classList.add('output-empty'); return;} const detail=progressDetail(job); kind.textContent=job.has_live_output?'Live tail · last 200 lines':'Captured output · last 200 lines'; meta.innerHTML=`<div class="inspector-name" title="${escape(job.name)}">${escape(job.name)}</div><div class="inspector-summary"><span>${escape(statusLabel(job.status))}</span><span>${fmtSeconds(job.runtime)}</span><span>${escape(job.session_name||'Uncategorized')}</span>${detail?`<span>${escape(detail)}</span>`:''}</div>`; if(!job.has_output){output.textContent='This job was not started with captured output.'; output.classList.add('output-empty');} else if(loadedOutputFor!==job.job_id){output.textContent=job.has_live_output?'Loading live output…':'Loading captured output…'; output.classList.remove('output-empty');} }
    function render() { renderSummary(); renderActive(); renderHistory(); renderInspector(); }
    async function loadOutput(jobId, quiet=false) { const job=allJobs().find(item=>item.job_id===jobId); const output=document.getElementById('output'), kind=document.getElementById('output-kind'); if(!job||!job.has_output||outputRequestFor===jobId){return;} outputRequestFor=jobId; if(!quiet){output.textContent=job.has_live_output?'Loading live output…':'Loading captured output…'; output.classList.remove('output-empty');} try { const response=await fetch(api(`/api/jobs/${encodeURIComponent(jobId)}/tail`),{cache:'no-store'}); const body=await response.json(); if(selectedJobId!==jobId)return; loadedOutputFor=jobId; kind.textContent=body.source==='live'?'Live tail · last 200 lines':'Captured output · last 200 lines'; output.textContent=body.text||'No captured output is available.'; output.classList.toggle('output-empty',!body.available); } catch(error) { if(selectedJobId===jobId){output.textContent='Unable to read captured output.'; output.classList.add('output-empty');} } finally { if(outputRequestFor===jobId)outputRequestFor=null; } }
    function selectJob(jobId) { selectedJobId=jobId; loadedOutputFor=null; render(); loadOutput(jobId); }
    async function refresh() { try { const response=await fetch(api('/api/status'),{cache:'no-store'}); if(!response.ok)throw new Error('status unavailable'); latest=await response.json(); if(!selectedJob()&&latest.active.length){selectedJobId=latest.active[0].job_id; loadedOutputFor=null;} render(); const current=selectedJob(); if(current&&current.has_output&&['running','queued'].includes(current.status)){loadOutput(current.job_id,true);} else if(current&&current.has_output&&loadedOutputFor!==current.job_id){loadOutput(current.job_id);} document.getElementById('updated').textContent=`Updated ${new Date().toLocaleTimeString()}`; } catch(error) { document.getElementById('updated').textContent='Connection lost — retrying'; } }
    document.addEventListener('click',event=>{const target=event.target.closest('[data-job-id]'); if(target)selectJob(target.dataset.jobId);}); document.getElementById('filter').addEventListener('input',renderHistory); document.getElementById('refresh').addEventListener('click',refresh); refresh(); setInterval(refresh,1000);
  </script>
</body>
</html>"""
    return template.replace("__JORT_TOKEN__", token_json).replace("__JORT_NONCE__", nonce)


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
