"""Tests for IPC-2152 via current solver, headless fab order budget, and ERC rules 54-55."""

from client.erc import run_erc
from client.fab_order_client import budget_fab_order
from client.mcp_server import handle_tool_call
from client.via_current_solver import solve_via_current_array


def test_via_current_array_sizing():
    """Verify 3A on a 0.3mm/25μm via stitches to a 4-via array."""
    res = solve_via_current_array(current_a=3.0, via_drill_mm=0.30, plating_um=25.0)
    assert res.array_size == 4
    assert res.array_capacity_a >= 3.0
    assert res.meets_requirement is True
    assert res.barrel_area_mil2 > 0
    assert "40% 降额" in res.recommendation or "合规" in res.recommendation


def test_via_current_overload_flags():
    """Verify a 20A rail cannot be met even at the array ceiling."""
    res = solve_via_current_array(current_a=20.0, via_drill_mm=0.30, max_array_size=8)
    assert res.meets_requirement is False
    assert "加宽走线" in res.recommendation


def test_via_current_filled_and_internal_variants():
    """Verify fill+cap credit and internal-layer derating move capacity correctly."""
    plain = solve_via_current_array(current_a=1.0, via_drill_mm=0.30)
    filled = solve_via_current_array(current_a=1.0, via_drill_mm=0.30, is_filled=True)
    internal = solve_via_current_array(current_a=1.0, via_drill_mm=0.30, internal_layer=True)
    assert filled.single_via_capacity_a > plain.single_via_capacity_a  # 1.5× credit
    assert internal.single_via_capacity_a < plain.single_via_capacity_a  # k 0.024 < 0.048


def test_fab_order_budget_cross_vendor():
    """Verify JLCPCB prices below PCBWay on standard specs and manifest digests."""
    budget = budget_fab_order(
        layers=4,
        qty=10,
        board_w_mm=80,
        board_h_mm=60,
        surface_finish="enig",
        include_smt=True,
        smt_parts=120,
        artifacts={"board-F_Cu.gtl": "gerber", "bom.csv": "bom"},
    )
    assert [q.vendor for q in budget.quotes] == ["JLCPCB", "PCBWay"]
    assert budget.recommended_vendor == "JLCPCB"
    assert budget.savings_vs_max_usd > 0
    assert budget.submission_ready is True
    assert budget.quotes[0].manifest_sha256 != "no-artifacts"
    assert set(budget.artifacts) == {"board-F_Cu.gtl", "bom.csv"}


def test_fab_order_budget_no_artifacts_flags():
    """Verify missing artifacts disable submission readiness with a note."""
    budget = budget_fab_order(layers=2, qty=5)
    assert budget.submission_ready is False
    assert any("SHA-256" in n for n in budget.notes)


def test_erc_rule_54_via_barrel_overload():
    """Verify ERC rule 54 fires when via array cannot carry the rail."""
    connections = [
        {
            "net": "/PWR_20A",
            "points": ["U1.VCC"],
            "properties": {"via_current_a": 20.0, "via_drill_mm": 0.30, "via_plating_um": 25.0},
        }
    ]
    issues = run_erc({}, connections)
    codes = [i["code"] for i in issues]
    assert "VIA_BARREL_CURRENT_OVERLOAD" in codes


def test_erc_rule_55_fab_order_manifest_incomplete():
    """Verify ERC rule 55 flags missing order artifacts."""
    modules = {
        "__meta__": {
            "fabrication_order": {
                "artifacts": ["board-Edge_Cuts.gm1", "board-F_Cu.gtl"],  # missing drill/BOM/CPL
            }
        },
        "R1": {"kind": "RESISTOR", "value": "10k"},
    }
    issues = run_erc(modules, [{"net": "/GND", "points": ["R1.1"]}])
    codes = [i["code"] for i in issues]
    assert "FAB_ORDER_MANIFEST_INCOMPLETE" in codes


def test_mcp_server_via_and_fab_tools():
    """Verify MCP server dispatches both new tools."""
    res_via = handle_tool_call("solve_via_current_array", {"current_a": 3.0})
    assert not res_via.get("isError")
    assert '"meets_requirement": true' in res_via["content"][0]["text"]

    res_fab = handle_tool_call(
        "budget_fab_order",
        {"layers": 2, "qty": 5, "artifacts": {"board.drl": "d"}},
    )
    assert not res_fab.get("isError")
    assert '"submission_ready": true' in res_fab["content"][0]["text"]
