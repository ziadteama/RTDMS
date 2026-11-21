from __future__ import annotations

import json
from pathlib import Path

from rtdms_pi.incidents.ids import incident_id

CONTRACT = Path(__file__).resolve().parents[3] / "contracts/pi-link"


def test_incident_id_format() -> None:
    # 2024-11-20 15:40:02.400 UTC = 1732117202400
    res = incident_id(1732117202400)
    assert res == "2024-11-20T15-40-02-400Z"

    # Year 2026 epoch: 2026-11-20 15:40:02.400 UTC = 1795189202400
    res_2026 = incident_id(1795189202400)
    assert res_2026 == "2026-11-20T15-40-02-400Z"


def test_incident_id_fixture_comparison() -> None:
    fixture_path = CONTRACT / "fixtures" / "incident_item.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    t_crash = fixture["t_crash"]
    fixture_id = fixture["id"]

    assert incident_id(t_crash) == fixture_id
