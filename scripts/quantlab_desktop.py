"""No Risk FX Quant Lab: loopback-only research control console.

Runs ONLY frozen, source-pinned historical batches through the existing
canonical auditable research_batch_orchestrator. Does not send orders or data.
Local operator service (not authenticated multiuser hosting).
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

try:
    from scripts import research_batch_orchestrator as lab
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    import research_batch_orchestrator as lab

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
FAMILY = {"ema", "donchian", "fvg", "bos-fib", "qs01", "m1-sweep", "tf-sweep"}
JOB_ID = re.compile(r"[0-9a-f]{64}\Z")
CAP = 5000
MAX_BODY = 32768
MONTHLY_FIELDS = {"period", "net_pnl", "trades", "total_cost", "observed_m1_samples",
                  "uncertain_gap_trades", "synthetic_end_of_data_trades"}


def private_dir(path: Path) -> Path:
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Workspace contains a symlinked path component")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise ValueError("Workspace must be a directory")
    if os.name == "posix":
        info = path.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Workspace must be owner-only (0700)")
    return path


def put_once(path: Path, obj: dict) -> None:
    payload = lab.canonical(obj) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def require_id(value: str) -> str:
    if type(value) is not str or not JOB_ID.fullmatch(value):
        raise ValueError("Invalid research ID")
    return value


def exact_year(value: object) -> int:
    if type(value) is not int or not 2010 <= value < date.today().year:
        raise ValueError("Full completed historical calendar year required")
    return value


def strict_dict(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("Missing or unsupported request fields")
    return value



def decode_request_json(raw: bytes) -> object:
    """Reject duplicate keys and nonfinite JSON in local research requests."""
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate research request JSON key")
            result[key] = value
        return result

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite research request JSON number")
        return number

    def reject_constant(value):
        raise ValueError("Nonfinite research request JSON constant")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                          parse_float=finite_float, parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed research request JSON") from exc


class ResearchHub:
    def __init__(self, workspace: Path):
        self.root = private_dir(workspace)
        self.plans = private_dir(self.root / "plans")
        self.runs = private_dir(self.root / "runs")
        self._lock = threading.Lock()
        self._active: str | None = None
        self._latest_error: dict[str, str] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._run_mode = "IDLE"
        self._budget_total = 0
        self._budget_completed = 0

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    def configured_source(self) -> Path | None:
        if not self.config_path.exists():
            return None
        config = lab.read_strict_json(self.config_path)
        if type(config) is not dict or set(config) != {"source_path", "source_sha256"}:
            raise ValueError("Unsafe Quant Lab source configuration")
        if config["source_sha256"] != SOURCE_SHA:
            raise ValueError("Source config changed")
        return Path(config["source_path"])

    def configure(self, source_path: str) -> dict:
        if type(source_path) is not str:
            raise ValueError("Source must be a local absolute file path")
        source = Path(source_path).absolute()
        if (not Path(source_path).is_absolute() or source.is_symlink()
                or not source.is_file() or source.suffix.lower() != ".zip"):
            raise ValueError("Choose the original private Gold .zip file")
        if lab.file_sha(source) != SOURCE_SHA:
            raise ValueError("Source fingerprint does not match authorized original Gold archive")
        if self.config_path.is_symlink():
            raise ValueError("Unsafe source config")
        config = {"source_path": str(source), "source_sha256": SOURCE_SHA}
        # A different existing config is not silently overwritten: operator
        # must deliberately reset it outside the app after stopping research.
        if self.config_path.exists():
            if lab.read_strict_json(self.config_path) != config:
                raise ValueError("A different source is configured; stop app before changing")
        else:
            put_once(self.config_path, config)
        return {"configured": True, "source_name": source.name, "sha256": SOURCE_SHA}

    def status(self) -> dict:
        source = self.configured_source()
        try:
            revision = lab.checkout_commit()
            engine_ok = True
        except ValueError:
            revision, engine_ok = None, False
        return {
            "product": "NO RISK FX QUANT LAB", "mode": "LOCAL_RESEARCH_ONLY",
            "source_configured": source is not None,
            "source_name": source.name if source else None,
            "source_sha256": SOURCE_SHA if source else None,
            "engine_revision": revision,
            "engine_verified_clean_checkout": engine_ok,
            "active_run": self._active,
            "run_mode": self._run_mode,
            "stop_requested": self._stop.is_set() if self._active else False,
            "operator_budget": self._budget_total,
            "operator_budget_completed": self._budget_completed,
            "historical_exposed_not_oos": True,
            "broker_orders_enabled": False,
            "all_in_cost_per_ounce": .40,
            "platform_ready": source is not None and engine_ok,
        }

    def _build(self, user: dict) -> tuple[dict, list]:
        strict_dict(user, {"year", "strategy", "timeframe", "execution", "grid"})
        year = exact_year(user["year"])
        strategy, tf, execution = user["strategy"], user["timeframe"], user["execution"]
        if type(strategy) is not str or strategy not in FAMILY:
            raise ValueError("Unknown research strategy")
        if type(tf) is not str or type(execution) is not str:
            raise ValueError("Strategy timeframe and execution must be text")
        axes = user["grid"]
        if type(axes) is not dict or not axes or len(axes) > 12:
            raise ValueError("Grid needs 1..12 parameter axes")
        if any(type(k) is not str or type(v) is not list or not 1 <= len(v) <= 30
               for k, v in axes.items()):
            raise ValueError("Invalid grid axes")
        if any(type(v) not in (int, float) for arr in axes.values() for v in arr):
            raise ValueError("Parameter values must be numeric, not text/boolean")
        source = self.configured_source()
        if source is None:
            raise ValueError("Configure and fingerprint the original private Gold archive first")
        revision = lab.checkout_commit()  # must be exact clean Git checkout
        plan = {
            "schema": lab.SCHEMA, "dataset": str(source),
            "source_sha256": SOURCE_SHA, "engine_commit": revision,
            "exposure_context": "historical_exposed", "jobs": [],
            "grids": [{"id_prefix": f"lab-{strategy.replace('_','-')}-{year}",
                       "strategy": strategy, "timeframe": tf, "execution": execution,
                       "start": f"{year}-01-01", "end": f"{year}-12-31", "grid": axes}],
        }
        jobs, plan_sha = lab.expand(plan, limit=CAP)
        return plan, jobs

    def preview(self, user: dict) -> dict:
        plan, jobs = self._build(user)
        return {"defined_jobs": len(jobs), "plan_id": lab.expand(plan, limit=CAP)[1],
                "first_experiment": jobs[0]["spec"], "status": "DEFINED_ONLY_NO_BACKTEST"}

    def freeze(self, user: dict) -> dict:
        plan, jobs = self._build(user)
        digest = lab.expand(plan, limit=CAP)[1]
        path = self.plans / (digest + ".json")
        if not path.exists():
            put_once(path, plan)
        elif lab.read_strict_json(path) != plan:
            raise ValueError("Frozen research plan ID collision or tampering")
        return {"plan_id": digest, "defined_jobs": len(jobs),
                "status": "FROZEN_PLAN_NOT_EXECUTED"}

    def freeze_research_universe(self, years: list[int]) -> dict:
        """Freeze multi-year, multi-family research without executing a job.

        Explicitly differentiates experiment definitions from tested systems.
        The underlying registered factory must verify supported parameters.
        """
        if (type(years) is not list or not 1 <= len(years) <= 14
                or any(type(y) is not int or not 2012 <= y <= 2025
                       or y >= date.today().year for y in years)
                or years != sorted(set(years))):
            raise ValueError("Require 1..14 ascending distinct completed 2012–2025 years")
        from scripts import generate_quant_research_grid as factory
        source = self.configured_source()
        if source is None:
            raise ValueError("Configure verified original Gold ZIP first")
        revision = lab.checkout_commit()
        plan = factory.make_plan(source, years=tuple(years),
                                 source_sha256=SOURCE_SHA, engine_commit=revision)
        jobs, digest = lab.expand(plan, limit=CAP)
        path = self.plans / (digest + ".json")
        if not path.exists():
            put_once(path, plan)
        elif lab.read_strict_json(path) != plan:
            raise ValueError("Research universe was modified")
        return {"plan_id": digest, "defined_jobs": len(jobs),
                "years": years, "status": "FROZEN_MULTIYEAR_NOT_EXECUTED"}

    def cross_year_comparison(self, plan_id: str) -> dict:
        """Audit annual runs before descriptive, training-only comparison.

        Never certify clean OOS; incomplete factory gets no candidate rank.
        """
        if self._active is not None:
            raise ValueError("Cross-year audit requires no active batch")
        plan = self._plan(plan_id)
        years = {int(g["start"][:4]) for g in plan["grids"]}
        required = set(range(2012, 2021))
        if not required.issubset(years):
            raise ValueError("Research universe requires all 2012–2020 annual windows")
        from scripts import research_cross_year_candidate_screen as cross
        output = self._run_folder(plan_id)
        if not output.exists():
            raise ValueError("No annual batch evidence exists")
        return cross.run_file(self.plans / (plan_id + ".json"), output,
                              train_years=tuple(range(2012, 2017)),
                              review_years=tuple(range(2017, 2021)))

    def _plan(self, digest: str) -> dict:
        path = self.plans / (require_id(digest) + ".json")
        plan = lab.read_strict_json(path)
        jobs, computed = lab.expand(plan, limit=CAP)
        if computed != digest:
            raise ValueError("Research plan content changed")
        return plan

    def list_plans(self) -> list[dict]:
        result = []
        for path in sorted(self.plans.glob("*.json")):
            plan = self._plan(path.stem)
            jobs, _ = lab.expand(plan, limit=CAP)
            result.append({"id": path.stem, "defined_jobs": len(jobs),
                           "strategy": plan["grids"][0]["strategy"],
                           "timeframe": plan["grids"][0]["timeframe"],
                           "year": (plan["grids"][0]["start"][:4]
                                    if len(plan["grids"]) == 1 else
                                    plan["grids"][0]["start"][:4] + "–" + plan["grids"][-1]["start"][:4])})
        return result

    def _run_folder(self, digest: str) -> Path:
        return self.runs / require_id(digest)

    def list_runs(self) -> list[dict]:
        result = []
        for path in sorted(self.runs.iterdir()):
            if path.is_symlink() or not path.is_dir() or not JOB_ID.fullmatch(path.name):
                raise ValueError("Unexpected research run entry")
            result.append(self.run_summary(path.name))
        return result

    def run_summary(self, plan_id: str) -> dict:
        plan = self._plan(plan_id)
        jobs, _ = lab.expand(plan, limit=CAP)
        path = self._run_folder(plan_id)
        manifest_path = path / "batch_manifest.json"
        stored = lab.read_strict_json(manifest_path) if manifest_path.exists() else None
        rows = stored.get("results", {}) if type(stored) is dict else {}
        if stored is not None and (stored.get("plan_sha256") != plan_id
                                   or stored.get("source_sha256") != SOURCE_SHA
                                   or stored.get("engine_commit") != plan["engine_commit"]):
            raise ValueError("Run manifest does not match frozen plan")
        accepted = sum(type(x) is dict and x.get("status") == lab.PASSED
                       for x in rows.values())
        return {"plan_id": plan_id, "defined_jobs": len(jobs),
                "remaining_jobs": len(jobs) - accepted,
                "completion_pct": round(100.0 * accepted / len(jobs), 2),
                "recorded_jobs_unverified": len(rows),
                "recorded_reconciled_unverified": sum(
                    type(x) is dict and x.get("status") == lab.PASSED for x in rows.values()),
                "active": self._active == plan_id,
                "last_error": self._latest_error.get(plan_id),
                "evidence_status": "RECORDED_NOT_REAUDITED_FROM_BROWSER"}

    def run_results(self, plan_id: str, *, offset: int = 0, limit: int = 50) -> dict:
        if (type(offset) is not int or offset < 0 or type(limit) is not int
                or not 1 <= limit <= 200):
            raise ValueError("Invalid pagination")
        summary = self.run_summary(plan_id)
        manifest_file = self._run_folder(plan_id) / "batch_manifest.json"
        if not manifest_file.exists():
            return {**summary, "jobs": []}
        manifest = lab.read_strict_json(manifest_file)
        plan = self._plan(plan_id)
        known = {job["id"] for job in lab.expand(plan, limit=CAP)[0]}
        if not set(manifest["results"]).issubset(known):
            raise ValueError("Unexpected job ID in run evidence")
        results = []
        all_records = sorted(manifest["results"].items())
        for ident, record in all_records[offset:offset + limit]:
            if type(record) is not dict:
                raise ValueError("Unsafe run record")
            results.append({"id": ident, "status": record.get("status"),
                            "trades": record.get("trades"),
                            "net_pnl": record.get("net_pnl"),
                            "positive_months": record.get("positive_months"),
                            "months_observed": record.get("months_observed")})
        return {**summary, "jobs": results, "page_offset": offset,
                "page_limit": limit, "recorded_total": len(all_records),
                "has_more": offset + limit < len(all_records)}

    def verify_run(self, plan_id: str) -> dict:
        if self._active is not None:
            raise ValueError("Cannot audit while any research execution is active")
        plan = self._plan(plan_id)
        if lab.checkout_commit() != plan["engine_commit"]:
            raise ValueError("Pinned engine checkout mismatch")
        source = Path(plan["dataset"])
        if source.is_symlink() or not source.is_file() or lab.file_sha(source) != SOURCE_SHA:
            raise ValueError("Original source changed")
        folder = self._run_folder(plan_id)
        with lab.exclusive_batch_lock(folder):
            manifest = lab.read_strict_json(folder / "batch_manifest.json")
            if manifest["plan_sha256"] != plan_id or manifest["source_sha256"] != SOURCE_SHA:
                raise ValueError("Untrusted frozen manifest")
            jobs = {job["id"]: job["spec"] for job in lab.expand(plan, limit=CAP)[0]}
            if not set(manifest["results"]).issubset(jobs):
                raise ValueError("Unrecognized results")
            for ident, record in manifest["results"].items():
                if record.get("status") != lab.PASSED:
                    raise ValueError("Failed or incomplete job; no clean certification")
                if lab.audit_run(folder / "runs" / ident, jobs[ident], SOURCE_SHA,
                                 plan["engine_commit"]) != record:
                    raise ValueError("Tampered run ledger")
            return {"status": "RE_AUDITED_HISTORICAL_EXPOSED_NOT_OOS",
                    "verified_jobs": len(manifest["results"]),
                    "defined_jobs": len(jobs),
                    "complete": len(manifest["results"]) == len(jobs),
                    "broker_tick_fills_verified": False}

    def monthly(self, plan_id: str, job_id: str) -> list[dict]:
        plan = self._plan(plan_id)
        jobs = {job["id"] for job in lab.expand(plan, limit=CAP)[0]}
        if job_id not in jobs or not lab.JOB_ID.fullmatch(job_id):
            raise ValueError("Unknown research job")
        manifest = lab.read_strict_json(self._run_folder(plan_id) / "batch_manifest.json")
        if job_id not in manifest["results"] or manifest["results"][job_id].get("status") != lab.PASSED:
            raise ValueError("No reconciled ledger for selected research job")
        file = self._run_folder(plan_id) / "runs" / job_id / "monthly.csv"
        if file.is_symlink() or not file.is_file():
            raise ValueError("Unsafe monthly ledger")
        if lab.file_sha(file) != manifest["results"][job_id]["monthly_sha256"]:
            raise ValueError("Monthly ledger fingerprint changed")
        rows = lab.read_ledger_csv(file)
        if not all(MONTHLY_FIELDS.issubset(row) for row in rows):
            raise ValueError("Unexpected monthly evidence fields")
        return [{"period": row["period"], "net_pnl": lab.finite(row["net_pnl"]),
                 "trades": lab.count(row["trades"]), "total_cost": lab.finite(row["total_cost"]),
                 "uncertain_gap_trades": lab.count(row["uncertain_gap_trades"]),
                 "synthetic_end_of_data_trades": lab.count(row["synthetic_end_of_data_trades"])}
                for row in rows]

    def weekly(self, plan_id: str, job_id: str) -> list[dict]:
        """Read SHA-checked recorded weekly ledger, not broker-certified fills."""
        plan = self._plan(plan_id)
        jobs = {j["id"] for j in lab.expand(plan, limit=CAP)[0]}
        if job_id not in jobs or not lab.JOB_ID.fullmatch(job_id):
            raise ValueError("Unknown research job")
        manifest = lab.read_strict_json(self._run_folder(plan_id) / "batch_manifest.json")
        if (manifest.get("plan_sha256") != plan_id
                or manifest.get("source_sha256") != SOURCE_SHA
                or manifest.get("engine_commit") != plan["engine_commit"]):
            raise ValueError("Weekly evidence provenance mismatch")
        record = manifest["results"].get(job_id)
        if type(record) is not dict or record.get("status") != lab.PASSED:
            raise ValueError("No reconciled weekly ledger")
        file = self._run_folder(plan_id) / "runs" / job_id / "weekly.csv"
        if file.is_symlink() or not file.is_file() or lab.file_sha(file) != record["weekly_sha256"]:
            raise ValueError("Weekly evidence fingerprint mismatch")
        return [{"period": row["period"], "net_pnl": lab.finite(row["net_pnl"]),
                 "trades": lab.count(row["trades"]),
                 "total_cost": lab.finite(row["total_cost"])}
                for row in lab.read_ledger_csv(file)]

    def evidence_bytes(self, plan_id: str, job_id: str,
                       filename: str) -> tuple[bytes, str]:
        """Exactly four SHA-locked exports; private source ZIP stays private."""
        allowed = {"trades.csv": "trades_sha256", "weekly.csv": "weekly_sha256",
                   "monthly.csv": "monthly_sha256", "summary.json": "summary_sha256"}
        if type(filename) is not str or filename not in allowed:
            raise ValueError("Unsupported private evidence export")
        plan = self._plan(plan_id)
        jobs = {j["id"] for j in lab.expand(plan, limit=CAP)[0]}
        if job_id not in jobs or not lab.JOB_ID.fullmatch(job_id):
            raise ValueError("Unknown research job")
        manifest = lab.read_strict_json(self._run_folder(plan_id) / "batch_manifest.json")
        if (manifest.get("plan_sha256") != plan_id
                or manifest.get("source_sha256") != SOURCE_SHA
                or manifest.get("engine_commit") != plan["engine_commit"]):
            raise ValueError("Evidence source or code changed")
        record = manifest["results"].get(job_id)
        if type(record) is not dict or record.get("status") != lab.PASSED:
            raise ValueError("Research result requires reconciliation")
        target = self._run_folder(plan_id) / "runs" / job_id / filename
        if target.is_symlink() or not target.is_file():
            raise ValueError("Missing or unsafe evidence export")
        content = target.read_bytes()
        import hashlib
        if len(content) > 20_000_000 or hashlib.sha256(content).hexdigest() != record[allowed[filename]]:
            raise ValueError("Evidence file integrity check failed")
        return content, ("application/json; charset=utf-8"
                         if filename.endswith(".json") else "text/csv; charset=utf-8")

    def start(self, plan_id: str, budget: int, *, recover: bool = False) -> dict:
        if type(budget) is not int or not 1 <= budget <= 20 or type(recover) is not bool:
            raise ValueError("Interactive per-click budget 1..20; recovery must be deliberate")
        plan = self._plan(plan_id)
        if lab.checkout_commit() != plan["engine_commit"]:
            raise ValueError("Pinned clean Git revision has changed")
        source = Path(plan["dataset"])
        if (source.is_symlink() or not source.is_file()
                or lab.file_sha(source) != SOURCE_SHA):
            raise ValueError("Original private Gold ZIP fingerprint mismatch")
        with self._lock:
            if self._active is not None:
                raise ValueError("Another research run is active")
            output = private_dir(self._run_folder(plan_id))
            self._active = plan_id
            self._stop.clear()
            self._run_mode = "SINGLE_BATCH"
            self._budget_total = budget
            self._budget_completed = 0
            self._latest_error.pop(plan_id, None)
            thread = threading.Thread(target=self._execute, args=(plan_id, plan, output, budget, recover),
                                      name="quantlab-research-worker", daemon=True)
            self._thread = thread
            thread.start()
        return {"status": "STARTED_LOCAL_RESEARCH", "plan_id": plan_id,
                "requested_job_budget": budget}

    @staticmethod
    def _verified_runner_count(report, budget: int) -> int:
        """Fail closed on malformed runner acknowledgements, never infer success.

        This is a progress-control check, NOT evidence that any result ledger
        has passed independent source/fee/market-data reconciliation.
        """
        if type(report) is not dict:
            raise ValueError("Research runner returned a non-object result")
        count = report.get("executed_this_invocation")
        if type(count) is not int or not 0 <= count <= budget:
            raise ValueError("Research runner returned invalid executed_this_invocation")
        return count

    def _execute(self, plan_id, plan, output, budget, recover):
        try:
            result = lab.run_plan(plan, output, max_jobs=budget, recover_verified_orphans=recover)
            completed = self._verified_runner_count(result, budget)
            with self._lock:
                self._budget_completed = completed
        except Exception as exc:
            with self._lock:
                self._latest_error[plan_id] = type(exc).__name__ + ": " + str(exc)[:300]
        finally:
            with self._lock:
                self._active = None
                self._run_mode = "IDLE"

    def start_autopilot(self, plan_id: str, batch_size: int,
                        total_budget: int, *, recover: bool = False) -> dict:
        """Bounded unattended local batches while app remains running."""
        if (type(batch_size) is not int or not 1 <= batch_size <= 100
                or type(total_budget) is not int or not 1 <= total_budget <= CAP
                or type(recover) is not bool):
            raise ValueError("Batch 1..100 and total budget 1..5000 required")
        plan = self._plan(plan_id)
        if lab.checkout_commit() != plan["engine_commit"]:
            raise ValueError("Pinned Git checkout changed")
        source = Path(plan["dataset"])
        if source.is_symlink() or not source.is_file() or lab.file_sha(source) != SOURCE_SHA:
            raise ValueError("Original Gold source fingerprint mismatch")
        with self._lock:
            if self._active is not None:
                raise ValueError("Another research run is active")
            output = private_dir(self._run_folder(plan_id))
            self._active = plan_id
            self._stop.clear()
            self._run_mode = "AUTOPILOT_BOUNDED"
            self._budget_total = total_budget
            self._budget_completed = 0
            self._latest_error.pop(plan_id, None)
            self._thread = threading.Thread(
                target=self._autopilot_worker,
                args=(plan_id, plan, output, batch_size, total_budget, recover),
                name="nrfx-autopilot-worker", daemon=True,
            )
            self._thread.start()
        return {"status": "AUTOPILOT_STARTED_LOCAL", "plan_id": plan_id,
                "batch_size": batch_size, "total_budget": total_budget,
                "stop_behavior": "AFTER_CURRENT_VERIFIED_BATCH"}

    def stop_autopilot(self, plan_id: str) -> dict:
        require_id(plan_id)
        with self._lock:
            if self._active != plan_id or self._run_mode != "AUTOPILOT_BOUNDED":
                raise ValueError("No matching autopilot is running")
            self._stop.set()
        return {"status": "STOP_REQUESTED_AFTER_CURRENT_BATCH", "plan_id": plan_id}

    def _autopilot_worker(self, plan_id, plan, output, batch_size, total_budget, recover):
        try:
            while not self._stop.is_set() and self._budget_completed < total_budget:
                report = lab.run_plan(
                    plan, output,
                    max_jobs=min(batch_size, total_budget - self._budget_completed),
                    recover_verified_orphans=recover,
                )
                launched = self._verified_runner_count(
                    report, min(batch_size, total_budget - self._budget_completed))
                reconciled, defined = report.get("reconciled_jobs"), report.get("defined_jobs")
                if (type(reconciled) is not int or type(defined) is not int
                        or not 0 <= reconciled <= defined <= CAP):
                    raise ValueError("Research runner returned invalid reconciled/defined job counts")
                with self._lock:
                    self._budget_completed += launched
                if reconciled >= defined:
                    break
                if launched == 0 and report.get("recovered_verified_orphans", 0) == 0:
                    raise RuntimeError("Research made no progress; manual investigation required")
        except Exception as exc:
            with self._lock:
                self._latest_error[plan_id] = type(exc).__name__ + ": " + str(exc)[:300]
        finally:
            with self._lock:
                self._active = None
                self._run_mode = "IDLE"


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, hub, ui_file: Path, token: str):
        super().__init__(address, ConsoleHandler)
        self.hub, self.ui_file, self.token = hub, ui_file, token


class ConsoleHandler(BaseHTTPRequestHandler):
    server: ConsoleServer

    def log_message(self, fmt, *args):
        # Do not print token-bearing browser URLs, source paths, or requests.
        pass

    def _guard(self):
        host = self.headers.get("Host", "")
        expected_port = self.server.server_address[1]
        if host not in (f"127.0.0.1:{expected_port}", f"localhost:{expected_port}"):
            raise PermissionError("Loopback Host required")
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{expected_port}",
                                    f"http://localhost:{expected_port}"):
            raise PermissionError("Cross-origin research actions forbidden")
        if self.path.startswith("/api/") and not secrets.compare_digest(
            self.headers.get("X-NRFX-Token", ""), self.server.token
        ):
            raise PermissionError("Invalid local session token")

    def _send(self, status: int, data: bytes, kind: str):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, obj: object):
        self._send(status, json.dumps(obj, ensure_ascii=False, allow_nan=False).encode(),
                   "application/json; charset=utf-8")

    def _handle_error(self, exc: Exception):
        status = 403 if isinstance(exc, PermissionError) else 400 if isinstance(exc, (ValueError, KeyError, FileNotFoundError)) else 500
        self._json(status, {"error": type(exc).__name__, "message": str(exc)[:400]})

    def do_GET(self):
        try:
            self._guard()
            parsed = urlsplit(self.path)
            if parsed.path == "/":
                html = self.server.ui_file.read_bytes()
                return self._send(200, html, "text/html; charset=utf-8")
            if parsed.path == "/api/status":
                return self._json(200, self.server.hub.status())
            if parsed.path == "/api/plans":
                return self._json(200, self.server.hub.list_plans())
            if parsed.path == "/api/runs":
                return self._json(200, self.server.hub.list_runs())
            params = parse_qs(parsed.query)
            if parsed.path == "/api/results":
                return self._json(200, self.server.hub.run_results(
                    params["plan_id"][0], offset=int(params.get("offset", ["0"])[0]),
                    limit=int(params.get("limit", ["50"])[0])))
            if parsed.path == "/api/weekly":
                return self._json(200, self.server.hub.weekly(
                    params["plan_id"][0], params["job_id"][0]))
            if parsed.path == "/api/evidence":
                payload, mime = self.server.hub.evidence_bytes(
                    params["plan_id"][0], params["job_id"][0], params["file"][0])
                return self._send(200, payload, mime)
            if parsed.path == "/api/monthly":
                return self._json(200, self.server.hub.monthly(params["plan_id"][0], params["job_id"][0]))
            return self._json(404, {"error": "not_found"})
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self):
        try:
            self._guard()
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("JSON requests only")
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except (ValueError, OverflowError) as exc:
                raise ValueError("Invalid Content-Length") from exc
            if not 0 < size <= MAX_BODY:
                raise ValueError("Request exceeds 32 KiB or is empty")
            payload = decode_request_json(self.rfile.read(size))
            parsed = urlsplit(self.path)
            hub = self.server.hub
            if parsed.path == "/api/configure":
                return self._json(200, hub.configure(strict_dict(payload, {"source_path"})["source_path"]))
            if parsed.path == "/api/preview":
                return self._json(200, hub.preview(payload))
            if parsed.path == "/api/freeze":
                return self._json(200, hub.freeze(payload))
            if parsed.path == "/api/freeze-universe":
                p = strict_dict(payload, {"years"})
                return self._json(200, hub.freeze_research_universe(p["years"]))
            if parsed.path == "/api/cross-year":
                p = strict_dict(payload, {"plan_id"})
                return self._json(200, hub.cross_year_comparison(p["plan_id"]))
            if parsed.path == "/api/start":
                p = strict_dict(payload, {"plan_id", "budget", "recover"})
                return self._json(202, hub.start(p["plan_id"], p["budget"], recover=p["recover"]))
            if parsed.path == "/api/autopilot":
                p = strict_dict(payload, {"plan_id", "batch_size", "total_budget", "recover"})
                return self._json(202, hub.start_autopilot(p["plan_id"],
                    p["batch_size"], p["total_budget"], recover=p["recover"]))
            if parsed.path == "/api/stop":
                p = strict_dict(payload, {"plan_id"})
                return self._json(202, hub.stop_autopilot(p["plan_id"]))
            if parsed.path == "/api/verify":
                p = strict_dict(payload, {"plan_id"})
                return self._json(200, hub.verify_run(p["plan_id"]))
            return self._json(404, {"error": "not_found"})
        except Exception as exc:
            self._handle_error(exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "NoRiskFX_QuantLab")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("Invalid local port")
    hub = ResearchHub(args.workspace)
    token = secrets.token_urlsafe(32)
    ui_file = Path(__file__).with_name("quantlab_desktop_ui.html")
    with ConsoleServer(("127.0.0.1", args.port), hub, ui_file, token) as server:
        uri = f"http://127.0.0.1:{server.server_port}/#{token}"
        print("\nNO RISK FX QUANT LAB — LOCAL RESEARCH ONLY\n" + uri, flush=True)
        print("Original source stays on this computer. No broker or internet endpoints.", flush=True)
        if args.open:
            webbrowser.open(uri)
        try:
            server.serve_forever(poll_interval=.25)
        except KeyboardInterrupt:
            print("\nConsole closed. Restart to resume an interrupted batch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
