# Independent source M1 gap-minute accounting — 2026-10-29

## Problem

The frozen annual runner checked exit prices, source-bar stop/target timing,
15-field persisted trade parity, fees, and UTC period allocation. It did not
independently recompute each trade's `gap_minutes` from the observed source
calendar. Identical incorrect in-memory and CSV gap values could therefore
survive the export comparison.

## Change

`verify_source_gap_minutes` uses a cumulative count of missing UTC M1
minute opens. For each executed trade it checks the exact observed entry and
exit timestamps and verifies that `gap_minutes` equals the missing-minute
count *after entry through exit*. Missing minutes before a new entry do not
belong to the position. The frozen annual runner now checks every trade
before producing an annual report and records the count verified.

Fail-closed conditions include unknown timestamps, reversed chronology,
non-UTC or unaligned source timestamps, duplicate columns, and non-integer,
boolean, negative, or falsified gap values. A synthetic integration test
replays a genuine `run_limits` gap-stop path.

This is an audit of missing **observed quote minutes**, not proof of
exchange/broker closures, real tick ordering, or profitable execution.
The all-in fee remains exactly $0.40/oz; strategy parameters and research
samples are unchanged. No original Gold ZIP or raw quotes are committed.

## Verification boundaries

Local isolated function examples verified two consecutive source gaps (5
missing minutes total), a later entry (3), and same-minute entry/exit (0).
New package tests and full current-HEAD pytest/CI require an actual run;
the private original-Gold-ZIP 13-field replay remains unverified on this
revision. PR #1 stays Draft.
