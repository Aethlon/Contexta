"""Build the CHIMERA HTML report from a run's artifacts.

Reads the summary JSON, the per-question JSONL log, and the ingestion dump
produced by run_benchmark.py, then renders a single self-contained HTML file
containing:

  - headline accuracy + retrieval latency percentiles
  - per-category table (accuracy + p50/p95 latency)
  - ingestion panel: the async 202/outbox drain log per session, an explicit note
    on which per-session counters the API cannot expose, and the full list of
    memory rows Contexta persisted
  - a searchable per-question audit log showing, for every question:
      question | category | verdict
      reference answer + reference (ground-truth) context
      what was saved in the DB while extracting
      what Contexta retrieved and gave the agent (with scores)
      what the agent answered
      timing breakdown (retrieve / answer / total)

Usage:
    python benchmarks/CHIMERA/report.py --tag run_20260101-120000
    python benchmarks/CHIMERA/report.py --latest
"""

from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

CHIMERA_DIR = Path(__file__).resolve().parent
RESULTS_DIR = CHIMERA_DIR / "results"

CSS = """
:root{--bg:#0d1117;--panel:#161b22;--border:#30363d;--txt:#c9d1d9;--dim:#8b949e;
--pass:#3fb950;--fail:#f85149;--warn:#d29922;--accent:#58a6ff;--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
h1,h2,h3{margin:0;font-weight:600}
header{padding:24px 28px;border-bottom:1px solid var(--border);background:var(--panel)}
header h1{font-size:20px;letter-spacing:.5px}
header .sub{color:var(--dim);font-size:12px;margin-top:6px;font-family:var(--mono)}
main{padding:20px 28px 60px;max-width:1500px}
section{margin-bottom:32px}
h2{font-size:15px;text-transform:uppercase;letter-spacing:1px;color:var(--accent);margin-bottom:12px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px 16px}
.card .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.6px}
.card .v{font-size:22px;font-weight:600;margin-top:6px;font-family:var(--mono)}
.card .n{color:var(--dim);font-size:11px;margin-top:2px}
table{width:100%;border-collapse:collapse;background:var(--panel);
border:1px solid var(--border);border-radius:8px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--border);font-size:13px}
th{background:#1c2128;color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.6px;font-weight:600}
tr:last-child td{border-bottom:none}
tbody tr:hover{background:#1c2128}
.pass{color:var(--pass);font-weight:600}
.fail{color:var(--fail);font-weight:600}
.mono{font-family:var(--mono);font-size:12px}
.dim{color:var(--dim)}
.bar{height:6px;background:#21262d;border-radius:3px;overflow:hidden;min-width:70px}
.bar>span{display:block;height:100%;background:var(--accent)}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;
font-family:var(--mono);border:1px solid var(--border)}
.pill.pass{color:var(--pass);border-color:var(--pass)}
.pill.fail{color:var(--fail);border-color:var(--fail)}
.pill.warn{color:var(--warn);border-color:var(--warn)}
input[type=search]{width:100%;padding:10px 14px;background:var(--panel);
border:1px solid var(--border);border-radius:8px;color:var(--txt);font-size:13px;margin-bottom:12px}
input[type=search]:focus{outline:none;border-color:var(--accent)}
details{background:var(--panel);border:1px solid var(--border);border-radius:8px;margin-bottom:8px}
summary{cursor:pointer;padding:11px 14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
summary:hover{background:#1c2128}
summary .qid{font-family:var(--mono);color:var(--dim);min-width:70px}
summary .qt{flex:1;min-width:260px}
summary .t{font-family:var(--mono);color:var(--dim);font-size:11px}
.body{padding:0 14px 14px;display:none}
details[open] .body{display:block}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.box{border:1px solid var(--border);border-radius:6px;padding:10px 12px;background:#0d1117}
.box .lbl{color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}
.box .val{font-family:var(--mono);font-size:12px;white-space:pre-wrap;word-break:break-word}
.ctx-item{border-left:2px solid var(--border);padding:5px 10px;margin-bottom:5px;background:#0d1117}
.ctx-item .h{font-family:var(--mono);font-size:11px;color:var(--dim);margin-bottom:2px}
.ctx-item .c{font-size:12px;white-space:pre-wrap;word-break:break-word}
.flag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;
font-family:var(--mono);background:#21262d;border:1px solid var(--border);margin-right:4px}
.flag.bad{color:var(--fail);border-color:var(--fail)}
.scroll{max-height:420px;overflow:auto;border:1px solid var(--border);border-radius:8px}
.scroll table{border:none}
.empty{color:var(--dim);padding:16px;font-style:italic}
pre{background:#0d1117;border:1px solid var(--border);border-radius:6px;
padding:10px 12px;overflow:auto;font-family:var(--mono);font-size:11px;max-height:340px;margin:0}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
"""

