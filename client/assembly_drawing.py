"""ASME Y14.5 / IPC-2221 装配图 SVG 生成器 (PCBA Assembly Drawing Generator).

工业背景与制图规范：
- ASME Y14.5《尺寸与公差标注》与 IPC-2221B §11 装配图要求：
  PCBA 交付组装厂必须随附比例装配图 (Assembly Drawing)，内容包含：
  1. 底视图按 X 镜像 (Bottom view mirrored)，顶视图正投影，按 1:1 或标注比例；
  2. 每个元件标注位号 (Reference Designator) 与外框 (body outline)；
  3. 极性标识：IC 第一脚圆点 (Pin-1 Dot)、二极管/LED 阴极条 (Cathode Bar)、
     电解电容 "+" 极性框 (IPC-A-610G §5.2 元件极性标识要求)；
  4. 标题栏 (Title Block)：图号/版本/比例/日期/设计-审核签署栏 (ASME Y14.100 工程制图惯例)；
  5. 比例尺 (Scale Bar) 与图幅边框。
- 输出为自包含 SVG (零依赖)，可直接嵌入 iBOM 或打印张贴供人工插件/返修对照。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

MIRROR_MARGIN_MM = 8.0
POLAR_KINDS = ("LED", "DIODE", "TVS", "ELECTROLYTIC")


@dataclass
class PolarityMark:
    ref: str
    x_mm: float
    y_mm: float
    kind: str  # "pin1_dot" / "cathode_bar" / "plus_frame"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssemblyDrawingResult:
    svg: str
    width_mm: float
    height_mm: float
    mirrored_bottom: bool
    component_count: int
    polarity_marks: list[PolarityMark] = field(default_factory=list)
    scale_note: str = "SCALE 1:1 (mm)"
    drawing_standard: str = "ASME Y14.5 / IPC-2221B Section 11"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["polarity_marks"] = [p.to_dict() for p in self.polarity_marks]
        return d


def _esc(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def export_assembly_drawing_svg(
    modules: dict[str, dict],
    board_width_mm: float = 70.0,
    board_height_mm: float = 50.0,
    mirrored_bottom: bool = True,
    title: str = "PCBA ASSEMBLY DRAWING",
    revision: str = "A",
) -> AssemblyDrawingResult:
    """Generate a self-contained scaled assembly drawing SVG with refDes + polarity marks."""
    bw = max(1.0, float(board_width_mm))
    bh = max(1.0, float(board_height_mm))
    margin = MIRROR_MARGIN_MM
    sheet_w = bw + 2 * margin + 30.0  # + title block strip
    sheet_h = bh + 2 * margin + 18.0  # + title block strip

    ox = margin
    oy = margin

    def tx(x_mm: float) -> float:
        x = x_mm if not mirrored_bottom else bw - x_mm
        return round(ox + x, 3)

    def ty(y_mm: float) -> float:
        return round(oy + y_mm, 3)

    parts: list[str] = []
    polarity_marks: list[PolarityMark] = []

    for ref, m in sorted(modules.items()):
        if ref == "__meta__":
            continue
        pos = m.get("position") or [bw / 2.0, bh / 2.0]
        px = float(pos[0]) if len(pos) >= 2 else bw / 2.0
        py = float(pos[1]) if len(pos) >= 2 else bh / 2.0
        pkg = str(m.get("package", "")).upper()
        kind = str(m.get("kind", "")).upper()
        val = str(m.get("value", ""))

        # Simple body footprint estimate from package keyword
        bw_mm, bh_mm = 3.0, 2.0
        if "0402" in pkg:
            bw_mm, bh_mm = 1.0, 0.5
        elif "0603" in pkg:
            bw_mm, bh_mm = 1.6, 0.8
        elif "0805" in pkg:
            bw_mm, bh_mm = 2.0, 1.25
        elif "1206" in pkg:
            bw_mm, bh_mm = 3.2, 1.6
        elif "SOT" in pkg:
            bw_mm, bh_mm = 2.9, 1.6
        elif "SOIC" in pkg or "SOP" in pkg:
            bw_mm, bh_mm = 5.0, 4.0
        elif "QFN" in pkg or "DFN" in pkg:
            bw_mm, bh_mm = 5.0, 5.0
        elif "QFP" in pkg or "LQFP" in pkg:
            bw_mm, bh_mm = 9.0, 9.0
        elif "BGA" in pkg:
            bw_mm, bh_mm = 8.0, 8.0
        elif "MODULE" in pkg:
            bw_mm, bh_mm = 10.0, 8.0
        elif "TYPE-C" in pkg or "USB" in pkg:
            bw_mm, bh_mm = 9.0, 7.5

        cx, cy = tx(px), ty(py)
        half_w, half_h = bw_mm / 2.0, bh_mm / 2.0

        parts.append(
            f'<rect x="{round(cx - half_w, 3)}" y="{round(cy - half_h, 3)}" '
            f'width="{bw_mm}" height="{bh_mm}" fill="none" stroke="#1e293b" stroke-width="0.15"/>'
        )
        parts.append(
            f'<text x="{cx}" y="{round(cy - half_h - 0.4, 3)}" font-size="1.4" '
            f'font-family="monospace" text-anchor="middle" fill="#0f172a">{_esc(ref)}</text>'
        )
        if val:
            parts.append(
                f'<text x="{cx}" y="{round(cy + half_h + 1.6, 3)}" font-size="1.1" '
                f'font-family="monospace" text-anchor="middle" fill="#475569">{_esc(val)}</text>'
            )

        # Polarity marks (IPC-A-610G §5.2)
        is_polar = kind in POLAR_KINDS or bool(m.get("polarized", False))
        if is_polar:
            if kind in ("LED", "DIODE", "TVS"):
                # Cathode bar on the mirrored-left edge
                bar_x = cx - half_w
                parts.append(
                    f'<line x1="{round(bar_x, 3)}" y1="{round(cy - half_h, 3)}" '
                    f'x2="{round(bar_x, 3)}" y2="{round(cy + half_h, 3)}" '
                    f'stroke="#dc2626" stroke-width="0.3"/>'
                )
                polarity_marks.append(PolarityMark(ref, px, py, "cathode_bar"))
            else:
                # Plus frame (electrolytic)
                parts.append(
                    f'<text x="{round(cx - half_w + 0.6, 3)}" y="{round(cy - half_h + 1.6, 3)}" '
                    f'font-size="1.3" font-family="monospace" fill="#dc2626">+</text>'
                )
                polarity_marks.append(PolarityMark(ref, px, py, "plus_frame"))
        elif kind in ("IC", "MCU", "REGULATOR", "TRANSCEIVER", "SENSOR", "DRIVER"):
            # Pin-1 dot at top-left corner of body
            parts.append(
                f'<circle cx="{round(cx - half_w + 0.6, 3)}" cy="{round(cy - half_h + 0.6, 3)}" '
                f'r="0.35" fill="#dc2626"/>'
            )
            polarity_marks.append(PolarityMark(ref, px, py, "pin1_dot"))

    # Title block (ASME Y14.100)
    tb_y = oy + bh + margin
    title_block = f'''<g id="titleblock">
  <rect x="{ox}" y="{round(tb_y, 3)}" width="{round(bw + 30.0, 3)}" height="12" fill="none" stroke="#0f172a" stroke-width="0.3"/>
  <line x1="{round(ox + (bw + 30.0) * 0.4, 3)}" y1="{round(tb_y, 3)}" x2="{round(ox + (bw + 30.0) * 0.4, 3)}" y2="{round(tb_y + 12, 3)}" stroke="#0f172a" stroke-width="0.2"/>
  <line x1="{round(ox + (bw + 30.0) * 0.7, 3)}" y1="{round(tb_y, 3)}" x2="{round(ox + (bw + 30.0) * 0.7, 3)}" y2="{round(tb_y + 12, 3)}" stroke="#0f172a" stroke-width="0.2"/>
  <text x="{round(ox + 1.5, 3)}" y="{round(tb_y + 4.5, 3)}" font-size="2.4" font-family="monospace" fill="#0f172a">{_esc(title)}</text>
  <text x="{round(ox + 1.5, 3)}" y="{round(tb_y + 9.5, 3)}" font-size="1.6" font-family="monospace" fill="#475569">BOTTOM VIEW{" (MIRRORED)" if mirrored_bottom else " (TOP VIEW)"} · UNITS mm</text>
  <text x="{round(ox + (bw + 30.0) * 0.4 + 1.5, 3)}" y="{round(tb_y + 4.5, 3)}" font-size="1.8" font-family="monospace" fill="#0f172a">REV {_esc(revision)}</text>
  <text x="{round(ox + (bw + 30.0) * 0.4 + 1.5, 3)}" y="{round(tb_y + 9.5, 3)}" font-size="1.4" font-family="monospace" fill="#475569">SCALE 1:1</text>
  <text x="{round(ox + (bw + 30.0) * 0.7 + 1.5, 3)}" y="{round(tb_y + 4.5, 3)}" font-size="1.5" font-family="monospace" fill="#0f172a">DRAWN: CircuitAgent</text>
  <text x="{round(ox + (bw + 30.0) * 0.7 + 1.5, 3)}" y="{round(tb_y + 9.5, 3)}" font-size="1.5" font-family="monospace" fill="#0f172a">CHK: __________</text>
</g>'''

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{round(sheet_w, 3)}mm" height="{round(sheet_h, 3)}mm" viewBox="0 0 {round(sheet_w, 3)} {round(sheet_h, 3)}">
<rect width="100%" height="100%" fill="#ffffff"/>
<g id="board-outline">
  <rect x="{ox}" y="{oy}" width="{bw}" height="{bh}" fill="none" stroke="#0f172a" stroke-width="0.4"/>
</g>
<g id="components">
{chr(10).join(parts)}
</g>
{title_block}
</svg>'''

    return AssemblyDrawingResult(
        svg=svg,
        width_mm=round(sheet_w, 2),
        height_mm=round(sheet_h, 2),
        mirrored_bottom=mirrored_bottom,
        component_count=len([r for r in modules if r != "__meta__"]),
        polarity_marks=polarity_marks,
        scale_note=f"SCALE 1:1 · SHEET {round(sheet_w, 1)} x {round(sheet_h, 1)} mm",
    )
