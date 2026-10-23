"""End-to-end production-readiness gate.

The gate exists so a CI job or a contract manufacturer gets one verdict instead of
reading five reports and guessing. These tests hold it to that: it must say yes
only when the package is genuinely buildable, and it must name what blocks it
when it says no.
"""

from __future__ import annotations

import json
from functools import cache

from client.mcp_server import handle_tool_call

PROMPT = "ESP32-C3 环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键"


@cache
def _gate_cached(prompt: str, bw: float, bh: float) -> str:
    """Run the gate once per distinct board.

    A gate call is a full synthesize -> place -> route -> export -> validate pass
    and takes minutes. The assertions below ask different questions about the same
    board, so running it per test would multiply the CI wall time for no extra
    coverage. ``job_name`` is deliberately not part of the key: it only labels the
    manifest, and including it re-ran the whole pipeline once per label.
    """
    res = handle_tool_call(
        "gate_production_readiness",
        {"prompt": prompt, "board_width_mm": bw, "board_height_mm": bh, "job_name": "GATE"},
    )
    assert not res.get("isError"), res["content"][0]["text"]
    return res["content"][0]["text"]


def _gate(prompt: str = PROMPT, bw: float = 70.0, bh: float = 50.0) -> dict:
    return json.loads(_gate_cached(prompt, bw, bh))


class TestGateVerdict:
    def test_a_complete_design_is_production_ready(self):
        d = _gate()
        assert d["production_ready"] is True, f"blocked by {d['blocking_defects']}"
        assert d["package_complete"] is True
        assert d["routed"] is True
        assert d["blocking_defects"] == []

    def test_the_bundle_carries_every_deliverable_the_fab_and_assembly_need(self):
        d = _gate()
        # 9 fab layers + BOM + CPL. A board without the last two cannot be ordered
        # populated, so a gate that counted only Gerbers would pass an unusable job.
        assert d["layer_count"] == 11, f"got {d['layer_count']} artifacts"

    def test_the_manifest_lists_the_stencil_and_the_assembly_files(self):
        d = _gate()
        names = {c["artifact_name"] for c in d["manifest"]["checks"]}
        assert "board-F_Paste.gtp" in names
        assert "bom.csv" in names
        assert "cpl.csv" in names

    def test_no_artifact_is_reported_missing(self):
        d = _gate()
        missing = [c["artifact_name"] for c in d["manifest"]["checks"] if c["status"] != "PASS"]
        assert missing == [], f"gate passed with these artifacts not PASS: {missing}"


class TestGateRefusesBadInput:
    def test_empty_prompt_is_an_error_not_an_empty_board(self):
        res = handle_tool_call("gate_production_readiness", {"prompt": "   "})
        assert res.get("isError") is True
        assert "prompt" in res["content"][0]["text"].lower()

    def test_missing_prompt_is_an_error(self):
        res = handle_tool_call("gate_production_readiness", {})
        assert res.get("isError") is True

    def test_the_gate_is_registered_in_the_schema(self):
        from client.mcp_schema import AVAILABLE_TOOLS

        names = {t["name"] for t in AVAILABLE_TOOLS}
        assert "gate_production_readiness" in names

    def test_the_schema_declares_prompt_as_required(self):
        from client.mcp_schema import AVAILABLE_TOOLS

        tool = next(t for t in AVAILABLE_TOOLS if t["name"] == "gate_production_readiness")
        assert tool["inputSchema"]["required"] == ["prompt"]
        assert "board_width_mm" in tool["inputSchema"]["properties"]


class TestGateHonoursBoardSize:
    def test_a_custom_outline_is_carried_into_the_cpl(self):
        """CPL coordinates must sit inside the board the fab receives.

        The exporter used to hardcode a 70 x 50 outline, so on any other board
        every placement row pointed outside the edge cuts.
        """
        from client.export_engine import export_jlcpcb_cpl
        from client.synthesizer import synthesize_from_prompt

        spec = synthesize_from_prompt(PROMPT)
        w, h = 120.0, 80.0
        cpl = export_jlcpcb_cpl(spec, board_width_mm=w, board_height_mm=h)
        xs, ys = [], []
        for line in cpl.splitlines()[1:]:
            cells = line.split(",")
            if len(cells) >= 3:
                # CPL coordinates carry a unit suffix: "52.000mm".
                xs.append(float(cells[1].replace("mm", "").strip()))
                ys.append(float(cells[2].replace("mm", "").strip()))
        assert xs and ys
        assert max(xs) <= w, f"a part sits at x={max(xs)} on a {w} mm board"
        assert max(ys) <= h, f"a part sits at y={max(ys)} on a {h} mm board"

    def test_the_gate_passes_on_a_larger_board(self):
        d = _gate(bw=120.0, bh=80.0)
        assert d["production_ready"] is True, f"blocked by {d['blocking_defects']}"
