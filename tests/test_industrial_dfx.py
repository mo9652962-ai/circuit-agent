"""Unit tests for Industrial DFX Engine, IPC-2152/IPC-2221 calculations, and industrial protection blocks."""

from __future__ import annotations

import pytest

from client.circuit_blocks import (
    block_esd_can_tvs,
    block_esd_rs485_tvs,
    block_esd_usb_tvs,
    block_fiducial_marks,
    block_power_pi_filter,
    block_reverse_polarity_protection,
    block_testpoint_matrix,
)
from client.industrial_dfx import (
    audit_industrial_dfx,
    calculate_ipc2152,
    get_ipc2221_clearance,
    solve_trace_width_ipc2152,
)
from client.synthesizer import synthesize_from_prompt

# --------------------------------------------------------------------------- #
# 1. IPC-2152 Conductor Current Carrying Tests
# --------------------------------------------------------------------------- #

class TestIPC2152Calculations:
    def test_calculate_trace_current_external(self):
        # 0.254mm (10 mil), 1oz copper, 20°C rise
        res = calculate_ipc2152(trace_width_mm=0.254, copper_oz=1.0, temp_rise_c=20.0, layer="external")
        assert res.trace_width_mil == pytest.approx(10.0, abs=0.2)
        assert 1.0 <= res.max_current_a <= 1.5
        assert res.resistance_mohm_per_m > 0
        assert res.power_loss_w_per_m > 0
        assert res.layer == "external"

    def test_internal_layer_derating(self):
        # Internal layers have worse heat dissipation, so max current must be lower than external
        res_ext = calculate_ipc2152(trace_width_mm=0.5, copper_oz=1.0, temp_rise_c=20.0, layer="external")
        res_int = calculate_ipc2152(trace_width_mm=0.5, copper_oz=1.0, temp_rise_c=20.0, layer="internal")
        assert res_int.max_current_a < res_ext.max_current_a
        assert res_int.max_current_a == pytest.approx(res_ext.max_current_a * 0.5, rel=0.1)

    def test_solve_trace_width_inverts_calculation(self):
        # Solve width for 2.5 Amps, then verify calculated current matches ~2.5A
        res_solve = solve_trace_width_ipc2152(target_current_a=2.5, copper_oz=1.0, temp_rise_c=20.0, layer="external")
        assert res_solve.trace_width_mm > 0.5
        res_verify = calculate_ipc2152(res_solve.trace_width_mm, copper_oz=1.0, temp_rise_c=20.0, layer="external")
        assert res_verify.max_current_a == pytest.approx(2.5, abs=0.05)

    def test_invalid_parameters_raise(self):
        with pytest.raises(ValueError, match="trace_width_mm must be positive"):
            calculate_ipc2152(trace_width_mm=-0.1)
        with pytest.raises(ValueError, match="target_current_a must be positive"):
            solve_trace_width_ipc2152(target_current_a=0.0)


# --------------------------------------------------------------------------- #
# 2. IPC-2221 Voltage Clearance & Creepage Tests
# --------------------------------------------------------------------------- #

class TestIPC2221Clearance:
    def test_low_voltage_clearance(self):
        # <= 15V (e.g. 3.3V, 5V, 12V)
        assert get_ipc2221_clearance(5.0, layer="external_coated") == 0.05
        assert get_ipc2221_clearance(12.0, layer="external_uncoated") == 0.10

    def test_industrial_24v_clearance(self):
        # 24V industrial supply
        assert get_ipc2221_clearance(24.0, layer="external_coated") == 0.05

    def test_high_voltage_clearance(self):
        # 220V mains peak (~310V)
        clr = get_ipc2221_clearance(310.0, layer="external_coated")
        assert clr >= 0.40
        clr_uncoated = get_ipc2221_clearance(310.0, layer="external_uncoated")
        assert clr_uncoated >= 1.25


# --------------------------------------------------------------------------- #
# 3. Industrial Protection CircuitBlocks Tests
# --------------------------------------------------------------------------- #

