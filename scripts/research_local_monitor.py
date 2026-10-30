"""Read-only localhost campaign monitor and verified strategy comparisons.

No external bind, write API, market ZIP, broker access or OOS certification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from scripts.materialize_arithmetic_generation import _load_strict

MAX_STATUS_BYTES = 128 * 1024
_VALID_STATES = frozenset({
    "RUNNING_OBSERVED", "PAUSED_TIME_BUDGET_BETWEEN_GENERATIONS",
    "PAUSED_DISK_BUDGET", "COMPLETE_TRAINING_ONLY_NOT_OOS",
    "FAILED_REQUIRES_EVIDENCE_REVIEW",
})
_VALID_COMPLETED = frozenset({
    "EXECUTED_AND_VERIFIED_FEEDBACK", "REUSED_FULLY_REAUDITED_FEEDBACK",
})
_HEX64 = re.compile(r"[0-9a-f]{64}\\Z".replace("\\\\", "\\"))


def safe_status(root: Path, *, current: datetime | None = None) -> dict:
    """Return minimal, safe status; never expose paths or trade-level data."""
    path = root / "campaign_status.json"
    if path.is_symlink():
        raise ValueError("Unsafe campaign status symlink")
    if not path.exists():
        return {"state": "NOT_STARTED", "completed_generations": 0,
                "independent_oos_proven": False}
    if not path.is_file() or path.stat().st_size > MAX_STATUS_BYTES:
        raise ValueError("Unsafe campaign status snapshot")
    data, _ = _load_strict(path)
    if (type(data) is not dict or data.get("schema") != "NRFX_ARITHMETIC_CAMPAIGN_V1"
            or data.get("training_only") is not True
            or data.get("independent_oos_proven") is not False
            or data.get("live_trading_authorized") is not False
            or type(data.get("status")) is not str
            or data["status"] not in _VALID_STATES
            or type(data.get("completed")) is not list
            or type(data.get("first_generation")) is not int
            or data["first_generation"] < 1
            or type(data.get("requested_generations")) is not int
            or not 1 <= data["requested_generations"] <= 200
            or len(data["completed"]) > data["requested_generations"]):
        raise ValueError("Campaign status lacks safe training provenance")
    completed = []
    for row in data["completed"]:
        if (type(row) is not dict or set(row) !=
                {"generation", "status", "input_sha256"}
                or type(row["generation"]) is not int
                or row["generation"] != data["first_generation"] + len(completed)
                or type(row["status"]) is not str
                or row["status"] not in _VALID_COMPLETED
                or type(row["input_sha256"]) is not str
                or _HEX64.fullmatch(row["input_sha256"]) is None):
            raise ValueError("Malformed campaign progress record")
        completed.append({"generation": row["generation"], "status": row["status"]})
    if (data["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"
            and len(completed) != data["requested_generations"]):
        raise ValueError("Incomplete campaign cannot claim completion")
    try:
        updated = datetime.fromisoformat(data["updated_utc"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Campaign missing UTC observation timestamp") from exc
    if updated.tzinfo is None or updated.utcoffset() != timedelta(0):
        raise ValueError("Campaign observation timestamp must be UTC")
    now = datetime.now(timezone.utc) if current is None else current
    if type(now) is not datetime or now.tzinfo is None:
        raise ValueError("Monitor clock must be timezone aware")
    elapsed = (now.astimezone(timezone.utc) - updated).total_seconds()
    if elapsed < -60:
        raise ValueError("Campaign observation timestamp is in the future")
    age = max(0, int(elapsed))
    return {"state": data["status"], "completed_generations": len(completed),
            "completed": completed, "last_update_utc": updated.isoformat(),
            "seconds_since_update": age,
            "observation_stale": age > 600 and data["status"] == "RUNNING_OBSERVED",
            "training_only": True, "independent_oos_proven": False,
            "live_trading_authorized": False}


HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>No Risk FX | Research Monitor</title><style>
body{background:#081626;color:#e9effa;font:16px system-ui;margin:0;padding:26px}main{max-width:1180px;margin:auto}
h1{color:#dcc181}.row{display:flex;gap:12px;flex-wrap:wrap}.card{background:#14263e;padding:20px;flex:1;min-width:180px;border:1px solid #334760;border-radius:12px}
small{color:#ddbb7e}.warning{border-left:3px solid #d6b777;background:#1b2c42;padding:12px}p{color:#a8bbd1}
input{background:#14263e;color:white;border:1px solid #4c5f78;border-radius:7px;padding:10px}
button{background:#263c57;color:white;padding:10px;border:1px solid #56708c;border-radius:7px;cursor:pointer}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:10px;text-align:left;border-bottom:1px solid #30435b}
.wrap{max-height:570px;overflow:auto}.err{color:#ffaaaa}
</style></head><body><main><small>NO RISK FX / LOCAL RESEARCH</small><h1>Quant Research Control Plane</h1>
<p class="warning">TRAINING ONLY — NOT INDEPENDENT OOS. No broker trading or raw price data.</p>
<section class="row"><div class="card"><small>CAMPAIGN STATUS</small><h2 id="state">Loading</h2></div>
<div class="card"><small>COMPLETED GENERATIONS</small><h2 id="count">—</h2></div>
<div class="card"><small>UPDATED UTC</small><h2 id="updated">—</h2></div></section>
<h2>Verified training comparisons</h2><input id="filter" type="search" placeholder="Filter strategies">
<button id="refresh">Refresh</button><p id="error" class="err"></p>
<div class="wrap"><table><thead><tr><th>Generation</th><th>Formula</th><th>Net USD/oz</th>
<th>Positive months</th><th>Training score</th><th>Failure diagnostics</th></tr></thead><tbody id="rows"></tbody></table></div>
<script>
let rows=[];const escapeHTML=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(){let q=document.getElementById('filter').value.toLowerCase();document.getElementById('rows').innerHTML=rows.filter(x=>JSON.stringify(x).toLowerCase().includes(q)).map(x=>'<tr>'+[x.g,x.id.substring(0,16),x.net,x.months,x.score,x.reason].map(t=>'<td>'+escapeHTML(t)+'</td>').join('')+'</tr>').join('');}
async function refresh(){try{let [sr,gr]=await Promise.all([fetch('/api/status',{cache:'no-store'}),fetch('/api/generations',{cache:'no-store'})]);if(!sr.ok||!gr.ok)throw Error('Verified evidence unavailable');let s=await sr.json(),gs=await gr.json();
document.getElementById('state').textContent=s.state+(s.observation_stale?' (STALE)':'');
document.getElementById('count').textContent=s.completed_generations;document.getElementById('updated').textContent=s.last_update_utc||'—';
rows=gs.flatMap(g=>(g.items||[]).map(i=>({g:g.generation,id:i.identity,net:i.net_usd_per_oz,months:i.positive_months+'/'+i.total_months,score:i.training_score,reason:(i.failure_reasons||[]).join(', ')})));render();document.getElementById('error').textContent='';
}catch(err){document.getElementById('error').textContent=err.message;}}
document.getElementById('refresh').addEventListener('click',refresh);document.getElementById('filter').addEventListener('input',render);refresh();setInterval(refresh,15000);
</script></main></body></html>""".encode("utf-8")


