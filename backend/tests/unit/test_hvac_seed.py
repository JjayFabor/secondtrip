from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path

from seeds.hvac import COLUMNS, FIXTURE_VERSION, demo_rows, performance_rows, render_csv


def test_performance_fixture_is_deterministic_and_unique() -> None:
    first = render_csv(performance_rows(1_000))
    second = render_csv(performance_rows(1_000))
    assert first == second
    assert first.rows == 1_000
    parsed = list(csv.DictReader(io.StringIO(first.body.decode())))
    assert tuple(parsed[0]) == COLUMNS
    assert len({row["Job ID"] for row in parsed}) == 1_000
    assert len({row["Customer ID"] for row in parsed}) == 200
    assert sum(not row["Equipment ID"] for row in parsed) == 100
    assert len({row["Category"] for row in parsed}) == 8
    assert sum(bool(row["Notes"]) for row in parsed) == 100


def test_demo_fixture_has_documented_shape() -> None:
    fixture = render_csv(demo_rows())
    parsed = list(csv.DictReader(io.StringIO(fixture.body.decode())))
    by_id = {row["Job ID"]: row for row in parsed}
    assert fixture.rows == 96
    assert len({row["Job ID"] for row in parsed}) == 96
    assert sum(row["Job ID"].startswith("DEMO-CB-") for row in parsed) == 24
    assert sum(row["Job ID"].startswith("DEMO-MAINT-") for row in parsed) == 16
    assert sum(row["Job ID"].startswith("DEMO-PLAN-") for row in parsed) == 8
    assert sum(row["Job ID"].startswith("DEMO-UNREL-") for row in parsed) == 16
    assert sum(row["Job ID"].startswith("DEMO-NOISE-") for row in parsed) == 32
    for index in range(1, 9):
        maintenance_prior = by_id[f"DEMO-MAINT-{index:02d}-A"]
        maintenance_followup = by_id[f"DEMO-MAINT-{index:02d}-B"]
        assert (
            date.fromisoformat(maintenance_followup["Date"])
            - date.fromisoformat(maintenance_prior["Date"])
        ).days <= 30

        unrelated_prior = by_id[f"DEMO-UNREL-{index:02d}-A"]
        unrelated_followup = by_id[f"DEMO-UNREL-{index:02d}-B"]
        assert unrelated_prior["Customer ID"] == unrelated_followup["Customer ID"]
        assert unrelated_prior["Location ID"] != unrelated_followup["Location ID"]
        assert unrelated_prior["Technician"] != unrelated_followup["Technician"]


def test_demo_manifest_labels_every_planted_pair() -> None:
    manifest_path = Path(__file__).parents[2] / "seeds/data/hvac_demo_expectations.json"
    manifest = json.loads(manifest_path.read_text())
    pairs = manifest["pairs"]
    fixture_ids = {row["Job ID"] for row in demo_rows()}
    labelled_ids = {external_id for pair in pairs for external_id in pair["external_job_ids"]}
    counts = manifest["expected_counts"]

    assert manifest["fixture_version"] == FIXTURE_VERSION
    assert len(pairs) == 32
    assert len(labelled_ids) == 64
    assert labelled_ids <= fixture_ids
    assert sum(pair["label"] == "callback" for pair in pairs) == counts["callback_pairs"]
    assert (
        sum(pair["label"] == "scheduled_maintenance" for pair in pairs)
        == counts["scheduled_maintenance_pairs"]
    )
    assert (
        sum(pair["label"] == "planned_multivisit" for pair in pairs)
        == counts["planned_multivisit_pairs"]
    )
    assert sum(pair["label"] == "unrelated" for pair in pairs) == counts["unrelated_pairs"]