class TestIndustrialCircuitBlocks:
    def test_block_esd_usb_tvs(self):
        blk = block_esd_usb_tvs()
        assert blk.name == "ESD_TVS_USB"
        assert len(blk.components) == 1
        comp = blk.components[0]
        assert comp.value == "USBLC6-2SC6"
        assert comp.package == "SOT-23-6"
        assert comp.lcsc == "C7519"
        assert "/USB_DP" in blk.nets
        assert "/USB_DM" in blk.nets
        assert "/VBUS" in blk.nets
        assert "/GND" in blk.nets

    def test_block_esd_rs485_tvs(self):
        blk = block_esd_rs485_tvs()
        assert blk.name == "ESD_TVS_RS485"
        comp = blk.components[0]
        assert comp.value == "SM712"
        assert comp.package == "SOT-23"
        assert comp.lcsc == "C19001"
        assert "/RS485_A" in blk.nets
        assert "/RS485_B" in blk.nets

    def test_block_esd_can_tvs(self):
        blk = block_esd_can_tvs()
        assert blk.name == "ESD_TVS_CAN"
        comp = blk.components[0]
        assert comp.value == "PESD1CAN"
        assert comp.package == "SOT-23"
        assert comp.lcsc == "C2848243"

    def test_block_reverse_polarity_protection(self):
        blk_schottky = block_reverse_polarity_protection(method="schottky")
        assert blk_schottky.name == "Reverse_Polarity_Protection"
        assert blk_schottky.components[0].value == "SS34"

        blk_pmos = block_reverse_polarity_protection(method="pmos")
        refs = [c.ref for c in blk_pmos.components]
        assert "Q_REV1" in refs
        assert "R_REV_G" in refs
        assert "D_REV_Z" in refs

    def test_block_power_pi_filter(self):
        blk = block_power_pi_filter()
        assert blk.name == "Power_Pi_Filter"
        assert len(blk.components) == 4
        bead = next(c for c in blk.components if c.kind == "INDUCTOR")
        assert bead.lcsc == "C1015"

    def test_block_fiducial_marks(self):
        blk = block_fiducial_marks(count=3)
        assert len(blk.components) == 3
        assert blk.components[0].kind == "FIDUCIAL"

    def test_block_testpoint_matrix(self):
        blk = block_testpoint_matrix(["/VBUS", "/+3.3V", "/GND"])
        assert len(blk.components) == 3
        assert all(c.kind == "TESTPOINT" for c in blk.components)


# --------------------------------------------------------------------------- #
# 4. Industrial DFX Audit Engine Tests
# --------------------------------------------------------------------------- #

class TestIndustrialDFXAudit:
    def test_audit_flags_missing_protections(self):
        # Minimal consumer netlist with exposed USB and RS485, but NO TVS or test points
        consumer_netlist = {
            "components": [
                {"ref": "J_USB1", "kind": "CONNECTOR", "value": "USB-C-16P", "package": "USB-C"},
                {"ref": "U_MCU1", "kind": "MCU", "value": "STM32F103C8T6", "package": "LQFP-48"},
                {"ref": "U_485", "kind": "TRANSCEIVER", "value": "SP3485", "package": "SOIC-8"},
            ],
            "connections": [
                {"net": "/USB_DP", "points": ["J_USB1.A6", "U_MCU1.33"]},
                {"net": "/USB_DM", "points": ["J_USB1.A7", "U_MCU1.32"]},
                {"net": "/RS485_A", "points": ["U_485.6"]},
                {"net": "/RS485_B", "points": ["U_485.7"]},
                {"net": "/+3.3V", "points": ["U_MCU1.48", "U_485.8"]},
                {"net": "/GND", "points": ["U_MCU1.47", "U_485.5", "J_USB1.GND"]},
            ],
        }
        report = audit_industrial_dfx(consumer_netlist)
        assert report.passed is False
        rule_ids = [v.rule_id for v in report.violations]
        assert "EMC-01" in rule_ids  # Missing USB TVS
        assert "EMC-02" in rule_ids  # Missing RS485 TVS
        assert "DFT-01" in rule_ids  # Missing Power Test Points
        assert "DFA-01" in rule_ids  # Missing Optical Fiducials

        md = report.to_markdown()
        assert "Industrial DFX & Manufacturing Audit Report" in md
        assert "Overall Verdict" in md

    def test_audit_passes_hardened_industrial_netlist(self):
        # Synthesize an industrial board with TVS, testpoints, and fiducials
        design = synthesize_from_prompt("工业级 STM32F103 RS485 采集卡，带 Type-C、AHT20 和 TVS 防护")
        report = audit_industrial_dfx(design["netlist"])

        assert report.passed is True
        assert report.score >= 85
        assert report.grade in ("A+", "A")
        assert not any(v.severity == "CRITICAL" for v in report.violations)
        assert report.metrics["testpoints_count"] >= 5
        assert report.metrics["fiducials_count"] >= 3
        assert report.metrics["has_usb_tvs"] is True
        assert report.metrics["has_rs485_tvs"] is True
