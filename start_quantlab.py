"""Launch standalone Quant Lab UI against an already clean engine checkout.

Keep this UI distribution OUTSIDE the Git repo so the frozen engine remains
commit-pinned and does not gain untracked importable modules in scripts/src.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-repo", required=True, type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "NoRiskFX_QuantLab")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    repo = args.engine_repo.expanduser().resolve()
    if not (repo / ".git").exists() or not (repo / "scripts" / "research_batch_orchestrator.py").is_file():
        parser.error("Engine repository must be an actual local Git checkout")
    if not (repo / "src" / "norisk_quant" / "cli.py").is_file():
        parser.error("Missing official No Risk FX engine package")
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(repo / "src"))
    root = Path(__file__).resolve().parent
    app_file = root / "scripts" / "quantlab_desktop.py"
    spec = importlib.util.spec_from_file_location("nrfx_quantlab_local_app", app_file)
    if spec is None or spec.loader is None:
        parser.error("Standalone UI files are missing")
    console = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(console)
    opts = ["--workspace", str(args.workspace), "--port", str(args.port)]
    if args.open:
        opts.append("--open")
    return console.main(opts)


if __name__ == "__main__":
    raise SystemExit(main())
