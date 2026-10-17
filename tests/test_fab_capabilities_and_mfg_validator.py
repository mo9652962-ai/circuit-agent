"""Tests for fab capabilities checker, manufacturing package validator, and ERC rules 40-41."""

from client.erc import run_erc
from client.fab_capabilities import FAB_PROFILES, audit_fab_capabilities
from client.mcp_server import handle_tool_call
from client.mfg_validator import validate_manufacturing_package


def test_audit_fab_capabilities_standard_pass():
    """Verify standard conservative design passes JLCPCB standard tier."""
    rep = audit_fab_capabilities(
        fab_id="jlcpcb_standard",
        min_trace_width_mm=0.150,
        min_trace_clearance_mm=0.150,
        min_via_drill_mm=0.300,
        min_via_pad_mm=0.600,
    )
    assert rep.is_compliant is True
    assert rep.violations_count == 0


def test_audit_fab_capabilities_violations_detected():
    """Verify trace width < 0.09mm triggers violation on JLCPCB standard tier."""
    rep = audit_fab_capabilities(
        fab_id="jlcpcb_standard",
        min_trace_width_mm=0.060,  # below 0.090mm
        min_trace_clearance_mm=0.070,
        min_via_drill_mm=0.100,  # below 0.200mm
    )
    assert rep.is_compliant is False
    assert rep.violations_count >= 3
    params = [v.parameter for v in rep.violations]
    assert "trace_width" in params
    assert "via_drill" in params
    assert len(rep.recommendations) > 0


def test_fab_profiles_coverage():
    """Verify fab profiles dictionary includes major fab houses."""
    assert "jlcpcb_standard" in FAB_PROFILES
    assert "jlcpcb_advanced" in FAB_PROFILES
    assert "pcbway_standard" in FAB_PROFILES
    assert "oshpark_standard" in FAB_PROFILES


def test_validate_manufacturing_package_complete():
    """Verify complete 5-layer Gerber + drill + BOM + CPL bundle passes with SHA256 manifest."""
    bundle = {
        "board-Edge_Cuts.gm1": "G04 Edge cuts*",
        "board-F_Cu.gtl": "G04 Top copper*",
        "board-B_Cu.gbl": "G04 Bottom copper*",
        "board-F_Mask.gts": "G04 Top mask*",
        "board-B_Mask.gbs": "G04 Bottom mask*",
        "board.drl": "M48\nT01C0.3\n%",
        "bom.csv": "Comment,Designator,Footprint\n100nF,C1,0402\nESP32,U1,QFN",
        "cpl.csv": "Designator,Mid X,Mid Y,Layer,Rotation\nC1,10,20,Top,0\nU1,30,20,Top,0",
    }
    modules = {"C1": {"kind": "CAPACITOR"}, "U1": {"kind": "MCU"}}
    rep = validate_manufacturing_package(bundle, modules=modules, job_name="TEST_RUN")

    assert rep.is_package_complete is True
    assert rep.missing_artifacts_count == 0
    assert rep.bom_cpl_consistent is True
    assert "board-Edge_Cuts.gm1" in rep.sha256_manifest
    assert len(rep.errors) == 0


def test_validate_manufacturing_package_missing_file():
    """Verify missing drill or Gerber flags incomplete package."""
    bundle = {
        "board-Edge_Cuts.gm1": "content",
    }
    rep = validate_manufacturing_package(bundle)
    assert rep.is_package_complete is False
    assert rep.missing_artifacts_count > 0
    assert any("board.drl" in e for e in rep.errors)


def test_erc_rules_40_and_41():
    """Verify ERC rules 40 (fab capability limit) and 41 (silkscreen over pad)."""
    # Rule 40: trace width 0.05mm violates fab capability
    connections = [
        {
            "net": "/ULTRA_THIN",
            "points": ["U1.1"],
            "properties": {"trace_width_mm": 0.05, "target_fab_id": "jlcpcb_standard"},
        }
    ]
    issues_40 = run_erc({}, connections)
    codes_40 = [i["code"] for i in issues_40]
    assert "FAB_CAPABILITY_LIMIT_EXCEEDED" in codes_40

    # Rule 41: silkscreen over exposed pad
    modules = {
        "U1": {"kind": "IC", "silkscreen_over_pad": True},
        "C1": {"kind": "CAPACITOR", "silkscreen_over_pad": False},
    }
    issues_41 = run_erc(modules, [{"net": "/GND", "points": ["U1.GND"]}])
    codes_41 = [i["code"] for i in issues_41]
    assert "SILKSCREEN_OVER_EXPOSED_COPPER" in codes_41


def test_mcp_server_fab_and_validator_tools():
    """Verify MCP server handles audit_fab_capabilities and validate_manufacturing_package."""
    res_fab = handle_tool_call(
        "audit_fab_capabilities",
        {"fab_id": "jlcpcb_standard", "min_trace_width_mm": 0.15},
    )
    assert not res_fab.get("isError")
    assert '"is_compliant": true' in res_fab["content"][0]["text"]

    res_val = handle_tool_call(
        "validate_manufacturing_package",
        {
            "artifacts_dict": {
                "board-Edge_Cuts.gm1": "content",
                "board-F_Cu.gtl": "content",
                "board-B_Cu.gbl": "content",
                "board-F_Mask.gts": "content",
                "board-B_Mask.gbs": "content",
                "board.drl": "content",
                "bom.csv": "Designator\nC1",
                "cpl.csv": "Designator\nC1",
            }
        },
    )
    assert not res_val.get("isError")
    assert '"is_package_complete": true' in res_val["content"][0]["text"]