def make_handler(root: Path):
    from scripts.research_training_dashboard import read_evidence

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # A loopback socket alone does not prevent DNS rebinding: a
            # malicious website may resolve its own hostname to 127.0.0.1.
            # Require the exact Host printed by main() before reading data.
            host_headers = self.headers.get_all("Host", [])
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if len(host_headers) != 1 or host_headers[0] != expected_host:
                self.send_error(403, "Invalid loopback Host")
                return
            endpoint = urlsplit(self.path).path
            if endpoint not in ("/", "/api/status", "/api/generations"):
                self.send_error(404, "Unknown endpoint")
                return
            try:
                if endpoint == "/":
                    payload, mime = HTML, "text/html; charset=utf-8"
                elif endpoint == "/api/status":
                    payload = json.dumps(safe_status(root), allow_nan=False).encode()
                    mime = "application/json; charset=utf-8"
                else:
                    location = root / "cycles" if (root / "cycles").is_dir() else root
                    payload = json.dumps(read_evidence(location),allow_nan=False).encode()
                    mime = "application/json; charset=utf-8"
            except (OSError, TypeError, KeyError, ValueError):
                self.send_error(503, "Verified research evidence unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if (not 1024 <= args.port <= 65535 or args.campaign.is_symlink()
            or not args.campaign.is_dir()):
        raise ValueError("Unsafe local monitor directory or port")
    with ThreadingHTTPServer(("127.0.0.1", args.port),
                             make_handler(args.campaign)) as server:
        print(f"Local-only research monitor: http://127.0.0.1:{args.port}/",flush=True)
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
