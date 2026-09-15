"""Minimal dashboard: stdlib HTTP server serving JSON + a single HTML page from the journal."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from ..memory.journal import Journal

HTML = """<!doctype html><html><head><meta charset=utf-8><title>Crypto Fund</title>
<style>body{font-family:system-ui;margin:24px;background:#0f1115;color:#e6e6e6}table{border-collapse:collapse;width:100%}
td,th{padding:6px 10px;border-bottom:1px solid #333;text-align:left}.k{color:#8a8}h2{margin-top:28px}.bad{color:#e66}.good{color:#6e6}</style></head>
<body><h1>Crypto AI Fund</h1><div id=summary></div><h2>Open positions</h2><table id=pos></table>
<h2>Recent decisions</h2><table id=dec></table><h2>Recent trades</h2><table id=tr></table><h2>Events</h2><ul id=ev></ul>
<script>
async function load(){const d=await (await fetch('/api/state')).json();
const s=d.summary;document.getElementById('summary').innerHTML=
`<p>Mode <b>${s.mode}</b> · Regime <b>${s.regime}</b> · Limits ${s.limits_hash}</p>
<p>Start $${s.start.toFixed(2)} · Value <b>$${s.equity.toFixed(2)}</b> · Return <b class="${s.ret>=0?'good':'bad'}">${(s.ret*100).toFixed(1)}%</b>
· Drawdown ${(s.drawdown*100).toFixed(1)}% · Cash ${(s.cash_pct*100).toFixed(0)}% · Risk level ${s.risk_level}</p>`;
const rows=(t,h,arr,f)=>{document.getElementById(t).innerHTML='<tr>'+h.map(x=>'<th>'+x+'</th>').join('')+'</tr>'+arr.map(r=>'<tr>'+f(r).map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')};
rows('pos',['Token','Entry','Stop','Target','Strategy','Opened'],d.positions,p=>[p.symbol,p.entry,p.trailing_stop||p.stop,JSON.parse(p.targets).slice(-1)[0],p.strategy,new Date(p.opened_at*1000).toLocaleString()]);
rows('dec',['Time','Asset','Strategy','Decision','Quality','Regime','Veto','Exec'],d.decisions,x=>[new Date(x.timestamp*1000).toLocaleString(),x.asset,x.strategy,x.decision,x.trade_quality.toFixed(0),x.regime,x.veto?'YES':'',x.executed?'YES':'']);
rows('tr',['Time','Asset','Strategy','Entry','Exit','P&L','R','Reason'],d.trades,x=>[new Date(x.timestamp*1000).toLocaleString(),x.asset,x.strategy,x.entry,x.exit,x.pnl_usd.toFixed(2),x.r_multiple.toFixed(2),x.exit_reason]);
document.getElementById('ev').innerHTML=d.events.map(e=>`<li><span class=k>${new Date(e.timestamp*1000).toLocaleString()}</span> [${e.level}] ${e.message}</li>`).join('');}
load();setInterval(load,15000);</script></body></html>"""


def build_state(journal: Journal) -> dict:
    snaps = journal.snapshots(1)
    last = snaps[-1] if snaps else {"equity": 100, "cash": 100, "drawdown": 0, "regime": "-", "mode": "-", "limits_hash": "-"}
    start = journal.get("starting_capital", 100.0)
    return {
        "summary": {"start": start, "equity": last["equity"], "cash_pct": last["cash"] / last["equity"] if last["equity"] else 1,
                    "ret": last["equity"] / start - 1, "drawdown": last["drawdown"], "regime": last["regime"],
                    "mode": last["mode"], "limits_hash": last["limits_hash"],
                    "risk_level": "LOW" if last["drawdown"] < 0.05 else "MEDIUM" if last["drawdown"] < 0.12 else "HIGH"},
        "positions": [dict(r) for r in journal.conn.execute("SELECT * FROM positions")],
        "decisions": journal.decisions(20), "trades": journal.trades()[-20:][::-1], "events": journal.events(20),
        "weekly_review": journal.get("last_weekly_review"), "equity_curve": journal.snapshots(300),
    }


def serve(db_path: str, port: int = 8080) -> None:
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/state"):
                body = json.dumps(build_state(Journal(db_path)), default=str).encode()
                ctype = "application/json"
            else:
                body, ctype = HTML.encode(), "text/html"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # quiet
            pass

    print(f"Dashboard on http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), H).serve_forever()
