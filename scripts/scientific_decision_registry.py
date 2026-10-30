"""Owner-private B11 scientific rejection gate (not an execution service).

Use --record only after original Gold B09 annual on-disk reattestation.
CLI never sends trading orders or automatically approves research.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from norisk_quant.scientific_rejection_registry import (
    ScientificDecisionJournal, evidence_from_audited_year,
)
from norisk_quant.source_registry import verify_record_manifest
from scripts import research_batch_orchestrator as batch

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal",required=True,type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record",action="store_true")
    mode.add_argument("--gate",action="store_true")
    mode.add_argument("--audit",action="store_true")
    parser.add_argument("--plan",type=Path)
    parser.add_argument("--source-manifest",type=Path)
    parser.add_argument("--reports",type=Path)
    parser.add_argument("--experiment-id")
    arg=parser.parse_args(argv)
    try:
        if not arg.record and not arg.journal.is_file():
            raise ValueError("Private scientific journal not registered")
        if arg.record:
            if not all((arg.plan,arg.source_manifest,arg.reports,arg.experiment_id)):
                raise ValueError("Missing original frozen evidence source")
            p=batch.read_strict_json(arg.plan)
            sr=verify_record_manifest(batch.read_strict_json(arg.source_manifest))
            if sr.family!="original_gold_m1_bidask" or p["source_sha256"]!=sr.source_file_sha256:
                raise ValueError("Research outcome has no original Gold source lineage")
            e=evidence_from_audited_year(p,arg.reports,experiment_id=arg.experiment_id,
                                         source_manifest_id=sr.id)
            result=ScientificDecisionJournal(arg.journal).append(e)
            public={"recorded":result["recorded"],"disposition":e["disposition"],
                    "year":e["year"],"months_observed":12,"trades":e["trades"],
                    "positive_months":e["positive_months"],"history_chain_head":result["chain_head"],
                    "independent_oos":False,"broker_fills_verified":False,
                    "profitability_verified":False,"approved_for_live":False}
        elif arg.gate:
            if arg.plan is None:raise ValueError("Frozen strategy plan required")
            public=ScientificDecisionJournal(arg.journal).candidate_gate(batch.read_strict_json(arg.plan))
        else:
            public=ScientificDecisionJournal(arg.journal).audit()
    except (OSError,ValueError,KeyError,TypeError,OverflowError):
        parser.exit(2,"Scientific decision rejected; no strategy approved or traded.\n")
    print(json.dumps(public,sort_keys=True,allow_nan=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
