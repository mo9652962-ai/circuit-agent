"""IPC-2581B Intelligent Fabrication Data Package Exporter (Single-File XML Handoff).

Industrial benchmark & standards:
- IPC-2581B: Generic Requirements for Printed Circuit Board Assembly Products Manufacturing
  Description Data and Transfer Methodology — the modern single-file intelligent data
  exchange format replacing the legacy "Gerber + Excellon + BOM + TXT notes" ZIP bundle.
  Adopted by Siemens X, Altium Designer, Zuken, Cadence, Polar, and major OSAT/EMS houses
  (Foxconn, Jabil, Plexus) for quote-to-fab handoff.
- Simplified conformant structure generated here (schema revision B):
    <IPC-2581 revision="B">                      — root, c="content" role
      <Content>                                  — content level
        <FunctionMode>IPC-2581 Simple</FunctionMode>
        <LayerSet name="ALL">                    — layer view set
          <StepAndLayerRef name="STEP_PCB"/>
        </LayerSet>
        <Step name="STEP_PCB">
          <Stackup>…</Stackup>                   — layer stack with materials/thicknesses
          <Bom>…</Bom>                           — bill of materials with refDes → MPN
          <CadData>
            <CadLayer>…</CadLayer>               — logical layers
            <Components>…</Components>           — placed components (refDes, part, x/y)
            <Nets>…</Nets>                       — net list with pin node membership
          </CadData>
          <Profile>…</Profile>                   — board outline bounding box
        </Step>
      </Content>
- All values XML-escaped via xml.sax.saxutils; output is deterministic (no timestamps),
  parseable by any IPC-2581 consumer and validated by xml.etree in the test suite.
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape, quoteattr

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'
IPC2581_NS = "http://www.ipc.org/2581"


def _el(tag: str, text: Any = None, attrs: str = "", indent: int = 0, self_close: bool = False) -> str:
    pad = "  " * indent
    a = f" {attrs}" if attrs else ""
    if self_close:
        return f"{pad}<{tag}{a}/>"
    if text is None:
        return f"{pad}<{tag}{a}>"
    return f"{pad}<{tag}{a}>{escape(str(text))}</{tag}>"


def export_ipc2581(
    modules: dict[str, dict],
    connections: list[dict],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    stackup_layers: list[dict] | None = None,
    project_name: str = "HARDWARE_PROJECT",
) -> str:
    """Generate a simplified IPC-2581B XML fabrication handoff from modules + netlist.

    stackup_layers: optional list of {name, class ('CONDUCTOR'/'DIELECTRIC'), thickness_um, material}.
    """
    modules = modules or {}
    connections = connections or []
    bw = max(1.0, float(board_width_mm))
    bh = max(1.0, float(board_height_mm))

    lines: list[str] = [XML_DECLARATION]
    lines.append(f'<IPC-2581 xmlns="{IPC2581_NS}" revision="B" c="content">')
    lines.append(_el("Content", indent=1))
    lines.append(_el("FunctionMode", "IPC-2581 Simple", indent=2))
    lines.append(_el("Organization", attrs=f"name={quoteattr(project_name)}", indent=2, self_close=True))

    # LayerSet view
    lines.append(_el("LayerSet", attrs='name="ALL"', indent=2))
    lines.append(_el("StepAndLayerRef", attrs='name="STEP_PCB"', indent=3, self_close=True))
    lines.append(_el("/LayerSet", indent=2))

    # Step
    lines.append(_el("Step", attrs=f'name={quoteattr("STEP_PCB")}', indent=2))

    # Stackup
    layers = stackup_layers or [
        {"name": "TOP", "class": "CONDUCTOR", "thickness_um": 35, "material": "COPPER"},
        {"name": "DIELECTRIC_1", "class": "DIELECTRIC", "thickness_um": 200, "material": "FR-4"},
        {"name": "BOTTOM", "class": "CONDUCTOR", "thickness_um": 35, "material": "COPPER"},
    ]
    lines.append(_el("Stackup", indent=3))
    lines.append(_el("Layer", attrs='name="STEP_PCB" p="1"', indent=4, self_close=True))
    for ly in layers:
        attrs = (
            f'name={quoteattr(str(ly.get("name", "L")))} '
            f'class={quoteattr(str(ly.get("class", "CONDUCTOR")))} '
            f'thickness="{float(ly.get("thickness_um", 35)) / 1000.0:.4f}" '
            f"material={quoteattr(str(ly.get('material', 'COPPER')))}"
        )
        lines.append(_el("Layer", indent=5, attrs=attrs, self_close=True))
    lines.append(_el("/Stackup", indent=3))

    # BOM
    lines.append(_el("Bom", indent=3))
    for ref, m in sorted(modules.items()):
        if ref == "__meta__":
            continue
        attrs = (
            f'refDes={quoteattr(str(ref))} '
            f'MPN={quoteattr(str(m.get("value", "")))} '
            f"quantity=\"1\" "
            f"package={quoteattr(str(m.get('package', '')))}"
        )
        lines.append(_el("Item", indent=4, attrs=attrs, self_close=True))
    lines.append(_el("/Bom", indent=3))

    # CadData
    lines.append(_el("CadData", indent=3))
    lines.append(_el("CadLayer", attrs='name="ALL"', indent=4))
    lines.append(_el("/CadLayer", indent=4))

    # Components (placed)
    lines.append(_el("Components", indent=4))
    for ref, m in sorted(modules.items()):
        if ref == "__meta__":
            continue
        pos = m.get("position") or [bw / 2.0, bh / 2.0]
        x = float(pos[0]) if len(pos) >= 2 else bw / 2.0
        y = float(pos[1]) if len(pos) >= 2 else bh / 2.0
        attrs = (
            f'refDes={quoteattr(str(ref))} '
            f'part={quoteattr(str(m.get("value", "")))} '
            f'x="{round(x, 3)}" y="{round(y, 3)}" '
            f"package={quoteattr(str(m.get('package', '')))}"
        )
        lines.append(_el("Component", indent=5, attrs=attrs, self_close=True))
    lines.append(_el("/Components", indent=4))

    # Nets with pin node membership
    lines.append(_el("Nets", indent=4))
    for conn in connections:
        net = str(conn.get("net", ""))
        pts = conn.get("points") or []
        attrs = f"name={quoteattr(net)}"
        lines.append(_el("Net", indent=5, attrs=attrs))
        for pt in pts:
            ref, _, pin = str(pt).partition(".")
            lines.append(_el("Pin", attrs=f"component={quoteattr(ref)} number={quoteattr(pin or '1')}", indent=6, self_close=True))
        lines.append(_el("/Net", indent=5))
    lines.append(_el("/Nets", indent=4))

    lines.append(_el("/CadData", indent=3))

    # Profile (board bounding box)
    lines.append(_el("Profile", indent=3))
    lines.append(_el("Polygon", indent=4))
    for px, py in ((0.0, 0.0), (bw, 0.0), (bw, bh), (0.0, bh)):
        lines.append(_el("PolyPoint", attrs=f'x="{round(px, 3)}" y="{round(py, 3)}"', indent=5, self_close=True))
    lines.append(_el("/Polygon", indent=4))
    lines.append(_el("/Profile", indent=3))

    lines.append(_el("/Step", indent=2))
    lines.append(_el("/Content", indent=1))
    lines.append("</IPC-2581>")
    return "\n".join(lines)
