"""B12 — one-shot, future-only prospective Gold study and attempt-count ledger.

This is a local operator protocol for RESEARCH, never a trading approval,
verified external pre-registration or permission to access future prices.
Only one candidate may enter one untouched future period. Historical
exploration remains a separate, exposed-data workflow.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,os,re,sqlite3,stat
from pathlib import Path
from .scientific_rejection_registry import strategy_spec

SCHEMA="NRFX_PROSPECTIVE_HOLDOUT_GOVERNANCE_V1"
SHA64=re.compile(r"[a-f0-9]{64}\Z")
SHA40=re.compile(r"[a-f0-9]{40}\Z")
EMBARGO=timedelta(hours=48)

def _iso(raw):
    if type(raw) is not str or not re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)\Z",raw):
        raise ValueError("Explicit UTC research timestamp required")
    try:dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:raise ValueError("Malformed UTC time") from exc
    if dt.utcoffset()!=timedelta(0):raise ValueError("Non-UTC source exposure")
    return dt.astimezone(timezone.utc)

def _clock(value):
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset()!=timedelta(0):
        raise ValueError("Operator study clock must be explicit UTC")
    return value.astimezone(timezone.utc)

def _canon(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=True)

def _sha(value):
    return sha256(_canon(value).encode("ascii")).hexdigest()

def validate_protocol(protocol,*,now):
    keys={"schema","asset","timeframe","dataset_sha256","engine_commit",
          "strategy_spec_sha256","registered_at_utc","historical_exposed_through_utc",
          "train_end_utc","holdout_start_utc","holdout_end_exclusive_utc",
          "trial_budget","fee_usd_per_oz_all_in","objective"}
    if type(protocol) is not dict or set(protocol)!=keys or protocol["schema"]!=SCHEMA:
        raise ValueError("Unknown prospective protocol fields")
    for k,p in (("dataset_sha256",SHA64),("strategy_spec_sha256",SHA64),("engine_commit",SHA40)):
        if type(protocol[k]) is not str or not p.fullmatch(protocol[k]):
            raise ValueError("Immutable experiment/code/source fingerprints needed")
    if (protocol["asset"]!="XAUUSD" or protocol["timeframe"]!="M1"
        or protocol["objective"]!="ALL_COMPLETE_MONTHS_NET_POSITIVE_AFTER_COST"
        or type(protocol["fee_usd_per_oz_all_in"]) is not float
        or protocol["fee_usd_per_oz_all_in"]!=0.4
        or type(protocol["trial_budget"]) is not int or protocol["trial_budget"]!=1):
        raise ValueError("Only one Gold M1 candidate with fixed cost/objective is allowed")
    stamp=_iso(protocol["registered_at_utc"])
    exposed=_iso(protocol["historical_exposed_through_utc"])
    train=_iso(protocol["train_end_utc"])
    start=_iso(protocol["holdout_start_utc"])
    end=_iso(protocol["holdout_end_exclusive_utc"])
    clock=_clock(now)
    if stamp>clock or clock-stamp>timedelta(minutes=5):
        raise ValueError("Prospective record has no fresh verified local clock")
    if train>exposed or exposed>stamp:
        raise ValueError("Training/exposure exceeds declared pre-registration")
    if start<stamp+EMBARGO or end<=start:
        raise ValueError("Prospective window is already observed or lacks 48h embargo")
    for value in (start,end):
        if (value.day!=1 or value.hour or value.minute or
            value.second or value.microsecond):
            raise ValueError("Prospective window must contain whole UTC calendar months")
    return _sha(protocol)

class ProspectiveTrialJournal:
    """Single-protocol owner-only SQLite. SHA chain is NOT external attestation."""
    def __init__(self,path):
        if os.name!="posix":
            raise ValueError("Owner-only POSIX study controls required")
        self.path=Path(path)
        if not self.path.is_absolute() or self.path.is_symlink() or not self.path.parent.is_dir():
            raise ValueError("Private absolute protocol journal required")
        parent=self.path.parent.stat()
        if parent.st_uid!=os.getuid() or stat.S_IMODE(parent.st_mode)&0o077:
            raise ValueError("Prospective protocol directory must be 0700")
        if self.path.exists():
            q=self.path.stat()
            if (not self.path.is_file() or q.st_nlink!=1 or q.st_uid!=os.getuid()
                    or stat.S_IMODE(q.st_mode)&0o077):
                raise ValueError("Prospective database must be 0600")
        else:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS protocol("
                       "id INTEGER PRIMARY KEY CHECK (id=1),digest TEXT NOT NULL,json TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS trials("
                       "seq INTEGER PRIMARY KEY,spec_sha TEXT NOT NULL UNIQUE,"
                       "prev_sha TEXT NOT NULL,chain_sha TEXT NOT NULL)")
    def _db(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        return db
    @staticmethod
    def _verify(db):
        raw=db.execute("SELECT id,digest,json FROM protocol").fetchall()
        if len(raw)>1:raise ValueError("Multiple frozen prospective protocols")
        protocol=None
        if raw:
            rid,hash_,content=raw[0]
            try:protocol=json.loads(content)
            except json.JSONDecodeError as exc:raise ValueError("Corrupt protocol record") from exc
            if rid!=1 or _sha(protocol)!=hash_:
                raise ValueError("Frozen protocol hash was modified")
        previous="0"*64
        count=0
        for seq,spec,prev,chain in db.execute(
                "SELECT seq,spec_sha,prev_sha,chain_sha FROM trials ORDER BY seq"):
            count+=1
            if (seq!=count or type(spec) is not str or not SHA64.fullmatch(spec)
                or previous!=prev or chain!=_sha({"seq":seq,"spec_sha":spec,"previous":prev})):
                raise ValueError("Trial attempt history was modified")
            previous=chain
        if (protocol is None and count) or (protocol is not None and count>protocol["trial_budget"]):
            raise ValueError("Orphan or excessive research trials")
        return protocol,count,previous
    def freeze(self,protocol,*,now):
        digest=validate_protocol(protocol,now=now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior,count,_=self._verify(db)
            if prior is not None:
                if _sha(prior)!=digest:raise ValueError("Cannot overwrite frozen prospective protocol")
                return {"registered":False,"protocol_sha256":digest,"trial_count":count}
            db.execute("INSERT INTO protocol VALUES (1,?,?)",(digest,_canon(protocol)))
        return {"registered":True,"protocol_sha256":digest,"trial_count":0}
    def declare_trial(self,plan,*,now):
        spec=strategy_spec(plan)
        digest=_sha(spec)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            protocol,count,head=self._verify(db)
            if protocol is None:raise ValueError("No frozen prospective protocol")
            if _clock(now)>=_iso(protocol["holdout_start_utc"]):
                raise ValueError("No post-hoc strategy change once future begins")
            if (digest!=protocol["strategy_spec_sha256"]
                or plan["source_sha256"]!=protocol["dataset_sha256"]
                or plan["engine_commit"]!=protocol["engine_commit"]):
                raise ValueError("Candidate differs from frozen strategy/source/code")
            if db.execute("SELECT 1 FROM trials WHERE spec_sha=?",(digest,)).fetchone():
                return {"accepted":False,"duplicate":True,"trials_used":count,"trial_budget":1}
            if count>=1:raise ValueError("Untouched future holdout attempt exhausted")
            new=count+1
            chain=_sha({"seq":new,"spec_sha":digest,"previous":head})
            db.execute("INSERT INTO trials VALUES (?,?,?,?)",(new,digest,head,chain))
        return {"accepted":True,"duplicate":False,"trials_used":new,"trial_budget":1}
    def status(self,*,now):
        with self._db() as db:protocol,count,head=self._verify(db)
        if protocol is None:
            return {"schema":SCHEMA,"state":"NOT_REGISTERED","independent_oos":False,
                    "profitability_verified":False,"approved_for_live":False}
        return {"schema":SCHEMA,
                "state":("FUTURE_NOT_OBSERVED" if _clock(now)<_iso(protocol["holdout_end_exclusive_utc"])
                         else "MANUAL_INDEPENDENT_AUDIT_REQUIRED"),
                "protocol_sha256":_sha(protocol),"trials_used":count,"trial_budget":1,
                "locally_chain_audited":True,"externally_preregistered":False,
                "independent_oos":False,"profitability_verified":False,"approved_for_live":False}
