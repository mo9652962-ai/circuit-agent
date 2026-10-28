"""Unit tests for SMT pick-and-place nozzle selector, trace fusing current solver, and ERC rules 60-61."""

from __future__ import annotations

import json

from client.erc import run_erc
from client.mcp_schema import AVAILABLE_TOOLS
from client.mcp_server import handle_tool_call
from client.smt_nozzle_selector import audit_smt_nozzle_selection
from client.trace_fusing_current import calculate_trace_fusing_current


def test_audit_smt_nozzle_selection_auto_success():
    """测试常规 0603 电阻自动吸嘴匹配合格。"""
    res = audit_smt_nozzle_selection(
        component_designator="R1",
        package_type="0603",
        vendor_preference="Juki",
    )
    assert res.is_suitable is True
    assert res.nozzle_collision_risk is False
    assert res.vacuum_leakage_risk is False
    assert res.dynamic_safety_factor >= 1.50
    assert res.nozzle_outer_diameter_mm < res.component_width_mm
    assert res.nozzle_inner_diameter_mm < res.component_width_mm
    assert any("EIA-481" in std for std in res.standards_cited)


def test_audit_smt_nozzle_selection_collision_risk():
    """测试吸嘴外径过大碰撞风险。"""
    # 0402 宽 0.50mm，选 Juki-504 (OD=1.50mm) 严重超出
    res = audit_smt_nozzle_selection(
        component_designator="C3",
        package_type="0402",
        specified_nozzle_model="Juki-504",
    )
    assert res.is_suitable is False
    assert res.nozzle_collision_risk is True
    assert any("大于等于器件最小平宽" in v for v in res.violations)


def test_audit_smt_nozzle_selection_vacuum_leakage():
    """测试吸嘴内径过大真空泄漏风险。"""
    # 0603 宽 0.80mm，选 Juki-504 (ID=0.80mm) 内孔越界
    res = audit_smt_nozzle_selection(
        component_designator="R10",
        package_type="0603",
        specified_nozzle_model="Juki-504",
    )
    assert res.is_suitable is False
    assert res.vacuum_leakage_risk is True
    assert any("真空泄漏" in v or "封装倒角" in v for v in res.violations)


def test_calculate_trace_fusing_current_safe():
    """测试正常走线短时故障脉冲热安全。"""
    res = calculate_trace_fusing_current(
        trace_width_mm=0.80,
        copper_thickness_um=35.0,
        trace_layer="external",
        fault_current_a=8.0,
        pulse_duration_s=0.05,
        upstream_fuse_i2t_a2s=0.5,
    )
    assert res.is_safe is True
    assert res.trace_burnout_risk is False
    assert res.coordination_margin_ok is True
    assert res.action_integral_i2t_a2s > 0
    assert any("IPC-2152" in std for std in res.standards_cited)


def test_calculate_trace_fusing_current_delamination_burnout():
    """测试细走线大短路电流突破 FR-4 爆板起泡碳化极限。"""
    res = calculate_trace_fusing_current(
        trace_width_mm=0.15,
        copper_thickness_um=35.0,
        trace_layer="internal",
        fault_current_a=35.0,
        pulse_duration_s=0.10,
    )
    assert res.is_safe is False
    assert res.trace_burnout_risk is True
    assert res.fault_current_a >= res.fr4_delamination_current_a
    assert any("爆板分层起泡阈值" in v for v in res.violations)


def test_calculate_trace_fusing_coordination_failure():
    """测试 PCB 走线耐受能量低于上游保险丝熔断能量（走线充当牺牲熔丝）。"""
    res = calculate_trace_fusing_current(
        trace_width_mm=0.30,
        copper_thickness_um=35.0,
        trace_layer="external",
        fault_current_a=10.0,
        pulse_duration_s=0.05,
        upstream_fuse_i2t_a2s=15.0,  # 保险丝熔断能量远超走线
    )
    assert res.is_safe is False
    assert res.coordination_margin_ok is False
    assert any("配合裕量不足" in v for v in res.violations)


def test_mcp_tools_registration_and_execution():
    """测试 MCP 工具注册总数达 84 个，且新工具可正常执行调用。"""
    tool_names = [t["name"] for t in AVAILABLE_TOOLS]
    assert "audit_smt_nozzle_selection" in tool_names
    assert "calculate_trace_fusing_current" in tool_names
    assert len(AVAILABLE_TOOLS) >= 84

    # 调用 audit_smt_nozzle_selection
    res_noz = handle_tool_call(
        "audit_smt_nozzle_selection",
        {"component_designator": "U1", "package_type": "QFN-32", "vendor_preference": "Yamaha"},
    )
    assert "isError" not in res_noz
    data_noz = json.loads(res_noz["content"][0]["text"])
    assert data_noz["component_designator"] == "U1"
    assert data_noz["package_type"] == "QFN-32"
    assert data_noz["is_suitable"] is True

    # 调用 calculate_trace_fusing_current
    res_fuse = handle_tool_call(
        "calculate_trace_fusing_current",
        {"trace_width_mm": 0.50, "copper_thickness_um": 35.0, "fault_current_a": 12.0},
    )
    assert "isError" not in res_fuse
    data_fuse = json.loads(res_fuse["content"][0]["text"])
    assert data_fuse["trace_width_mm"] == 0.50
    assert "action_integral_i2t_a2s" in data_fuse


def test_erc_rules_60_and_61():
    """测试 ERC 规则 60 (SMT_PICK_AND_PLACE_NOZZLE_MISMATCH) 与 61 (CONDUCTOR_FUSING_BURNOUT_RISK)。"""
    modules = {
        "U1": {"type": "MCU", "package": "0402", "specified_nozzle": "Juki-506"},  # 碰撞冲突
        "__meta__": {
            "trace_fusing_audit": {
                "trace_width_mm": 0.10,
                "copper_thickness_um": 35.0,
                "fault_current_a": 30.0,
                "pulse_duration_s": 0.20,
            }
        },
    }
    connections = [
        {"net": "GND", "points": ["U1.1", "U1.2"]},
        {"net": "VCC", "points": ["U1.3", "U1.4"]},
    ]
    issues = run_erc(modules, connections)
    rule_ids = [i["code"] for i in issues]
    assert "SMT_PICK_AND_PLACE_NOZZLE_MISMATCH" in rule_ids
    assert "CONDUCTOR_FUSING_BURNOUT_RISK" in rule_ids
