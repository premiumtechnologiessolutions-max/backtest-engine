"""Research-only Gold rejection evidence. No live/OOS approval.

Private owner-only registry. Source evidence must first pass B09 audit.
The SHA chain is LOCAL and is not externally timestamped or tamper-proof.
"""
from __future__ import annotations
import csv, json, os, re, sqlite3, stat
from decimal import Decimal, ROUND_HALF_EVEN
from hashlib import sha256
from pathlib import Path
from .frozen_batch_attestation import verify_frozen_batch_evidence
from scripts import research_batch_orchestrator as batch

SCHEMA="NRFX_SCIENTIFIC_REJECTION_EVIDENCE_V1"
H64=re.compile(r"[a-f0-9]{64}\Z")

def _canonical(x):
    return json.dumps(x,sort_keys=True,ensure_ascii=True,separators=(",",":"),allow_nan=False)
def _hash(x):
    return sha256(_canonical(x).encode("ascii")).hexdigest()
def _money(x):
    if type(x) is not str or not re.fullmatch(r"-?\d+(?:\.\d{1,30})?",x):
        raise ValueError("Invalid private research amount")
    d=Decimal(x)
    if not d.is_finite() or abs(d)>1_000_000_000:
        raise ValueError("Research amount outside bounds")
    return d.quantize(Decimal("0.01"),rounding=ROUND_HALF_EVEN)

def strategy_spec(plan):
    jobs,_=batch.expand(plan,limit=1)
    if len(jobs)!=1 or plan["exposure_context"]!="historical_exposed":
        raise ValueError("Only one frozen historical strategy allowed")
    s=jobs[0]["spec"]
    if s["strategy"]!="m1-sweep" or s["timeframe"]!="M1" or s["execution"]!="reference":
        raise ValueError("Unsupported canonical Gold signal family")
    return {"asset":"XAUUSD","strategy":s["strategy"],"parameters":s["parameters"],
            "timeframe":"M1","execution":"reference","fee_all_in_usd_per_ounce":0.4,
            "quantity_ounces":1.0,"identity_version":1}

def _verify_evidence(e):
    required={"schema","spec","spec_sha256","exposure","disposition","year",
              "monthly","positive_months","months_observed","trades","total_net_usd",
              "original_source_sha256","source_manifest_id","engine_commit",
              "plan_sha256","batch_manifest_sha256","experiment_id",
              "out_of_sample","broker_fills_verified","approved_for_live",
              "profitability_verified"}
    if type(e) is not dict or set(e)!=required or e["schema"]!=SCHEMA:
        raise ValueError("Evidence schema mismatch")
    s=e["spec"]
    if (type(s) is not dict or
        set(s)!={"asset","strategy","parameters","timeframe","execution",
                 "fee_all_in_usd_per_ounce","quantity_ounces","identity_version"}
        or s["asset"]!="XAUUSD" or s["strategy"]!="m1-sweep"
        or s["timeframe"]!="M1" or s["execution"]!="reference"
        or s["fee_all_in_usd_per_ounce"]!=0.4 or s["quantity_ounces"]!=1.0
        or s["identity_version"]!=1 or type(s["parameters"]) is not dict
        or type(e["spec_sha256"]) is not str or e["spec_sha256"]!=_hash(s)):
        raise ValueError("Scientific strategy identity mismatch")
    for name in ("original_source_sha256","source_manifest_id","plan_sha256",
                 "batch_manifest_sha256","experiment_id"):
        if type(e[name]) is not str or not H64.fullmatch(e[name]):
            raise ValueError("Invalid source/evidence fingerprint")
    if type(e["engine_commit"]) is not str or not re.fullmatch(r"[a-f0-9]{40}",e["engine_commit"]):
        raise ValueError("Invalid exact engine commit")
    if (e["exposure"]!="HISTORICAL_EXPOSED_NOT_OOS"
        or any(e[k] is not False for k in ("out_of_sample","broker_fills_verified",
                                           "approved_for_live","profitability_verified"))):
        raise ValueError("No self-authored live/OOS/profitability certification")
    if type(e["year"]) is not int or not 2010<=e["year"]<=2026 or type(e["monthly"]) is not list or len(e["monthly"])!=12:
        raise ValueError("Year must contain 12 historical months")
    months=e["monthly"]
    for index,m in enumerate(months,1):
        if (type(m) is not dict or set(m)!={"period","net_usd","trades","all_in_cost_usd"}
            or m["period"]!=f'{e["year"]}-{index:02d}'
            or type(m["trades"]) is not int or m["trades"]<0
            or _money(m["all_in_cost_usd"])!=Decimal("0.40")*m["trades"]):
            raise ValueError("Period/fee/month evidence mismatch")
        _money(m["net_usd"])
    positive=sum(_money(m["net_usd"])>0 for m in months)
    status=("HISTORICAL_ONLY_NOT_APPROVED" if positive==12
            else "REJECTED_HISTORICAL_MONTHLY_OBJECTIVE")
    if (e["disposition"]!=status or e["positive_months"]!=positive
        or e["months_observed"]!=12
        or e["trades"]!=sum(m["trades"] for m in months)
        or _money(e["total_net_usd"])!=sum((_money(m["net_usd"]) for m in months),Decimal(0))):
        raise ValueError("Monthly evidence contradicts disposition")

