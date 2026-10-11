"""Tests for panel grid utilization optimizer, ERC rule 32, and MCP tool 45."""

from client.erc import run_erc
from client.mcp_server import handle_tool_call
from client.panel_optimizer import optimize_panel_grid


def test_panel_optimizer_ranking():
    """Verify ranked options sorted by utilization with a feasible best."""
    rep = optimize_panel_grid(board_width_mm=50.0, board_height_mm=40.0, max_grid=4)
    assert rep.best is not None
    assert rep.best.feasible is True
    assert rep.best.utilization_pct >= 70.0
    # ranked must be descending by utilization
    utils = [o.utilization_pct for o in rep.ranked]
    assert utils == sorted(utils, reverse=True)


def test_panel_optimizer_rejects_oversize():
    """Verify options exceeding the max panel size are rejected with reasons."""
    rep = optimize_panel_grid(
        board_width_mm=140.0,
        board_height_mm=120.0,
        max_grid=4,
        max_panel_mm=300.0,
    )
    assert rep.rejected_count > 0
    assert all(o.rejected_reason for o in rep.ranked if not o.feasible) or rep.best is not None
    if rep.best is not None:
        assert rep.best.panel_width_mm <= 300.0
        assert rep.best.panel_height_mm <= 300.0


def test_erc_rule_32_mounting_hole_keepout():
    """Verify ERC rule 32 (MOUNTING_HOLE_KEEPOUT_MISSING)."""
    modules = {"H1": {"kind": "MOUNT_HOLE", "value": "M3", "has_keepout_ring": False}}
    issues = run_erc(modules, [{"net": "/GND", "points": ["U1.GND"]}])
    codes = [i["code"] for i in issues]
    assert "MOUNTING_HOLE_KEEPOUT_MISSING" in codes

    modules_ok = {"H1": {"kind": "MOUNT_HOLE", "value": "M3", "has_keepout_ring": True}}
    issues_ok = run_erc(modules_ok, [{"net": "/GND", "points": ["U1.GND"]}])
    assert "MOUNTING_HOLE_KEEPOUT_MISSING" not in [i["code"] for i in issues_ok]


def test_mcp_server_panel_optimizer_tool():
    """Verify MCP server dispatches optimize_panel_grid (tool 45)."""
    res = handle_tool_call(
        "optimize_panel_grid",
        {"board_width_mm": 45.0, "board_height_mm": 35.0, "max_grid": 3},
    )
    assert not res.get("isError")
    text = res["content"][0]["text"]
    assert '"best"' in text
    assert '"utilization_pct"' in text
