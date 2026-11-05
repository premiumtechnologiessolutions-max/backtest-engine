from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from norisk_quant.lab_proposals import (
    SCHEMA, UPSTREAM_PINS, normalize_proposal_envelope, run_proposal_campaign,
)
from norisk_quant.math_discovery import Formula


def _envelope(*formulas, generator='rd-agent'):
    return dict(schema=SCHEMA, generator=generator,
                source_commit=UPSTREAM_PINS[generator][1], proposals=list(formulas))


class LabProposalsTests(unittest.TestCase):
    def test_normalization_is_canonical_and_deduplicates_numeric_equivalents(self):
        first = asdict(Formula(threshold=1))
        second = asdict(Formula(threshold=2))
        normal = normalize_proposal_envelope(_envelope(first, second))
        self.assertEqual(normal, normalize_proposal_envelope(_envelope(second, first)))
        self.assertEqual(normal, normalize_proposal_envelope(normal))
        self.assertTrue(all(type(row['threshold']) is float for row in normal['proposals']))
        with self.assertRaisesRegex(ValueError, 'Duplicate or equivalent'):
            normalize_proposal_envelope(_envelope(first, dict(first, threshold=1.0)))

    def test_untrusted_fields_and_invalid_pins_are_rejected(self):
        proposal = asdict(Formula())
        source = _envelope(proposal)
        invalid = (
            dict(source, reported_score=9), dict(source, generator=['rd-agent']),
            dict(source, source_commit='a' * 40),
            _envelope(dict(proposal, code='print(1)')),
            _envelope(dict(proposal, market_data='/tmp/gold.parquet')),
            _envelope(dict(proposal, reverse=True)),
            _envelope(dict(proposal, threshold=float('nan'))),
            _envelope(dict(proposal, threshold=10**800)),
        )
        for index, envelope in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(ValueError):
                normalize_proposal_envelope(envelope)

    def test_interactive_batch_has_separate_bound(self):
        formulas = [asdict(Formula(lookback=n)) for n in range(5, 22)]
        accepted = normalize_proposal_envelope(_envelope(*formulas[:16]))
        self.assertEqual(len(accepted['proposals']), 16)
        for batch in ([], formulas):
            with self.assertRaisesRegex(ValueError, r'1\.\.16'):
                normalize_proposal_envelope(_envelope(*batch))

    def test_external_handoff_runs_both_canonical_engines_on_synthetic_bars(self):
        trading = Formula(lookback=12, threshold=.3, stop_usd=1.5, cooldown=8)
        inactive = Formula(lookback=240)
        envelope = _envelope(asdict(trading), asdict(inactive), generator='tradingagents')
        stages = []
        result = run_proposal_campaign(dict(envelope=envelope, bars=240, seed=19), stages.append)
        self.assertEqual(stages, result['stages'][:-1])
        self.assertEqual(result['provenance'], 'SYNTHETIC_NOT_MARKET')
        self.assertEqual(result['upstream_repository'], 'TauricResearch/TradingAgents')
        self.assertEqual(result['upstream_commit_asserted'], envelope['source_commit'])
        for field in ('upstream_runtime_executed', 'provenance_authenticated',
                      'market_data_accessed', 'live_trading_enabled', 'independent_oos_proven'):
            self.assertIs(result[field], False)
        by_id = {candidate['id']: candidate for candidate in result['candidates']}
        self.assertGreater(by_id[trading.identity()]['trades'], 0)
        self.assertEqual(by_id[inactive.identity()]['trades'], 0)
        for candidate in by_id.values():
            self.assertIs(candidate['parity_passed'], True)
            self.assertEqual(candidate['curve'][-1], candidate['net_usd_per_oz'])
            self.assertRegex(candidate['trade_ledger_sha256'], r'^[0-9a-f]{64}$')
        replay = dict(envelope, proposals=list(reversed(envelope['proposals'])))
        self.assertEqual(result, run_proposal_campaign(dict(envelope=replay, bars=240, seed=19)))
        json.dumps(result, allow_nan=False)

    def test_legacy_file_intake_stays_strict_and_keeps_raw_input_digest(self):
        from scripts.import_external_formula_proposals import load_proposals

        envelope = _envelope(*(asdict(Formula(lookback=n)) for n in range(5, 22)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'envelope.json'
            raw = json.dumps(envelope, indent=2).encode()
            path.write_bytes(raw)
            report, payload = load_proposals(path)
            self.assertEqual(report['status'], 'PROPOSED_UNEVALUATED')
            self.assertEqual(report['formula_count'], 17)
            self.assertEqual(report['input_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(payload, raw)
            path.write_bytes(raw.replace(b'"generator":', b'"generator": null, "generator":', 1))
            with self.assertRaisesRegex(ValueError, 'Duplicate external proposal JSON key'):
                load_proposals(path)


if __name__ == '__main__':
    unittest.main()
