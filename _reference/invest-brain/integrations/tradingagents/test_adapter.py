from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

import sys

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

def _drop_foreign_local_modules(names):
    for name in names:
        module = sys.modules.get(name)
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve().parent != THIS_DIR:
            del sys.modules[name]

_drop_foreign_local_modules(('schemas', 'ab_test', 'parse_report', 'generate_challenge', 'completion_audit', 'batch', 'codex_native', 'provider_config', 'setup_env', 'run_sidecar', 'doctor'))

from parse_report import parse_inputs
from generate_challenge import render_challenge
from ab_test import (
    aggregate_gradings,
    compare_protected_snapshots,
    grading_template,
    init_sample,
    protected_snapshot,
    SAMPLE_POOL,
    validate_grading,
)
from doctor import collect_status
from completion_audit import (
    ab_text_links_codex_native_evidence,
    ab_text_links_sidecar_evidence,
    completion_audit,
    has_placeholder_text,
    render_markdown as render_completion_audit_markdown,
)
from batch import batch_plan, init_ab_pool, run_sidecar_pool
from codex_native import codex_native_plan, init_codex_native_sample
from provider_config import known_api_keys, provider_api_keys
from setup_env import PINNED_COMMIT, paths
from run_sidecar import required_key_for_provider, assert_provider_ready, main as run_sidecar_main
from schemas import IntegrationError, archive_slug, assert_safe_output_path, validate_ticker
from schemas import load_env_files, parse_env_line


