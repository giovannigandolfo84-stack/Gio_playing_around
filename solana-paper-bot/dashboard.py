"""Tiny local dashboard at http://localhost:8000 (only reachable from this Mac)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def build_state(portfolio_path, log_path, title):
    try:
        with open(portfolio_path) as f:
            p = json.load(f)
    except (OSError, ValueError):
        p = {"starting_balance": 0, "cash": 0, "open": [], "closed": []}
    decisions = []
    try:
        with open(log_path) as f:
            lines = f.readlines()[-200:]
        decisions = [json.loads(x) for x in reversed(lines) if x.strip()]
    except (OSError, ValueError):
        pass

    closed = p.get("closed", [])
    wins = [t["pnl_usd"] for t in closed if t["pnl_usd"] > 0]
    losses = [t["pnl_usd"] for t in closed if t["pnl_usd"] <= 0]
    start = p.get("starting_balance") or 0
    equity = p.get("cash", 0) + sum(o["tokens"] * o["last_price"] for o in p.get("open", []))
    return {
        "title": title,
        "updated_at": p.get("updated_at"),
        "cash": p.get("cash", 0),
        "equity": equity,
        "start": start,
        "return_pct": (equity / start - 1) * 100 if start else 0,
        "win_rate": len(wins) / len(closed) * 100 if closed else None,
        "avg_win": sum(wins) / len(wins) if wins else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "worst_loss": min((t["pnl_pct"] for t in closed if t["pnl_usd"] <= 0), default=None),
        "halted": p.get("halted_day"),
        "open": p.get("open", []),
        "closed": list(reversed(closed)),
        "decisions": decisions,
    }


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Paper Bot</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2330;--muted:#6b7385;--line:#e3e6eb;--good:#11845b;--bad:#c63b3b;--accent:#3b5bdb}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--card:#1b2029;--text:#e6e9ef;--muted:#949cad;--line:#2b313d;--good:#3ecf8e;--bad:#ff6b6b;--accent:#7c95ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:16px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:24px 0 8px}.muted{color:var(--muted)}
.banner{background:var(--accent);color:#fff;padding:6px 10px;border-radius:6px;display:inline-block;font-weight:600;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.card b{display:block;font-size:20px;font-variant-numeric:tabular-nums}.card span{color:var(--muted);font-size:12px}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:6px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:500;font-size:12px}td.r{white-space:normal;min-width:280px}
.good{color:var(--good)}.bad{color:var(--bad)}.tag{font-weight:700;font-size:12px}
.BUY{color:var(--good)}.SELL{color:var(--accent)}.SKIP{color:var(--muted)}.WAIT{color:#d08c00}.HALT{color:var(--bad)}
a{color:var(--accent)}
</style></head><body>
<span class="banner">PAPER TRADING — FAKE MONEY ONLY</span>
<h1 id="title">Paper Bot</h1><div class="muted" id="upd"></div>
<div class="grid" id="cards"></div>
<h2>Open trades</h2><div class="wrap"><table id="open"></table></div>
<h2>Closed trades</h2><div class="wrap"><table id="closed"></table></div>
<h2>Latest decisions</h2><div class="wrap"><table id="dec"></table></div>
<script>
const $=id=>document.getElementById(id);
const usd=v=>v==null?"–":(v<0?"-$":"$")+Math.abs(v).toFixed(2);
const pct=v=>v==null?"–":(v>0?"+":"")+v.toFixed(1)+"%";
const cls=v=>v==null?"":v>0?"good":v<0?"bad":"";
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const t=s=>typeof s==="number"?new Date(s*1000).toLocaleString():s?new Date(s).toLocaleString():"";
const sym=o=>o.url?`<a href="${esc(o.url)}" target="_blank">${esc(o.symbol)}</a>`:esc(o.symbol);
function table(el,head,rows,empty){el.innerHTML="<tr>"+head.map(h=>`<th>${h}</th>`).join("")+"</tr>"+
 (rows.length?rows.join(""):`<tr><td colspan="${head.length}" class="muted">${empty}</td></tr>`)}
async function load(){
 let s; try{s=await (await fetch("/api/state",{cache:"no-store"})).json()}catch(e){$("upd").textContent="Bot not running (dashboard can't reach it).";return}
 $("title").textContent=s.title; $("upd").textContent="Last update: "+(t(s.updated_at)||"waiting for first cycle…")+(s.halted?" · Buying paused today (daily loss limit)":"");
 const c=[["Total balance",usd(s.equity),""],["Cash",usd(s.cash),""],["Return",pct(s.return_pct),cls(s.return_pct)],
  ["Win rate",s.win_rate==null?"–":s.win_rate.toFixed(0)+"%",""],["Avg win",usd(s.avg_win),"good"],["Avg loss",usd(s.avg_loss),"bad"],
  ["Worst loss",pct(s.worst_loss),cls(s.worst_loss)],["Open / closed",s.open.length+" / "+s.closed.length,""]];
 $("cards").innerHTML=c.map(([k,v,k2])=>`<div class="card"><span>${k}</span><b class="${k2}">${v}</b></div>`).join("");
 table($("open"),["Coin","Bought","Cost","Entry price","Now","Change","Value"],s.open.map(o=>{const ch=(o.last_price/o.entry_price-1)*100;
  return `<tr><td>${sym(o)}</td><td>${t(o.entry_time)}</td><td>${usd(o.cost_usd)}</td><td>${o.entry_price.toPrecision(4)}</td><td>${o.last_price.toPrecision(4)}</td><td class="${cls(ch)}">${pct(ch)}</td><td>${usd(o.tokens*o.last_price)}</td></tr>`}),"No open trades");
 table($("closed"),["Coin","Sold","Cost","Got back","P/L","Why"],s.closed.slice(0,100).map(o=>
  `<tr><td>${sym(o)}</td><td>${t(o.exit_time)}</td><td>${usd(o.cost_usd)}</td><td>${usd(o.proceeds_usd)}</td><td class="${cls(o.pnl_usd)}">${usd(o.pnl_usd)} (${pct(o.pnl_pct)})</td><td class="r">${esc(o.exit_reason)}</td></tr>`),"No closed trades yet");
 table($("dec"),["Time","Action","Coin","Reason"],s.decisions.slice(0,100).map(d=>
  `<tr><td>${t(d.time)}</td><td class="tag ${esc(d.action)}">${esc(d.action)}</td><td>${esc(d.symbol||"")}</td><td class="r">${esc(d.reason)}</td></tr>`),"No decisions yet");
}
load(); setInterval(load,5000);
</script></body></html>"""


def start_dashboard(port, portfolio_path, log_path, title):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/state"):
                body = json.dumps(build_state(portfolio_path, log_path, title)).encode()
                ctype = "application/json"
            elif self.path in ("/", "/index.html"):
                body, ctype = PAGE.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)  # raises OSError if port busy
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
