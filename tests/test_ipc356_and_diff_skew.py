"""Tests for IPC-D-356A bare board electrical test exporter and differential skew solver."""

from client.differential_skew import solve_differential_pair_skew
from client.erc import erc_allowed, run_erc
from client.ipc_d356_exporter import export_ipc_d356
from client.synthesizer import synthesize_from_prompt


def test_export_ipc_d356_format():
    """Verify IPC-D-356A file structure: P JOB, 317/327 records, 80-column width, 999 EOF."""
    res = synthesize_from_prompt("STM32F103 USB-C LDO CAN")
    ipc_txt = export_ipc_d356(
        res["modules"],
        res["netlist"]["connections"],
        job_name="TEST_BOARD",
        board_width_mm=80.0,
        board_height_mm=60.0,
    )
    lines = ipc_txt.splitlines()
    assert any(l.startswith("P  JOB TEST_BOARD") for l in lines)
    assert any(l.startswith("P  UNITS CUST 0") for l in lines)
    assert any(l.startswith("317") for l in lines)  # Component pin record
    assert any(l.startswith("999") for l in lines)  # End of data record

    # Check 80-column fixed-width constraint on data records
    for line in lines:
        if line.startswith(("317", "327")):
            assert len(line) == 80, f"Record line not 80 chars: {line!r} (len={len(line)})"


def test_solve_differential_pair_skew():
    """Verify differential pair skew solver across USB 2.0 High-Speed and Ethernet."""
    # 1. USB2_HS with small length delta 0.8mm -> skew ~5.3ps <= 10ps limit -> Compliant
    res_pass = solve_differential_pair_skew(0.8, protocol="USB2_HS", dielectric_er=4.2)
    assert res_pass.is_compliant is True
    assert res_pass.delay_skew_ps < 10.0
    assert res_pass.required_tuning_length_mm == 0.0
    assert res_pass.serpentine_bumps_count == 0

    # 2. USB2_HS with excessive length delta 5.0mm -> skew ~33ps > 10ps limit -> Non-compliant
    res_fail = solve_differential_pair_skew(5.0, protocol="USB2_HS", dielectric_er=4.2)
    assert res_fail.is_compliant is False
    assert res_fail.delay_skew_ps > 10.0
    assert res_fail.required_tuning_length_mm > 0.0
    assert res_fail.serpentine_bumps_count >= 1
    assert "serpentine compensation" in res_fail.notes


def test_erc_high_speed_pair_unbalanced():
    """Verify ERC rule 8: HIGH_SPEED_PAIR_UNBALANCED detects unequal differential pin counts."""
    modules = {
        "J_USB": {"kind": "CONNECTOR", "value": "USB-C"},
        "MCU": {"kind": "MCU", "value": "STM32"},
        "TP_EXTRA": {"kind": "TESTPOINT", "value": "TP"},
    }
    # /USB_DP has 3 points (extra test point), /USB_DM has only 2 points -> Unbalanced
    conns_unbalanced = [
        {"net": "/GND", "points": ["J_USB.GND", "MCU.GND"]},
        {"net": "/USB_DP", "points": ["J_USB.DP", "MCU.PA12", "TP_EXTRA.1"]},
        {"net": "/USB_DM", "points": ["J_USB.DM", "MCU.PA11"]},
    ]
    issues = run_erc(modules, conns_unbalanced)
    codes = {i["code"] for i in issues}
    assert "HIGH_SPEED_PAIR_UNBALANCED" in codes
    assert erc_allowed(issues) is True  # Warning does not block

    # Balance by adding matching testpoint to /USB_DM -> Warning eliminated
    conns_balanced = [
        {"net": "/GND", "points": ["J_USB.GND", "MCU.GND"]},
        {"net": "/USB_DP", "points": ["J_USB.DP", "MCU.PA12", "TP_EXTRA.1"]},
        {"net": "/USB_DM", "points": ["J_USB.DM", "MCU.PA11", "TP_EXTRA_2.1"]},
    ]
    modules["TP_EXTRA_2"] = {"kind": "TESTPOINT", "value": "TP"}
    issues2 = run_erc(modules, conns_balanced)
    codes2 = {i["code"] for i in issues2}
    assert "HIGH_SPEED_PAIR_UNBALANCED" not in codes2


def test_mcp_tools_ipc356_and_skew():
    """Verify MCP tools export_ipc_d356 and calculate_differential_skew execute cleanly."""
    from client.mcp_server import handle_tool_call

    # 1. calculate_differential_skew
    out_skew = handle_tool_call(
        "calculate_differential_skew",
        {
            "trace_length_delta_mm": 2.5,
            "protocol": "USB2_HS",
            "dielectric_er": 4.2,
        },
    )
    assert "isError" not in out_skew
    import json

    data_skew = json.loads(out_skew["content"][0]["text"])
    assert "delay_skew_ps" in data_skew
    assert "is_compliant" in data_skew

    # 2. export_ipc_d356
    res = synthesize_from_prompt("STM32F103 CAN")
    out_ipc = handle_tool_call(
        "export_ipc_d356",
        {
            "modules": res["modules"],
            "netlist": res["netlist"],
            "job_name": "AUTO_TEST_JOB",
        },
    )
    assert "isError" not in out_ipc
    ipc_content = out_ipc["content"][0]["text"]
    assert "P  JOB AUTO_TEST_JOB" in ipc_content
    assert "317" in ipc_content
    assert "999" in ipc_content