class TestTradingAgentsAdapter(unittest.TestCase):
    def test_ticker_validation_rejects_path_escape(self):
        with self.assertRaises(IntegrationError):
            validate_ticker("../NVDA")
        with self.assertRaises(IntegrationError):
            validate_ticker("NVDA/../../state")

    def test_archive_slug_preserves_exchange_suffix_safely(self):
        self.assertEqual(archive_slug("0700.HK"), "0700-hk")
        self.assertEqual(archive_slug("BRK-B"), "brk-b")

    def test_protected_output_path_rejected(self):
        protected = THIS_DIR.parents[1] / "state" / "portfolio.md"
        with self.assertRaises(IntegrationError):
            assert_safe_output_path(protected)

    def test_parse_sample_report(self):
        sample = THIS_DIR / "fixtures" / "sample_complete_report.md"
        evidence = parse_inputs("NVDA", "2026-05-05", sample, None)
        data = evidence.to_dict()
        self.assertEqual(data["ticker"], "NVDA")
        self.assertEqual(data["rating"], "Hold")
        self.assertGreaterEqual(len(data["claims"]), 1)
        self.assertGreaterEqual(len(data["risks"]), 1)
        self.assertEqual(data["suggested_entry"], 180.0)
        self.assertEqual(data["suggested_stop"], 165.0)

    def test_evidence_json_roundtrip_shape(self):
        sample = THIS_DIR / "fixtures" / "sample_complete_report.md"
        evidence = parse_inputs("NVDA", "2026-05-05", sample, None)
        with tempfile.TemporaryDirectory() as tmp:
            out = THIS_DIR.parents[1] / "research" / "archive" / "2099-01-01-test-tradingagents" / "tradingagents_extract.json"
            try:
                evidence.write_json(out)
                loaded = json.loads(out.read_text(encoding="utf-8"))
                self.assertEqual(loaded["source"], "tradingagents")
                self.assertIn("raw_sections", loaded)
            finally:
                if out.exists():
                    out.unlink()
                if out.parent.exists():
                    out.parent.rmdir()

    def test_generate_challenge_keeps_local_gate(self):
        sample = THIS_DIR / "fixtures" / "sample_complete_report.md"
        evidence = parse_inputs("NVDA", "2026-05-05", sample, None)
        challenge = render_challenge(evidence.to_dict())
        self.assertIn("TradingAgents is external evidence only", challenge)
        self.assertIn("Local score: TODO / 10", challenge)
        self.assertIn("score >= 6.0", challenge)

    def test_ab_validate_grading_adds_totals(self):
        payload = grading_template("NVDA", "2026-05-05")
        payload["scores"]["a_old_flow"]["fact_verifiability"] = 20
        payload["scores"]["b_with_tradingagents"]["fact_verifiability"] = 25
        validated = validate_grading(payload)
        self.assertEqual(validated["a_total"], 20)
        self.assertEqual(validated["b_total"], 25)
        self.assertEqual(validated["delta"], 5)

    def test_ab_aggregate_requires_full_pass_criteria(self):
        gradings = []
        for sample in SAMPLE_POOL:
            payload = grading_template(sample["ticker"], "2026-05-05")
            payload["status"] = "final"
            payload["has_incremental_information"] = True
            payload["scores"]["a_old_flow"] = {
                "fact_verifiability": 20,
                "risk_coverage": 15,
                "catalyst_clarity": 10,
                "decision_discipline": 20,
                "incremental_information": 0,
                "actionability": 8,
            }
            payload["scores"]["b_with_tradingagents"] = {
                "fact_verifiability": 23,
                "risk_coverage": 19,
                "catalyst_clarity": 12,
                "decision_discipline": 20,
                "incremental_information": 8,
                "actionability": 9,
            }
            gradings.append(validate_grading(payload))
        result = aggregate_gradings(
            gradings,
            protected_audits=[{"writeback_violation": False, "changed_files": []}],
        )
        self.assertEqual(result.verdict, "PASS")

    def test_ab_aggregate_requires_required_sample_pool_for_pass(self):
        gradings = []
        for i in range(10):
            payload = grading_template(f"T{i}", "2026-05-05")
            payload["status"] = "final"
            payload["has_incremental_information"] = True
            payload["scores"]["a_old_flow"] = {
                "fact_verifiability": 20,
                "risk_coverage": 15,
                "catalyst_clarity": 10,
                "decision_discipline": 20,
                "incremental_information": 0,
                "actionability": 8,
            }
            payload["scores"]["b_with_tradingagents"] = {
                "fact_verifiability": 23,
                "risk_coverage": 19,
                "catalyst_clarity": 12,
                "decision_discipline": 20,
                "incremental_information": 8,
                "actionability": 9,
            }
            gradings.append(validate_grading(payload))
        result = aggregate_gradings(
            gradings,
            protected_audits=[{"writeback_violation": False, "changed_files": []}],
        )
        self.assertNotEqual(result.verdict, "PASS")
        self.assertTrue(result.missing_required_tickers)

    def test_ab_aggregate_requires_protected_audit_for_pass(self):
        gradings = []
        for sample in SAMPLE_POOL:
            payload = grading_template(sample["ticker"], "2026-05-05")
            payload["status"] = "final"
            payload["has_incremental_information"] = True
            payload["scores"]["a_old_flow"] = {
                "fact_verifiability": 20,
                "risk_coverage": 15,
                "catalyst_clarity": 10,
                "decision_discipline": 20,
                "incremental_information": 0,
                "actionability": 8,
            }
            payload["scores"]["b_with_tradingagents"] = {
                "fact_verifiability": 23,
                "risk_coverage": 19,
                "catalyst_clarity": 12,
                "decision_discipline": 20,
                "incremental_information": 8,
                "actionability": 9,
            }
            gradings.append(validate_grading(payload))
        result = aggregate_gradings(gradings)
        self.assertNotEqual(result.verdict, "PASS")
        self.assertIn("Protected file audit is required", " ".join(result.notes))

    def test_ab_aggregate_requires_final_status_for_pass(self):
        gradings = []
        for sample in SAMPLE_POOL:
            payload = grading_template(sample["ticker"], "2026-05-05")
            payload["has_incremental_information"] = True
            payload["scores"]["a_old_flow"] = {
                "fact_verifiability": 20,
                "risk_coverage": 15,
                "catalyst_clarity": 10,
                "decision_discipline": 20,
                "incremental_information": 0,
                "actionability": 8,
            }
            payload["scores"]["b_with_tradingagents"] = {
                "fact_verifiability": 23,
                "risk_coverage": 19,
                "catalyst_clarity": 12,
                "decision_discipline": 20,
                "incremental_information": 8,
                "actionability": 9,
            }
            gradings.append(validate_grading(payload))
        result = aggregate_gradings(
            gradings,
            protected_audits=[{"writeback_violation": False, "changed_files": []}],
        )
        self.assertNotEqual(result.verdict, "PASS")
        self.assertIn("status=final", " ".join(result.notes))

    def test_ab_aggregate_fails_on_protected_audit_change(self):
        gradings = []
        for sample in SAMPLE_POOL:
            payload = grading_template(sample["ticker"], "2026-05-05")
            payload["status"] = "final"
            payload["has_incremental_information"] = True
            payload["scores"]["a_old_flow"] = {
                "fact_verifiability": 20,
                "risk_coverage": 15,
                "catalyst_clarity": 10,
                "decision_discipline": 20,
                "incremental_information": 0,
                "actionability": 8,
            }
            payload["scores"]["b_with_tradingagents"] = {
                "fact_verifiability": 23,
                "risk_coverage": 19,
                "catalyst_clarity": 12,
                "decision_discipline": 20,
                "incremental_information": 8,
                "actionability": 9,
            }
            gradings.append(validate_grading(payload))
        result = aggregate_gradings(
            gradings,
            protected_audits=[{
                "writeback_violation": True,
                "changed_files": ["state/portfolio.md"],
            }],
        )
        self.assertEqual(result.verdict, "FAIL")
        self.assertIn("state/portfolio.md", result.protected_audit_changed_files)

    def test_protected_snapshot_detects_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            watched = Path(tmp) / "watched.md"
            watched.write_text("before", encoding="utf-8")
            before = protected_snapshot([watched])
            watched.write_text("after", encoding="utf-8")
            after = protected_snapshot([watched])
            audit = compare_protected_snapshots(before, after)
            self.assertTrue(audit["writeback_violation"])
            self.assertIn(str(watched), audit["changed_files"])

    def test_completion_audit_reports_incomplete_without_real_outputs(self):
        payload = completion_audit("2099-01-12", protected_audit_paths=[])
        self.assertFalse(payload["overall_passed"])
        item_names = {item["name"] for item in payload["items"]}
        self.assertIn("ten_real_sidecar_outputs", item_names)
        rendered = render_completion_audit_markdown(payload)
        self.assertIn("Overall passed: `False`", rendered)

    def test_completion_audit_rejects_placeholder_ab_content(self):
        try:
            paths = init_ab_pool("2099-01-18", force=True)
            for path in paths:
                grading_path = path / "ab_grading.json"
                grading = json.loads(grading_path.read_text(encoding="utf-8"))
                grading["status"] = "final"
                grading["has_incremental_information"] = True
                grading["notes"]["b_added"] = ["placeholder detection test"]
                grading["notes"]["gate_check"] = "local gate preserved"
                grading_path.write_text(json.dumps(grading, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            payload = completion_audit("2099-01-18", protected_audit_paths=[])
            ab_item = next(item for item in payload["items"] if item["name"] == "ten_ab_samples_present_and_final")
            self.assertFalse(ab_item["passed"])
            self.assertIn("placeholder", " ".join(ab_item["notes"]).lower())
            self.assertTrue(has_placeholder_text(paths[0] / "a_old_flow.md"))
        finally:
            for sample in SAMPLE_POOL:
                out_dir = THIS_DIR.parents[1] / "research" / "archive" / f"2099-01-18-abtest-{sample['ticker'].replace('.', '-').lower()}"
                for child in sorted(out_dir.glob("*")):
                    if child.is_file():
                        child.unlink()
                if out_dir.exists():
                    out_dir.rmdir()

    def test_completion_audit_requires_b_text_to_reference_sidecar_evidence(self):
        self.assertTrue(ab_text_links_sidecar_evidence("Uses tradingagents_extract.json and local_challenge.md."))
        self.assertFalse(ab_text_links_sidecar_evidence("Uses only local notes."))
        self.assertTrue(ab_text_links_codex_native_evidence("Uses codex_native_plan.json and codex_native_prompt.md."))
        self.assertFalse(ab_text_links_codex_native_evidence("Uses tradingagents_extract.json and local_challenge.md."))

    def test_completion_audit_codex_native_mode_requires_codex_artifacts(self):
        payload = completion_audit("2099-01-19", protected_audit_paths=[], evidence_mode="codex-native")
        self.assertFalse(payload["overall_passed"])
        item_names = {item["name"] for item in payload["items"]}
        self.assertIn("ten_codex_native_artifacts", item_names)
        self.assertNotIn("ten_real_sidecar_outputs", item_names)

    def test_codex_native_sample_writes_plan_prompt_and_b_template(self):
        out_dir = THIS_DIR.parents[1] / "research" / "archive" / "2099-01-20-abtest-nvda"
        try:
            created = init_codex_native_sample("NVDA", "2099-01-20", force=True)
            self.assertEqual(created, out_dir)
            self.assertTrue((out_dir / "codex_native_plan.json").exists())
            self.assertTrue((out_dir / "codex_native_prompt.md").exists())
            b_text = (out_dir / "b_with_tradingagents.md").read_text(encoding="utf-8")
            self.assertIn("codex_native_plan.json", b_text)
            self.assertIn("codex_native_prompt.md", b_text)
            plan = codex_native_plan("NVDA", "2099-01-20")
            self.assertEqual(plan["mode"], "codex_native")
            self.assertFalse(plan["writeback_allowed"])
        finally:
            for child in sorted(out_dir.glob("*")):
                if child.is_file():
                    child.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_batch_plan_covers_required_pool(self):
        plan = batch_plan("2099-01-13")
        self.assertEqual(len(plan.sidecar_dirs), len(SAMPLE_POOL))
        self.assertEqual(len(plan.ab_sample_dirs), len(SAMPLE_POOL))
        self.assertIn("protected_audit.json", plan.protected_audit)
        self.assertIn("completion_audit.json", plan.completion_audit_json)

    def test_batch_init_ab_pool_writes_all_samples(self):
        try:
            paths = init_ab_pool("2099-01-14", force=True)
            self.assertEqual(len(paths), len(SAMPLE_POOL))
            for path in paths:
                self.assertTrue((path / "ab_grading.json").exists())
        finally:
            for sample in SAMPLE_POOL:
                out_dir = THIS_DIR.parents[1] / "research" / "archive" / f"2099-01-14-abtest-{sample['ticker'].replace('.', '-').lower()}"
                for child in sorted(out_dir.glob("*")):
                    if child.is_file():
                        child.unlink()
                if out_dir.exists():
                    out_dir.rmdir()

    def test_batch_run_sidecars_preflights_missing_provider_key(self):
        import os
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                run_sidecar_pool(
                    analysis_date="2099-01-15",
                    llm_provider="openai",
                    analysts=["market"],
                    output_language="Chinese",
                    checkpoint=False,
                    quick_model=None,
                    deep_model=None,
                    backend_url=None,
                    continue_on_error=False,
                )
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old

    def test_ab_init_sample_writes_expected_files(self):
        out_dir = THIS_DIR.parents[1] / "research" / "archive" / "2099-01-04-abtest-nvda"
        try:
            created = init_sample("NVDA", "2099-01-04", force=True)
            self.assertEqual(created, out_dir)
            self.assertTrue((out_dir / "a_old_flow.md").exists())
            self.assertTrue((out_dir / "b_with_tradingagents.md").exists())
            self.assertTrue((out_dir / "ab_grading.json").exists())
        finally:
            for child in sorted(out_dir.glob("*")):
                child.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_sidecar_ingest_generates_local_challenge(self):
        out_dir = THIS_DIR.parents[1] / "research" / "archive" / "2099-01-09-tradingagents-nvda"
        sample = THIS_DIR / "fixtures" / "sample_complete_report.md"
        try:
            run_sidecar_main([
                "--ticker", "NVDA",
                "--analysis-date", "2099-01-09",
                "--from-report", str(sample),
            ])
            challenge = out_dir / "local_challenge.md"
            metadata = json.loads((out_dir / "tradingagents_metadata.json").read_text(encoding="utf-8"))
            self.assertTrue(challenge.exists())
            self.assertIn("TradingAgents is external evidence only", challenge.read_text(encoding="utf-8"))
            self.assertIn("Generated local red-team challenge", " ".join(metadata["notes"]))
        finally:
            for child in sorted(out_dir.glob("*")):
                if child.is_file():
                    child.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_doctor_reports_boundary_status(self):
        status = collect_status()
        self.assertIn("ready_for_real_sidecar_run", status)
        self.assertIn("readiness_blockers", status)
        self.assertIn("next_actions", status)
        self.assertIn("isolated_tradingagents_package", status)
        self.assertTrue(status["boundary"]["research_archive_allowed"])
        self.assertTrue(status["boundary"]["adapter_cache_allowed"])
        self.assertTrue(all(value == "blocked" for value in status["boundary"]["protected_paths"].values()))

    def test_setup_env_uses_pinned_commit_and_cache_paths(self):
        self.assertEqual(PINNED_COMMIT, "7e9e7b83c7fcc18d941300b253c6ed24d985788d")
        p = paths()
        self.assertIn(".cache", str(p["upstream"]))
        self.assertIn(".cache", str(p["venv"]))

    def test_provider_key_mapping(self):
        self.assertEqual(required_key_for_provider("openai"), "OPENAI_API_KEY")
        self.assertEqual(required_key_for_provider("qwen"), "DASHSCOPE_API_KEY")
        self.assertIsNone(required_key_for_provider("ollama"))
        self.assertIn("OPENAI_API_KEY", provider_api_keys())
        self.assertIn("ALPHA_VANTAGE_API_KEY", known_api_keys())

    def test_ollama_preflight_requires_explicit_models(self):
        with self.assertRaises(RuntimeError):
            assert_provider_ready("ollama")

    def test_env_loader_reads_dotenv_without_overriding_existing_values(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "OPENAI_API_KEY=from_file\n"
                "export GOOGLE_API_KEY='quoted_value'\n"
                "# ignored\n",
                encoding="utf-8",
            )
            old_openai = os.environ.get("OPENAI_API_KEY")
            old_google = os.environ.get("GOOGLE_API_KEY")
            os.environ["OPENAI_API_KEY"] = "already_set"
            os.environ.pop("GOOGLE_API_KEY", None)
            try:
                loaded = load_env_files([env_path])
                self.assertEqual(loaded, [env_path])
                self.assertEqual(os.environ["OPENAI_API_KEY"], "already_set")
                self.assertEqual(os.environ["GOOGLE_API_KEY"], "quoted_value")
            finally:
                if old_openai is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = old_openai
                if old_google is None:
                    os.environ.pop("GOOGLE_API_KEY", None)
                else:
                    os.environ["GOOGLE_API_KEY"] = old_google

    def test_env_line_parser_rejects_invalid_keys(self):
        self.assertEqual(parse_env_line("OPENAI_API_KEY=abc"), ("OPENAI_API_KEY", "abc"))
        self.assertIsNone(parse_env_line("BAD-KEY=value"))

    def test_execute_preflight_rejects_missing_key(self):
        import os
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                assert_provider_ready("openai")
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