JS = """
function filterQ(){
  var t=document.getElementById('q').value.toLowerCase();
  var c=document.getElementById('c').value;
  var v=document.getElementById('v').value;
  document.querySelectorAll('details.q').forEach(function(d){
    var okT=d.dataset.q.toLowerCase().indexOf(t)>-1;
    var okC=!c||d.dataset.cat===c;
    var okV=!v||d.dataset.verdict===v;
    d.style.display=(okT&&okC&&okV)?'':'none';
  });
  var n=document.querySelectorAll('details.q:not([style*="none"])').length;
  document.getElementById('shown').textContent=n+' shown';
}
document.addEventListener('DOMContentLoaded',function(){
  ['q','c','v'].forEach(function(i){
    var e=document.getElementById(i);
    if(e) e.addEventListener('input',filterQ);
  });
  var one=document.querySelector('details.q');
  if(one) one.open=true;
});
"""


def esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""))


def cell(value: Any) -> str:
    """Render a value, or 'n/a' when the API cannot expose it.

    The ingestion counters the old in-process harness read out of
    MemoryPipelineResult do not exist in any HTTP response body, so the summary
    carries null for them. Rendering null as 0 would read as "zero extracted",
    which is a claim the benchmark can no longer make.
    """
    if value is None:
        return "<span class='dim'>n/a</span>"
    return esc(value)


def latest_tag() -> str | None:
    logs = [p for p in RESULTS_DIR.glob("chimera_*.jsonl") if not p.name.endswith(".ingest.json")]
    if not logs:
        return None
    newest = max(logs, key=lambda p: p.stat().st_mtime)
    return newest.stem[len("chimera_") :]


def load_run(tag: str) -> tuple[list[dict], dict, dict]:
    log = RESULTS_DIR / f"chimera_{tag}.jsonl"
    summary = RESULTS_DIR / f"chimera_{tag}.summary.json"
    ingest = RESULTS_DIR / f"chimera_{tag}.ingest.json"
    records = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    s = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    g = json.loads(ingest.read_text(encoding="utf-8")) if ingest.exists() else {}
    return records, s, g


