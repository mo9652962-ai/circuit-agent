"""Tests for IPC-7525 stencil aperture ratios, J-STD-020 fiducial layout, and ERC rules 23-24."""

import json

from client.erc import run_erc
from client.fiducial_optimizer import calculate_fiducial_layout
from client.mcp_server import handle_tool_call
from client.stencil_aperture import calculate_stencil_aperture_ratios


def test_stencil_aperture_compliant_rect():
    """Verify 0.5x0.25mm rect on 100μm foil: AR = 0.5*0.25 / (1.5*0.1) ≈ 0.83 (pass)."""
    rep = calculate_stencil_aperture_ratios(
        apertures=[{"ref": "R1", "shape": "rect", "width_mm": 0.5, "length_mm": 0.25}],
        foil_thickness_um=100.0,
    )
    c = rep.checks[0]
    assert c.area_ratio == 0.833
    assert c.aspect_ratio == 2.5  # smallest dimension 0.25mm / 0.1mm foil
    assert c.is_compliant is True
    assert rep.deficient_count == 0


def test_stencil_aperture_deficient_fine_pitch():
    """Verify ultra-fine aperture (0.12mm wide, 100μm foil): AR < 0.66 (fail)."""
    rep = calculate_stencil_aperture_ratios(
        apertures=[
            {"ref": "U1.PAD", "shape": "rect", "width_mm": 0.12, "length_mm": 0.6},
            {"ref": "C1", "shape": "rect", "width_mm": 0.5, "length_mm": 0.25},
        ],
        foil_thickness_um=100.0,
    )
    # 0.12x0.6: AR = 0.072 / (1.44*0.1) = 0.5 (fail), aspect = 1.2 (fail)
    assert rep.deficient_count == 1
    assert rep.deficient_refs == ["U1.PAD"]
    assert rep.checks[1].is_compliant is True


def test_stencil_aperture_circle():
    """Verify circular aperture geometry (BGA daisy-chain window)."""
    rep = calculate_stencil_aperture_ratios(
        apertures=[{"ref": "B1.A1", "shape": "circle", "width_mm": 0.3}],
        foil_thickness_um=100.0,
    )
    c = rep.checks[0]
    # Area = π*(0.15)^2 = 0.0707, wall = π*0.3*0.1 = 0.0942 -> AR ≈ 0.75
    assert 0.70 <= c.area_ratio <= 0.80
    assert c.is_compliant is True


def test_fiducial_layout_asymmetric_l_shape():
    """Verify 3 global fiducials in asymmetric L-shape with proper edge clearance."""
    rep = calculate_fiducial_layout(board_width_mm=70.0, board_height_mm=50.0)
    assert rep.global_fiducial_count == 3
    assert rep.is_asymmetric is True
    assert len(rep.fiducials) == 3

    pts = {(f.x_mm, f.y_mm) for f in rep.fiducials}
    # TR quadrant intentionally empty
    assert (65.0, 45.0) not in pts
    assert (5.0, 5.0) in pts
    assert rep.coverage_pct >= 70.0


def test_fiducial_layout_local_for_fine_pitch():
    """Verify local fiducials generated for pitch <= 0.5mm components."""
    rep = calculate_fiducial_layout(
        board_width_mm=80.0,
        board_height_mm=60.0,
        fine_pitch_components=[
            {"ref": "U1", "pitch_mm": 0.4, "x_mm": 40.0, "y_mm": 30.0, "half_diagonal_mm": 3.5, "has_local_fiducials": False},
            {"ref": "U2", "pitch_mm": 0.8, "x_mm": 60.0, "y_mm": 30.0},
        ],
    )
    assert rep.local_fiducial_count == 2
    local = [f for f in rep.fiducials if f.fiducial_type == "local"]
    assert len(local) == 2
    assert all(f.owner == "U1" for f in local)
    assert rep.fine_pitch_refs_without_local == ["U1"]


def test_erc_rules_23_and_24():
    """Verify ERC rules 23 (stencil area ratio) and 24 (fiducial ambiguity)."""
    # Rule 23: stencil area ratio below 0.66
    connections = [
        {"net": "/NET_PASTE", "points": ["U1.1"], "properties": {"stencil_area_ratio": 0.52}},
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "STENCIL_APERTURE_RATIO_DEFICIENT" in codes

    # Rule 24: fewer than 3 global fiducials
    modules = {"__meta__": {"global_fiducial_count": 2}, "U1": {"kind": "MCU"}}
    issues_24 = run_erc(modules, [{"net": "/GND", "points": ["U1.GND"]}])
    codes_24 = [i["code"] for i in issues_24]
    assert "FIDUCIAL_LAYOUT_AMBIGUOUS" in codes_24


def test_mcp_server_stencil_and_fiducial_tools():
    """Verify MCP server handles calculate_stencil_aperture_ratios and calculate_fiducial_layout."""
    res_st = handle_tool_call(
        "calculate_stencil_aperture_ratios",
        {"apertures": [{"ref": "C1", "shape": "rect", "width_mm": 0.5, "length_mm": 0.25}]},
    )
    assert not res_st.get("isError")
    data_st = json.loads(res_st["content"][0]["text"])
    assert data_st["total_apertures"] == 1

    res_fid = handle_tool_call(
        "calculate_fiducial_layout",
        {
            "board_width_mm": 60.0,
            "board_height_mm": 40.0,
            "fine_pitch_components": [{"ref": "U1", "pitch_mm": 0.4, "x_mm": 30.0, "y_mm": 20.0}],
        },
    )
    assert not res_fid.get("isError")
    data_fid = json.loads(res_fid["content"][0]["text"])
    assert data_fid["global_fiducial_count"] == 3
    assert len(data_fid["fiducials"]) == 5
