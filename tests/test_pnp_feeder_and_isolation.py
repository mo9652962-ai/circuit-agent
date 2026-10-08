"""Tests for SMT pick-and-place feeder matrix, OpenPnP job exporter, and ERC rules 13 & 14."""

import json

from client.erc import erc_allowed, run_erc
from client.pnp_machine_exporter import export_openpnp_job_csv
from client.smt_feeder_matrix import (
    assign_smt_feeder_and_nozzle,
    generate_smt_feeder_matrix,
)
from client.synthesizer import synthesize_from_prompt


def test_assign_smt_feeder_and_nozzle():
    """Verify EIA-481 tape width/pitch and nozzle assignments across key package families."""
    # 0402 -> 8mm tape, 2mm pitch, 502 nozzle
    w, pitch, noz = assign_smt_feeder_and_nozzle("R_0402_1005Metric")
    assert (w, pitch, noz) == (8, 2, "502_CN040")

    # 0603 -> 8mm tape, 4mm pitch, 503 nozzle
    w, pitch, noz = assign_smt_feeder_and_nozzle("C_0603_1608Metric")
    assert (w, pitch, noz) == (8, 4, "503_CN065")

    # SOT-223 -> 12mm tape, 8mm pitch, 504 nozzle
    w, pitch, noz = assign_smt_feeder_and_nozzle("SOT-223")
    assert (w, pitch, noz) == (12, 8, "504_CN100")

    # QFN-48 -> 16mm tape, 12mm pitch, 505 nozzle
    w, pitch, noz = assign_smt_feeder_and_nozzle("QFN-48")
    assert (w, pitch, noz) == (16, 12, "505_CN140")

    # LQFP-48 / RJ45 -> 24mm tape, 16mm pitch, 506 nozzle
    w, pitch, noz = assign_smt_feeder_and_nozzle("LQFP-48_7x7mm_P0.5mm")
    assert (w, pitch, noz) == (24, 16, "506_CN220")


def test_generate_smt_feeder_matrix():
    """Verify feeder slot allocation and optimization report."""
    res = synthesize_from_prompt("STM32F103 USB-C LDO CAN 步进电机 以太网")
    rep = generate_smt_feeder_matrix(res["modules"])

    assert rep.total_slots_used >= 6
    assert 8 in rep.tape_width_breakdown
    assert "503_CN065" in rep.nozzle_distribution
    assert len(rep.recommendations) >= 2


def test_export_openpnp_job_csv():
    """Verify generated OpenPnP job CSV lines."""
    res = synthesize_from_prompt("ESP32-C3 USB-C LDO")
    csv_txt = export_openpnp_job_csv(res["modules"], board_width_mm=75.0, board_height_mm=55.0)

    lines = csv_txt.splitlines()
    assert lines[0].startswith("# OpenPnP")
    assert any("Slot_01" in l for l in lines)
    # Check CSV columns: val, ref, x, y, rot, side, pkg, nozzle, slot
    data_lines = [l for l in lines if not l.startswith("#")]
    assert len(data_lines) == len(res["modules"])
    fields = data_lines[0].split(",")
    assert len(fields) == 9
    assert fields[5] == "Top"  # Default placed side


def test_erc_rules_13_and_14():
    """Verify ERC rule 13 (tape pitch mismatch) and rule 14 (high-voltage isolation boundary breach)."""
    # 1. Rule 13: SMT_TAPE_FEEDER_PITCH_MISMATCH
    bad_feeder_modules = {
        "R_BIG": {"kind": "RESISTOR", "value": "100k", "package": "SOIC-8_2MM_PITCH"},
    }
    issues1 = run_erc(bad_feeder_modules, [])
    assert any(i["code"] == "SMT_TAPE_FEEDER_PITCH_MISMATCH" for i in issues1)

    # 2. Rule 14: HIGH_VOLTAGE_ISOLATION_BARRIER_BREACH
    # Connect 24V PLC to 3.3V logic through non-isolated resistor R1
    bad_iso_modules = {
        "R_UNPROTECTED": {"kind": "RESISTOR", "value": "10k"},
    }
    bad_iso_conns = [
        {"net": "/PLC_24V", "points": ["R_UNPROTECTED.1"]},
        {"net": "/+3.3V", "points": ["R_UNPROTECTED.2"]},
        {"net": "/GND", "points": ["R_GND.1", "R_GND.2"]},
    ]
    bad_iso_modules["R_GND"] = {"kind": "RESISTOR", "value": "0R"}
    issues2 = run_erc(bad_iso_modules, bad_iso_conns)
    assert any(i["code"] == "HIGH_VOLTAGE_ISOLATION_BARRIER_BREACH" for i in issues2)
    assert erc_allowed(issues2) is True  # Warning level


def test_mcp_tools_feeder_matrix_and_openpnp():
    """Verify MCP tools calculate_smt_feeder_matrix and export_openpnp_job execute cleanly."""
    from client.mcp_server import handle_tool_call

    res = synthesize_from_prompt("STM32F103 RS485 CAN")

    # 1. calculate_smt_feeder_matrix
    out_fm = handle_tool_call(
        "calculate_smt_feeder_matrix",
        {
            "modules": res["modules"],
        },
    )
    assert "isError" not in out_fm
    data_fm = json.loads(out_fm["content"][0]["text"])
    assert "total_slots_used" in data_fm
    assert "feeders" in data_fm

    # 2. export_openpnp_job
    out_pnp = handle_tool_call(
        "export_openpnp_job",
        {
            "modules": res["modules"],
            "board_width_mm": 80.0,
            "board_height_mm": 60.0,
        },
    )
    assert "isError" not in out_pnp
    pnp_content = out_pnp["content"][0]["text"]
    assert "# OpenPnP" in pnp_content
    assert "Slot_" in pnp_content