def cat_table(records: list[dict], summary: dict) -> str:
    by = summary.get("by_category", {})
    rows = []
    for cat in sorted(by, key=lambda c: (-by[c]["pass"] / max(by[c]["total"], 1), c)):
        d = by[cat]
        acc = d["accuracy"]
        rows.append(
            f"<tr><td class='mono'>{esc(cat)}</td>"
            f"<td class='mono'>{d['pass']}/{d['total']}</td>"
            f"<td><div class='bar'><span style='width:{acc*100:.0f}%'></span></div></td>"
            f"<td class='mono'>{acc*100:.1f}%</td>"
            f"<td class='mono'>{d.get('retrieve_p50_ms',0)}</td>"
            f"<td class='mono'>{d.get('retrieve_p95_ms',0)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Category</th><th>Passed</th><th></th>"
        "<th>Accuracy</th><th>Retrieve p50 (ms)</th><th>Retrieve p95 (ms)</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def question_detail(rec: dict, stored_lookup: dict[str, list[dict]]) -> str:
    flags = "".join(
        f"<span class='flag {'bad' if f in ('hallucinated','leaked') else ''}'>{esc(f)}</span>"
        for f in rec.get("verdict_flags", [])
    )
    t = rec.get("timing_ms", {})
    rc = rec.get("reference_context", {}) or {}

    ref_facts = "".join(
        f"<div class='ctx-item'><div class='h'>{esc(f.get('predicate'))} = {esc(f.get('value'))}"
        f" &middot; {esc(f.get('status'))} &middot; {esc(f.get('timestamp'))}</div>"
        f"<div class='c'>{esc(f.get('id'))}</div></div>"
        for f in rc.get("required_facts", [])
    )
    ref_commits = "".join(
        f"<div class='ctx-item'><div class='h'>{esc(c.get('diff_type'))} &middot; {esc(c.get('timestamp'))}</div>"
        f"<div class='c'>{esc(c.get('content'))}</div></div>"
        for c in rc.get("required_commits", [])
    )
    distractors = "".join(
        f"<div class='ctx-item'><div class='h'>distractor &middot; {esc(f.get('status'))}</div>"
        f"<div class='c'>{esc(f.get('predicate'))} = {esc(f.get('value'))}</div></div>"
        for f in rc.get("distractor_facts", [])
    )

    ctx = "".join(
        f"<div class='ctx-item'><div class='h'>score {c['score']} &middot; sem {c['semantic']} "
        f"&middot; kw {c['keyword']} &middot; graph {c['graph']} &middot; rec {c['recency']} "
        f"&middot; imp {c['importance']} &middot; [{esc(c['type'])}|{esc(c['state'])}]</div>"
        f"<div class='c'>{esc(c['content'])}</div></div>"
        for c in rec.get("context_given_to_agent", [])
    ) or "<div class='empty'>nothing retrieved</div>"

    # memories persisted by Contexta for the sessions that back this question
    stored = stored_lookup.get(rec["id"], [])

    return f"""
<details class="q" data-q="{esc(rec.get('question',''))}" data-cat="{esc(rec.get('category',''))}" data-verdict="{esc(rec.get('verdict',''))}">
<summary>
  <span class="pill {'pass' if rec['verdict']=='PASS' else 'fail'}">{esc(rec['verdict'])}</span>
  <span class="qid">{esc(rec.get('id'))}</span>
  <span class="qt">{esc(rec.get('question'))}</span>
  <span class="pill">{esc(rec.get('category'))}</span>
  <span class="t">ret {t.get('retrieve',0)}ms &middot; ans {t.get('answer',0)}ms</span>
</summary>
<div class="body">
  <div class="grid2">
    <div class="box"><div class="lbl">Question</div><div class="val">{esc(rec.get('question'))}</div></div>
    <div class="box"><div class="lbl">Verdict &amp; reason</div>
      <div class="val"><span class="{'pass' if rec['verdict']=='PASS' else 'fail'}">{esc(rec['verdict'])}</span>
      &mdash; {esc(rec.get('verdict_reason'))} {flags}</div></div>
    <div class="box"><div class="lbl">Reference (gold) answer</div><div class="val">{esc(rec.get('reference_answer'))}</div></div>
    <div class="box"><div class="lbl">Agent answer</div><div class="val">{esc(rec.get('agent_answer'))}</div></div>
  </div>

  <h3 style="margin:16px 0 8px;font-size:13px">Reference context (ground truth &mdash; what should have been recoverable)</h3>
  <div class="grid2">
    <div><div class="lbl dim" style="margin-bottom:4px">required facts</div>{ref_facts or '<div class="empty">none</div>'}</div>
    <div><div class="lbl dim" style="margin-bottom:4px">required commits</div>{ref_commits or '<div class="empty">none</div>'}</div>
  </div>
  {f'<h3 style="margin:16px 0 8px;font-size:13px">Reference distractors</h3>{distractors}' if distractors else ''}

  <h3 style="margin:16px 0 8px;font-size:13px">What Contexta gave the agent ({len(rec.get('context_given_to_agent',[]))} memories, ranked)</h3>
  <div class="scroll">{ctx}</div>

  <h3 style="margin:16px 0 8px;font-size:13px">Saved in DB while extracting</h3>
  <pre>{esc(json.dumps(stored, indent=2) if stored else 'no per-question snapshot recorded')}</pre>

  <div class="grid2" style="margin-top:12px">
    <div class="box"><div class="lbl">Timing</div><div class="val">retrieve: {t.get('retrieve',0)} ms
answer:   {t.get('answer',0)} ms
total:    {t.get('total',0)} ms
tokens:   {rec.get('tokens',{}).get('prompt',0)} in / {rec.get('tokens',{}).get('completion',0)} out</div></div>
    <div class="box"><div class="lbl">Errors</div><div class="val">{esc(json.dumps(rec.get('errors',{})))}</div></div>
  </div>
</div>
</details>
"""


def build_html(records: list[dict], summary: dict, ingest: dict, tag: str) -> str:
    empty_sessions_row = "<tr><td colspan='10' class='dim'>no sessions</td></tr>"
    t = summary.get("totals", {})
    lat = summary.get("latency", {})
    r_ms = lat.get("retrieve_ms", {})
    a_ms = lat.get("answer_ms", {})
    ing = summary.get("ingestion", {})
    meta = summary.get("meta", {})
    flags = summary.get("flags", {})

    cards = f"""
<div class="cards">
  <div class="card"><div class="k">Accuracy</div>
    <div class="v {'pass' if t.get('accuracy',0)>=0.5 else 'fail'}">{t.get('accuracy',0)*100:.1f}%</div>
    <div class="n">{t.get('passed',0)} / {t.get('questions',0)} passed</div></div>
  <div class="card"><div class="k">Retrieve p50</div><div class="v">{r_ms.get('p50',0)}<span style="font-size:13px"> ms</span></div>
    <div class="n">mean {r_ms.get('mean',0)} ms</div></div>
  <div class="card"><div class="k">Retrieve p95</div><div class="v">{r_ms.get('p95',0)}<span style="font-size:13px"> ms</span></div>
    <div class="n">p99 {r_ms.get('p99',0)} ms</div></div>
  <div class="card"><div class="k">Answer p50</div><div class="v">{a_ms.get('p50',0)}<span style="font-size:13px"> ms</span></div>
    <div class="n">{esc(meta.get('answer_model','?'))}</div></div>
  <div class="card"><div class="k">Memories stored</div>
    <div class="v">{ing.get('memories_delta_by_drain', 0)}</div>
    <div class="n">from {ing.get('chunks',0)} chunks</div></div>
  <div class="card"><div class="k">Hallucinations</div>
    <div class="v {'fail' if flags.get('hallucinated',0) else 'pass'}">{flags.get('hallucinated',0)}</div>
    <div class="n">{flags.get('leaked',0)} leaked &middot; {flags.get('abstained',0)} abstained</div></div>
</div>
"""

    # per-question stored-memory snapshot: attach every stored memory grouped by
    # nothing more specific than "all", since sessions are global. We show a
    # per-question count and the global store below.
    stored_lookup: dict[str, list[dict]] = defaultdict(list)

    cats = sorted({r.get("category", "") for r in records})
    cat_opts = "".join(f"<option value='{esc(c)}'>{esc(c)}</option>" for c in cats)

    details = "".join(question_detail(r, stored_lookup) for r in records)

    stored_rows = "".join(
        f"<tr><td class='mono'>{esc(m.get('type'))}</td><td>{esc(m.get('title'))}</td>"
        f"<td>{esc(m.get('content'))}</td><td class='mono'>{esc(m.get('state'))}</td>"
        f"<td class='mono'>{esc(m.get('importance'))}</td></tr>"
        for m in ingest.get("stored_memories", [])[:2000]
    )

    per_session = ingest.get("per_session", [])
    session_rows = "".join(
        f"<tr><td class='mono'>{esc(s.get('session_key'))}</td>"
        f"<td>{esc(s.get('domain'))}</td><td class='mono'>{esc(s.get('chunks'))}</td>"
        f"<td class='mono'>{esc(s.get('accept_ms'))} ms</td>"
        f"<td class='mono'>{esc(s.get('drain_ms'))} ms</td>"
        f"<td><span class='pill {'pass' if s.get('status')=='completed' else 'fail'}'>"
        f"{esc(s.get('status') or 'not accepted')}</span></td>"
        f"<td class='mono'>{esc(s.get('attempt_count'))}</td>"
        f"<td class='mono'>{esc(s.get('outbox_status'))}</td>"
        f"<td class='mono'>{esc(s.get('memories_delta'))}</td>"
        f"<td>{esc(s.get('last_error') or s.get('error',''))}</td></tr>"
        for s in per_session
    )
    unobservable = ing.get("unobservable_via_api", [])
    unobservable_note = (
        "<div class='box' style='margin-top:12px'><div class='lbl'>Not observable through the API</div>"
        f"<div class='val'>{esc(', '.join(unobservable))}</div>"
        "<div class='val dim' style='margin-top:6px'>Ingestion is asynchronous: "
        "POST /v1/observations returns 202 and the Celery worker reports no counts back. "
        "Per-session <em>memories delta</em> below is derived by diffing "
        "GET /v1/memories at each drain boundary, and the vector count comes from "
        "GET /v1/memories/search?threshold=0.0.</div></div>"
        if unobservable
        else ""
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CHIMERA report &mdash; {esc(tag)}</title>
<style>{CSS}</style></head><body>
<header>
  <h1>CHIMERA &mdash; Contexta memory evaluation</h1>
  <div class="sub">tag {esc(tag)} &middot; ran {esc(meta.get('ran_at',''))} &middot;
  rerank {esc(meta.get('rerank','off'))} &middot; api {esc(meta.get('api_url',''))} &middot;
  org {esc(meta.get('organization_id',''))} &middot; actor {esc(meta.get('actor_user_id',''))} &middot;
  model {esc(meta.get('answer_model',''))} &middot; k={esc(meta.get('retrieval_limit',''))}</div>
</header>
<main>
  <section><h2>Overview</h2>{cards}</section>

  <section><h2>Per-category results</h2>{cat_table(records, summary)}</section>

  <section><h2>Ingestion</h2>
    <div class="cards">
      <div class="card"><div class="k">Sessions</div><div class="v">{ing.get('sessions',0)}</div>
        <div class="n">{ing.get('observations_completed',0)} completed &middot;
          {ing.get('observations_failed',0)} failed</div></div>
      <div class="card"><div class="k">Memories added by drain</div>
        <div class="v">{ing.get('memories_delta_by_drain',0)}</div>
        <div class="n">extracted / stored: {cell(ing.get('memories_extracted'))} via API</div></div>
      <div class="card"><div class="k">With vectors</div>
        <div class="v">{cell(ing.get('memories_with_vectors'))}</div>
        <div class="n">{cell(ing.get('memories_without_vectors'))} without</div></div>
      <div class="card"><div class="k">Mean drain</div>
        <div class="v">{ing.get('mean_drain_ms',0)}<span style="font-size:13px"> ms</span></div>
        <div class="n">max {ing.get('max_drain_ms',0)} ms</div></div>
    </div>
    {unobservable_note}
    <h3 style="margin:16px 0 8px;font-size:13px">Per-session async drain log</h3>
    <div class="scroll"><table><thead><tr><th>Session</th><th>Domain</th><th>Chunks</th>
      <th>Accept (ms)</th><th>Drain (ms)</th><th>Status</th><th>Attempts</th>
      <th>Outbox</th><th>Memories &Delta;</th><th>Error</th></tr></thead>
      <tbody>{session_rows or empty_sessions_row}</tbody></table></div>
    <h3 style="margin:16px 0 8px;font-size:13px">Memory rows persisted in the database ({len(ingest.get('stored_memories',[]))})</h3>
    <div class="scroll"><table><thead><tr><th>Type</th><th>Title</th><th>Content</th>
      <th>State</th><th>Importance</th></tr></thead>
      <tbody>{stored_rows or '<tr><td colspan="5" class="dim">no memories</td></tr>'}</tbody></table></div>
  </section>

  <section><h2>Per-question audit log</h2>
    <input type="search" id="q" placeholder="search questions, answers, verdicts ...">
    <select id="c"><option value="">all categories</option>{cat_opts}</select>
    <select id="v"><option value="">all verdicts</option><option value="PASS">PASS only</option>
      <option value="FAIL">FAIL only</option></select>
    <div class="dim" id="shown" style="margin:8px 0"></div>
    {details}
  </section>
</main>
<script>{JS}</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Render the CHIMERA HTML report")
    ap.add_argument("--tag", default="")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    tag = args.tag or (latest_tag() if args.latest else "")
    if not tag:
        raise SystemExit("no run found -- pass --tag or --latest")

    records, summary, ingest = load_run(tag)
    page = build_html(records, summary, ingest, tag)
    out = Path(args.out) if args.out else RESULTS_DIR / f"chimera_{tag}.html"
    out.write_text(page, encoding="utf-8")
    print(f"report -> {out}  ({len(records)} questions)")


if __name__ == "__main__":
    main()