def evidence_from_audited_year(plan,output,*,experiment_id,source_manifest_id):
    att=verify_frozen_batch_evidence(plan,output,expected_experiment_id=experiment_id,
                                     source_manifest_id=source_manifest_id)
    jobs,plan_sha=batch.expand(plan,limit=1)
    spec=jobs[0]["spec"]
    year=int(spec["start"][:4])
    if spec["start"]!=f"{year}-01-01" or spec["end"]!=f"{year}-12-31":
        raise ValueError("Expected one complete historical calendar year")
    directory=Path(output)/"runs"/att.frozen_job_id
    report=directory/"monthly.csv"
    with report.open("r",newline="",encoding="utf-8") as f:
        rdr=csv.DictReader(f)
        if rdr.fieldnames is None or len(rdr.fieldnames)!=len(set(rdr.fieldnames)):
            raise ValueError("Ambiguous historical month CSV")
        original=list(rdr)
    if len(original)!=12:
        raise ValueError("Require 12 months of original evidence")
    monthly=[]
    for index,m in enumerate(original,1):
        if (m.get("period")!=f"{year}-{index:02d}" or
            m.get("month_has_observed_m1")!="True" or
            not re.fullmatch(r"\d{1,9}",m.get("trades",""))):
            raise ValueError("Missing/unobserved or noncanonical source month")
        t=int(m["trades"]); net=_money(m["net_pnl"]);cost=_money(m["total_cost"])
        if cost!=Decimal("0.40")*t:
            raise ValueError("Wrong fixed market research cost")
        monthly.append({"period":m["period"],"net_usd":str(net),
                        "trades":t,"all_in_cost_usd":str(cost)})
    if sum(m["trades"] for m in monthly)!=att.trades or att.months_observed!=12:
        raise ValueError("Annual trade audit does not reconcile")
    if batch.file_sha(report)!=batch.audit_run(
            directory,spec,plan["source_sha256"],plan["engine_commit"])["monthly_sha256"]:
        raise ValueError("Annual month ledger mutated during capture")
    positive=sum(_money(m["net_usd"])>0 for m in monthly)
    strategy=strategy_spec(plan)
    result={"schema":SCHEMA,"spec":strategy,"spec_sha256":_hash(strategy),
            "year":year,"monthly":monthly,"trades":att.trades,"months_observed":12,
            "positive_months":positive,"total_net_usd":str(sum((_money(m["net_usd"]) for m in monthly),Decimal(0))),
            "exposure":"HISTORICAL_EXPOSED_NOT_OOS",
            "disposition":"HISTORICAL_ONLY_NOT_APPROVED" if positive==12 else "REJECTED_HISTORICAL_MONTHLY_OBJECTIVE",
            "original_source_sha256":att.original_source_sha256,
            "source_manifest_id":source_manifest_id,"engine_commit":att.engine_commit,
            "plan_sha256":plan_sha,"batch_manifest_sha256":att.manifest_sha256,
            "experiment_id":att.experiment_id,"out_of_sample":False,
            "broker_fills_verified":False,"profitability_verified":False,"approved_for_live":False}
    _verify_evidence(result)
    return result

