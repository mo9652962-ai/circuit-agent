"""Unit tests for Parametric Hardware Equations and Manufacturing/EDA Export Engine."""

from __future__ import annotations

import csv

import pytest

from client.export_engine import (
    export_jlcpcb_bom,
    export_jlcpcb_cpl,
    export_kicad_netlist,
    get_cpl_rotation_offset,
    render_ascii_topology,
)
from client.parametric_equations import (
    calculate_i2c_pullup,
    calculate_ldo_thermal,
    calculate_rc_filter,
    generate_standard_series,
    snap_to_e_series,
    solve_resistor_divider,
)
from client.synthesizer import synthesize_from_prompt

# --------------------------------------------------------------------------- #
# 1. Parametric Equations Tests
# --------------------------------------------------------------------------- #

class TestParametricEquations:
    def test_standard_e_series_snapping(self):
        assert snap_to_e_series(9980.0, "E96") == 10000.0
        assert snap_to_e_series(4690.0, "E24") == 4700.0
        assert snap_to_e_series(3.29, "E24") == 3.3

        e96_list = generate_standard_series("E96", 100.0, 976.0)
        assert len(e96_list) == 96
        assert 100.0 in e96_list
        assert 976.0 in e96_list

    def test_solve_resistor_divider_5v_to_3v3(self):
        # 5V in, 3.3V out
        res = solve_resistor_divider(v_in=5.0, v_out_target=3.3, max_quiescent_current_ma=1.0)
        assert res.v_out_actual == pytest.approx(3.3, rel=0.01)
        assert res.ratio_error_pct < 1.0  # < 1% error
        assert res.quiescent_current_ma <= 1.0
        assert res.r1_ohm > 0
        assert res.r2_ohm > 0
        # Check ohm's law: Vout = Vin * R2 / (R1 + R2)
        calc_v = res.v_in * (res.r2_ohm / (res.r1_ohm + res.r2_ohm))
        assert res.v_out_actual == pytest.approx(calc_v, abs=0.001)

    def test_ldo_thermal_safe_vs_overheating(self):
        # 5V -> 3.3V at 100mA in SOT-223: Pd = 0.17W, should be very safe
        safe = calculate_ldo_thermal(v_in=5.0, v_out=3.3, i_load_a=0.1, package="SOT-223", ambient_temp_c=25.0)
        assert safe.is_safe is True
        assert safe.junction_temp_c < 45.0
        assert safe.efficiency_pct > 60.0

        # 24V -> 3.3V at 800mA in SOT-23: Pd = ~16.5W, massive overheat risk!
        hot = calculate_ldo_thermal(v_in=24.0, v_out=3.3, i_load_a=0.8, package="SOT-23", ambient_temp_c=25.0)
        assert hot.is_safe is False
        assert hot.junction_temp_c > 125.0
        assert "CRITICAL OVERHEATING RISK" in hot.recommendation

    def test_i2c_pullup_standard_and_fast_mode(self):
        # 3.3V bus, 100pF load in fast mode (400kHz)
        i2c_fast = calculate_i2c_pullup(v_cc=3.3, bus_capacitance_pf=100.0, mode="fast")
        assert i2c_fast.min_resistance_ohm == pytest.approx(966.7, abs=1.0)
        assert i2c_fast.max_resistance_ohm == pytest.approx(3540.6, abs=1.0)
        assert 1000.0 <= i2c_fast.recommended_standard_ohm <= 3300.0
        # Typical engineering choice is 2.2k or 2.7k
        assert i2c_fast.recommended_standard_ohm in (1800.0, 2000.0, 2200.0, 2400.0, 2700.0)

    def test_rc_filter_solver(self):
        # 10k ohm + 100nF -> fc = 1 / (2*pi*10k*100n) = ~159.15 Hz
        res = calculate_rc_filter(r_ohm=10000.0, c_f=100e-9)
        assert res.cutoff_freq_hz == pytest.approx(159.15, abs=0.5)

        # Invert: solve R for 1kHz and 10nF
        res_r = calculate_rc_filter(cutoff_freq_hz=1000.0, c_f=10e-9)
        assert res_r.resistance_ohm == pytest.approx(15915.5, abs=1.0)


# --------------------------------------------------------------------------- #
# 2. Manufacturing & EDA Export Engine Tests
# --------------------------------------------------------------------------- #

class TestExportEngine:
    @pytest.fixture
    def sample_hardware_project(self):
        return synthesize_from_prompt("工业级 STM32F103 RS485 采集卡，带 Type-C、AHT20 和 TVS 防护")

    def test_export_kicad_netlist(self, sample_hardware_project):
        kicad_net = export_kicad_netlist(sample_hardware_project, title="Test_STM32_Board")
        assert kicad_net.startswith('(export (version "E")')
        assert '(source "Test_STM32_Board.kicad_sch")' in kicad_net
        assert "(components" in kicad_net
        assert "(nets" in kicad_net

        # Parentheses must be strictly balanced
        assert kicad_net.count("(") == kicad_net.count(")")

        # Verify key parts are declared
        assert 'comp (ref "U_MCU1")' in kicad_net or 'comp (ref "U_485")' in kicad_net
        assert 'field (name "LCSC")' in kicad_net

    def test_export_jlcpcb_bom_grouping(self, sample_hardware_project):
        bom_csv = export_jlcpcb_bom(sample_hardware_project)
        reader = list(csv.DictReader(bom_csv.splitlines()))

        assert len(reader) > 5
        headers = list(reader[0].keys())
        assert headers == ["Comment", "Designator", "Footprint", "LCSC Part Number", "JLCPCB Part Class", "Quantity"]

        # Check grouping: passives with same value should be aggregated
        for row in reader:
            qty = int(row["Quantity"])
            des_count = len(row["Designator"].split(","))
            assert qty == des_count
            assert row["JLCPCB Part Class"] in ("Basic Part", "Extended Part")

    def test_export_jlcpcb_cpl_rotations(self, sample_hardware_project):
        cpl_csv = export_jlcpcb_cpl(sample_hardware_project)
        reader = list(csv.DictReader(cpl_csv.splitlines()))

        assert len(reader) > 5
        headers = list(reader[0].keys())
        assert headers == ["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Val", "Package"]

        # Verify rotation corrections work for QFN/SOT/Diode
        assert get_cpl_rotation_offset("QFN-24") == 270.0
        assert get_cpl_rotation_offset("SOT-23") == 180.0
        assert get_cpl_rotation_offset("0603") == 0.0

    def test_render_ascii_topology(self, sample_hardware_project):
        diag = render_ascii_topology(sample_hardware_project)
        assert "SYSTEM ARCHITECTURE TOPOLOGY" in diag
        assert "Power Domain Rails" in diag
        assert "STM32F103C8T6" in diag
        assert "Total Components:" in diag
