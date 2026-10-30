"""Atomic private output invariants for canonical research files."""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from norisk_quant.report import _private_csv, _private_json


def test_csv_writes_are_not_public_even_with_normal_umask(tmp_path):
    file=tmp_path/"trades.csv"
    frame=pd.DataFrame([{"trade":1,"net_pnl":-1.2},{"trade":2,"net_pnl":1.3}])
    _private_csv(frame,file,index=False)
    assert pd.read_csv(file)["net_pnl"].sum()==pytest.approx(0.1)
    if os.name=="posix":
        assert file.stat().st_mode & 0o077 == 0


def test_json_writes_are_owner_only_and_strict(tmp_path):
    file=tmp_path/"summary.json"
    _private_json({"status":"research","net_pnl":-2.3},file)
    assert json.loads(file.read_text(encoding="utf-8"))["net_pnl"]==-2.3
    if os.name=="posix":
        assert file.stat().st_mode & 0o077 == 0


def test_invalid_nonfinite_report_does_not_replace_frozen_original(tmp_path):
    file=tmp_path/"summary.json"
    _private_json({"status":"unverified"},file)
    before=file.read_bytes()
    with pytest.raises(ValueError,match="Out of range float"):
        _private_json({"profit":float("inf")},file)
    assert file.read_bytes()==before
    assert not list(tmp_path.glob(".nrfx-report-*"))


def test_repeat_report_replaces_atomically_and_keeps_owner_only_permissions(tmp_path):
    file=tmp_path/"monthly.csv"
    _private_csv(pd.DataFrame([{"period":"2024-01","net_pnl":-4.0}]),file,index=False)
    _private_csv(pd.DataFrame([{"period":"2024-01","net_pnl":7.0}]),file,index=False)
    assert float(pd.read_csv(file)["net_pnl"].iloc[0])==7.0
    if os.name=="posix":
        assert file.stat().st_mode & 0o077 == 0
    assert not list(tmp_path.glob(".nrfx-report-*"))


def test_existing_file_symlink_never_followed(tmp_path):
    target=tmp_path/"protected.txt"
    target.write_text("never overwrite")
    link=tmp_path/"trades.csv"
    try:
        link.symlink_to(target)
    except (NotImplementedError,OSError):
        pytest.skip("No symlink support")
    with pytest.raises(ValueError,match="Unsafe"):
        _private_csv(pd.DataFrame([{"profit":100}]),link,index=False)
    assert target.read_text()=="never overwrite"


@pytest.mark.skipif(os.name!="posix",reason="POSIX hardlink invariant")
def test_hardlinked_report_cannot_be_published(tmp_path):
    file=tmp_path/"monthly.csv"
    other=tmp_path/"private-hardlink.csv"
    _private_csv(pd.DataFrame([{"net_pnl":-1}]),file,index=False)
    os.link(file,other)
    before=file.read_bytes()
    with pytest.raises(ValueError,match="Unsafe"):
        _private_csv(pd.DataFrame([{"net_pnl":999}]),file,index=False)
    assert other.read_bytes()==before


def test_crashing_csv_writer_does_not_corrupt_existing_report(tmp_path):
    class BadFrame:
        def to_csv(self,handle,**kwargs):
            handle.write("partial secret report")
            raise RuntimeError("synthetic output crash")
    file=tmp_path/"weekly.csv"
    _private_csv(pd.DataFrame([{"trades":1}]),file,index=False)
    before=file.read_bytes()
    with pytest.raises(RuntimeError,match="synthetic output crash"):
        _private_csv(BadFrame(),file,index=False)
    assert file.read_bytes()==before
    assert not list(tmp_path.glob(".nrfx-report-*"))