class ScientificDecisionJournal:
    """Local chained evidence: catches ordinary tampering, not privileged re-rooting."""
    def __init__(self,path):
        if os.name!="posix": raise ValueError("POSIX owner-only local evidence required")
        self.path=Path(path)
        if not self.path.is_absolute() or self.path.is_symlink() or not self.path.parent.is_dir():
            raise ValueError("Expected private absolute database")
        info=self.path.parent.stat()
        if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise ValueError("Private research parent directory must be 0700")
        if self.path.exists():
            info=self.path.stat()
            if not self.path.is_file() or info.st_nlink!=1 or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
                raise ValueError("Private rejection journal must be 0600")
        else:
            fd=os.open(self.path,os.O_EXCL|os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS evidence(seq INTEGER PRIMARY KEY AUTOINCREMENT,"
                       " evidence_id TEXT NOT NULL UNIQUE,strategy_id TEXT NOT NULL,"
                       " json TEXT NOT NULL,prev_hash TEXT NOT NULL,event_hash TEXT NOT NULL)")
    def _connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        return db
    def _verify(self,db):
        previous="0"*64
        rows=db.execute("SELECT seq,evidence_id,strategy_id,json,prev_hash,event_hash FROM evidence ORDER BY seq").fetchall()
        for index,(seq,evid,ident,raw,prev,chain) in enumerate(rows,1):
            if seq!=index or prev!=previous:raise ValueError("Missing/forked journal event")
            try:r=json.loads(raw)
            except json.JSONDecodeError as exc:raise ValueError("Corrupted research event") from exc
            _verify_evidence(r)
            if (evid!=_hash(r) or ident!=r["spec_sha256"]
                or chain!=_hash({"previous":prev,"evidence_id":evid,"seq":seq})):
                raise ValueError("Scientific chain modified")
            previous=chain
        return previous,len(rows)
    def append(self,record):
        # WARNING: only privileged operator code should call with audited evidence.
        _verify_evidence(record);digest=_hash(record)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            head,n=self._verify(db)
            if db.execute("SELECT 1 FROM evidence WHERE evidence_id=?",(digest,)).fetchone():
                return {"recorded":False,"evidence_id":digest,"chain_head":head}
            next_id=n+1
            chain=_hash({"previous":head,"evidence_id":digest,"seq":next_id})
            db.execute("INSERT INTO evidence(evidence_id,strategy_id,json,prev_hash,event_hash) VALUES(?,?,?,?,?)",
                       (digest,record["spec_sha256"],_canonical(record),head,chain))
        return {"recorded":True,"evidence_id":digest,"chain_head":chain}
    def candidate_gate(self,plan):
        spec=strategy_spec(plan);fingerprint=_hash(spec)
        with self._connect() as db:
            head,n=self._verify(db)
            rows=db.execute("SELECT json FROM evidence").fetchall()
        historic=[json.loads(row[0]) for row in rows]
        exact=[x for x in historic if x["spec_sha256"]==fingerprint]
        family=[x for x in historic if x["spec"]["strategy"]==spec["strategy"]]
        rejected=any(x["disposition"]=="REJECTED_HISTORICAL_MONTHLY_OBJECTIVE" for x in exact)
        decision=("BLOCK_IDENTICAL_PREVIOUSLY_REJECTED" if rejected
                  else "HISTORICAL_RESEARCH_ONLY_ALREADY_TESTED" if exact
                  else "HISTORICAL_EXPOSED_FAMILY_VARIANT" if family
                  else "UNREGISTERED_HYPOTHESIS_RESEARCH_ONLY")
        return {"schema":"NRFX_CANDIDATE_SCIENTIFIC_GATE_V1",
                "decision":decision,"strategy_spec_sha256":fingerprint,
                "same_spec_evidence_count":len(exact),"family_evidence_count":len(family),
                "history_chain_head":head,"independent_oos":False,
                "profitability_verified":False,"approved_for_live":False,
                "autonomous_promotion":False}
    def audit(self):
        with self._connect() as db:head,n=self._verify(db)
        return {"evidence_count":n,"chain_head":head,
                "externally_anchored":False,"rejection_journal_audited":True,
                "independent_oos":False,"broker_fill_parity":False}
