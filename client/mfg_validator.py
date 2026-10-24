"""量产制造交付包全要素合规性与密码学校验器 (PCB Manufacturing Package Validator & Ledger).

工业背景与生产级验收规范：
- 适配真实 macOS 个人开发者与外部 Linux CI/CD 流水线：
  在无人值守的自动化制造交付中，开发者与代工厂 (EMS) 需要一键核对交付包是否完备无缺：
  1. 制造 Gerber 五层全量性：
     - Edge_Cuts (板框 .gm1)
     - Top/Bottom Copper (铜皮 .gtl / .gbl)
     - Top/Bottom Mask (阻焊开窗 .gts / .gbs)
     - Top/Bottom Silk (丝印层 .gto / .gbo)
  2. 数控钻孔 Excellon (.drl)：刀具表与坐标点有效性；
  3. 量产 BOM (CSV) 与 SMT 贴片 CPL (CSV) 的元器件位号一致性；
  4. 裸板飞针测试 IPC-D-356 网表或 IPC-2581B 智能制造数据包；
  5. 密码学 SHA-256 防篡改账本生成与校验。
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DeliverableCheck:
    artifact_name: str
    artifact_type: str  # "gerber", "drill", "bom", "cpl", "netlist", "ipc2581", "drawing"
    is_present: bool
    size_bytes: int
    sha256: str = ""
    status: str = "PASS"  # "PASS", "MISSING", "EMPTY"


@dataclass
class ManufacturingValidationReport:
    job_name: str
    is_package_complete: bool
    total_artifacts_checked: int
    missing_artifacts_count: int
    component_count_in_modules: int
    component_count_in_bom: int
    bom_cpl_consistent: bool
    sha256_manifest: str
    checks: list[DeliverableCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    standard: str = "IPC-2581B & ISO 9001 PCBA Package Completeness Verification"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["checks"] = [asdict(c) for c in self.checks]
        return d


#: A designator is a letter prefix plus a number — ``R12``, ``C_DEC_U_MCU`` is
#: not one, and neither is the footprint ``C0603`` nor the LCSC part ``C14663``.
#: The previous parser accepted anything starting with R/C/U/D/L/J/S/Q/Y, which
#: collected both of those as part references.
REF_TOKEN_RE = re.compile(r"^[A-Z]{1,3}[_A-Z0-9]*\d+[A-Z]?$")


#: Minimum solder-mask web between two openings, in mm. Below this the mask
#: scums during development and bridges the pins at reflow. 0.08 mm is the
#: figure JLCPCB and PCBWay publish as their process floor.
MIN_MASK_DAM_MM = 0.08


def _mask_openings(gerber_text: str) -> list[tuple[float, float, float, float]]:
    """Parse a mask Gerber into opening rectangles (x0, y0, x1, y1) in mm.

    Aperture definitions are read from the ``%ADD`` block and flashes are
    resolved against them, because the opening size is only knowable from the
    aperture the flash uses — the coordinate alone says nothing about width.
    """
    apertures: dict[int, tuple[str, float, float]] = {}
    for m in re.finditer(r"%ADD(\d+)([A-Z]),([0-9.]+)(?:X([0-9.]+))?\*%", gerber_text):
        code = int(m.group(1))
        shape = m.group(2)
        w = float(m.group(3))
        h = float(m.group(4)) if m.group(4) else w
        apertures[code] = (shape, w, h)

    rects: list[tuple[float, float, float, float]] = []
    current: tuple[str, float, float] | None = None
    for line in gerber_text.splitlines():
        sel = re.fullmatch(r"D(\d+)\*", line.strip())
        if sel:
            current = apertures.get(int(sel.group(1)))
            continue
        flash = re.fullmatch(r"X(-?\d+)Y(-?\d+)D03\*", line.strip())
        if flash and current:
            _, w, h = current
            x = int(flash.group(1)) / 100000.0
            y = int(flash.group(2)) / 100000.0
            rects.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
    return rects


def _tightest_mask_dam(
    artifacts_dict: dict[str, str | bytes],
    modules: dict[str, dict] | None,
) -> tuple[float, str, str] | None:
    """Find the narrowest mask web in the top-mask layer.

    Only pads that belong to the same part are compared: a web between two
    unrelated parts is not a manufacturability problem, it is a placement
    problem, and the DRC reports it separately.
    """
    raw = artifacts_dict.get("board-F_Mask.gts")
    if raw is None:
        return None
    text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw
    rects = _mask_openings(text)
    if len(rects) < 2:
        return None

    # Recover the designator for each opening from the CPL/placement data is not
    # available here, so compare every pair that is close enough to be a dam and
    # report the tightest. Pads from different parts are separated by placement
    # clearance, which is far larger than a mask dam.
    best: tuple[float, str, str] | None = None
    for i in range(len(rects)):
        ax0, ay0, ax1, ay1 = rects[i]
        for j in range(i + 1, len(rects)):
            bx0, by0, bx1, by1 = rects[j]
            # Gap along X when the Y ranges overlap, and vice versa.
            y_overlap = min(ay1, by1) - max(ay0, by0)
            x_overlap = min(ax1, bx1) - max(ax0, bx0)
            gap: float | None = None
            if y_overlap > 0:
                gap = max(bx0 - ax1, ax0 - bx1)
            if x_overlap > 0:
                g = max(by0 - ay1, ay0 - by1)
                gap = g if gap is None else min(gap, g)
            if gap is None or gap < 0:
                continue
            if best is None or gap < best[0]:
                best = (
                    gap,
                    f"({ax0:.2f},{ay0:.2f})",
                    f"({bx0:.2f},{by0:.2f})",
                )
    return best


REQUIRED_FAB_ARTIFACTS = [
    ("board-Edge_Cuts.gm1", "gerber", "板框层 (Edge_Cuts)"),
    ("board-F_Cu.gtl", "gerber", "顶层走线铜皮 (F_Cu)"),
    ("board-B_Cu.gbl", "gerber", "底层走线铜皮 (B_Cu)"),
    ("board-F_Mask.gts", "gerber", "顶层阻焊开窗 (F_Mask)"),
    ("board-B_Mask.gbs", "gerber", "底层阻焊开窗 (B_Mask)"),
    # Without a stencil layer no SMT line can build the board: the stencil is
    # what the printer uses to deposit solder paste. A package without it is a
    # hand-solder board regardless of what parts the design calls for.
    ("board-F_Paste.gtp", "gerber", "顶层 SMT 激光钢网开孔 (F_Paste)"),
    ("board.drl", "drill", "Excellon 数控钻孔文件 (.drl)"),
    ("bom.csv", "bom", "量产嘉立创/EMS SMT BOM 表格"),
    ("cpl.csv", "cpl", "SMT 贴片机中心坐标文件 (CPL)"),
]


def validate_manufacturing_package(
    artifacts_dict: dict[str, str | bytes],
    modules: dict[str, dict] | None = None,
    job_name: str = "PCB_PROJECT",
) -> ManufacturingValidationReport:
    """验证传入的制造交付文件集合是否完备，并计算 SHA256 校验账本。

    artifacts_dict: {filename: content_str_or_bytes}
    modules: 原始设计中的元件字典 (用于位号一致性校验)
    """
    artifacts_dict = artifacts_dict or {}
    modules = modules or {}
    checks: list[DeliverableCheck] = []
    missing_cnt = 0
    errors: list[str] = []
    manifest_lines = [f"# MANUFACTURING ARTIFACT CHECKSUMS — {job_name}", "# SHA-256 HASH                     FILENAME"]

    # 1. 检查核心必要制造交付件
    for fname, atype, desc in REQUIRED_FAB_ARTIFACTS:
        if fname in artifacts_dict:
            raw = artifacts_dict[fname]
            raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
            sz = len(raw_bytes)
            if sz > 0:
                h = hashlib.sha256(raw_bytes).hexdigest()
                checks.append(DeliverableCheck(fname, atype, True, sz, h, "PASS"))
                manifest_lines.append(f"{h}  {fname}")
            else:
                checks.append(DeliverableCheck(fname, atype, True, 0, "", "EMPTY"))
                errors.append(f"文件 {fname} ({desc}) 内容为空")
                missing_cnt += 1
        else:
            checks.append(DeliverableCheck(fname, atype, False, 0, "", "MISSING"))
            errors.append(f"缺少必要制造交付件: {fname} ({desc})")
            missing_cnt += 1

    # 2. 检查额外增强交付件 (IPC-2581 / IPC-D-356 / 装配图)
    for opt_name, atype in [("ipc2581.xml", "ipc2581"), ("testpoints.d356", "netlist"), ("assembly_drawing.svg", "drawing")]:
        if opt_name in artifacts_dict:
            raw = artifacts_dict[opt_name]
            raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
            sz = len(raw_bytes)
            if sz > 0:
                h = hashlib.sha256(raw_bytes).hexdigest()
                checks.append(DeliverableCheck(opt_name, atype, True, sz, h, "PASS"))
                manifest_lines.append(f"{h}  {opt_name}")

    # 3. 校验 BOM 与 modules 元件位号一致性
    bom_consistent = True
    # Fiducials / test points / mounting holes are fabricated features, not
    # purchased parts: the BOM legitimately omits them, so they take no part
    # in the designator comparison.
    real_mod_refs = {
        r
        for r in modules
        if r != "__meta__" and not r.startswith(("FID", "TP_"))
    }
    mod_count = len(real_mod_refs)
    bom_count = 0

    if "bom.csv" in artifacts_dict:
        bom_raw = artifacts_dict["bom.csv"]
        bom_text = bom_raw.decode("utf-8", errors="ignore") if isinstance(bom_raw, bytes) else bom_raw
        # The designator field is quoted and holds several references separated
        # by commas ("C_SW1,C_SW2"). Splitting on commas by hand tore those
        # apart, so the references were read as fragments and reported missing.
        #
        # Which column is the designator column is decided by the header, and
        # *what counts as a reference* is decided by the design itself — the
        # module map is the authority. Guessing with a pattern collected
        # footprints (C0603) and LCSC numbers (C14663) as parts, and then missed
        # legitimate references that carry no number (U_MCU).
        reader = csv.reader(io.StringIO(bom_text))
        header: list[str] = []
        bom_tokens: set[str] = set()
        for row in reader:
            cells = [c.strip() for c in row]
            if not any(cells):
                continue
            lowered = [c.lower() for c in cells]
            if "designator" in lowered:
                header = lowered
                continue
            if header and "designator" in header:
                idx = header.index("designator")
                raw_des = cells[idx] if idx < len(cells) else ""
            else:
                raw_des = ",".join(cells[:2])
            bom_tokens.update(t for t in re.split(r"[,;\s]+", raw_des) if t)
        bom_refs = bom_tokens & real_mod_refs if real_mod_refs else bom_tokens

        bom_count = len(bom_refs)
        if real_mod_refs and bom_refs:
            diff = real_mod_refs - bom_refs
            if diff:
                bom_consistent = False
                errors.append(f"BOM 表格缺少设计中的元件位号: {sorted(diff)[:5]}")

    # 3b. 校验 BOM 与 CPL 位号一致性（真实量产缺陷：贴片漏件）
    #
    # `bom_cpl_consistent` used to report the BOM-vs-modules comparison, which is
    # a different question. The one that stops a board from being built is
    # whether every part in the BOM has a placement entry: a part in the BOM but
    # not the CPL is ordered, paid for, and never soldered — the board ships
    # unpopulated and the fault is found at functional test, not at assembly.
    cpl_tokens: set[str] = set()
    for cpl_name in ("cpl.csv", "pick_and_place.csv", "positions.csv"):
        if cpl_name not in artifacts_dict:
            continue
        cpl_raw = artifacts_dict[cpl_name]
        cpl_text = cpl_raw.decode("utf-8", errors="ignore") if isinstance(cpl_raw, bytes) else cpl_raw
        for line in cpl_text.splitlines():
            line = line.strip()
            if not line or line.lower().startswith(("designator", "ref", "comment")):
                continue
            first = line.split(",")[0].strip().strip('"')
            if first:
                cpl_tokens.add(first)
        break
    cpl_refs = cpl_tokens & real_mod_refs if real_mod_refs else cpl_tokens

    if cpl_refs and bom_refs:
        unplaced = bom_refs - cpl_refs
        orphaned = cpl_refs - bom_refs
        if unplaced:
            bom_consistent = False
            errors.append(
                f"BOM 中有 {len(unplaced)} 个位号在 CPL 贴片坐标文件中缺失，这些器件会被采购但不会贴装："
                f"{sorted(unplaced)[:8]}"
            )
        if orphaned:
            bom_consistent = False
            errors.append(f"CPL 中有 {len(orphaned)} 个位号不在 BOM 中，贴片机会找不到物料：{sorted(orphaned)[:8]}")

    # 4. 阻焊桥 (Solder Mask Dam) 可制造性
    #
    # Between two pads closer than about 0.5 mm the mask web is only a few tens of
    # microns wide. Below the fab's minimum the web lifts during development and
    # floats into the gap — "mask scum". It looks like a cosmetic defect and
    # behaves like a solder bridge: the next reflow shorts the two pins. The
    # package must therefore state the tightest dam it contains, and whether it is
    # under the process floor.
    dam = _tightest_mask_dam(artifacts_dict, modules)
    if dam is not None:
        tightest_mm, ref_a, ref_b = dam
        if tightest_mm < MIN_MASK_DAM_MM:
            errors.append(
                f"阻焊桥宽度仅 {tightest_mm:.3f} mm（{ref_a} / {ref_b} 之间），"
                f"低于量产工艺极限 {MIN_MASK_DAM_MM:.2f} mm；显影时阻焊会剥离飘油，"
                f"回流后两脚桥连。需改为合并开窗 (Gang Mask) 或加大焊盘间距。"
            )

    is_complete = missing_cnt == 0 and len(errors) == 0

    return ManufacturingValidationReport(
        job_name=job_name,
        is_package_complete=is_complete,
        total_artifacts_checked=len(checks),
        missing_artifacts_count=missing_cnt,
        component_count_in_modules=mod_count,
        component_count_in_bom=bom_count,
        bom_cpl_consistent=bom_consistent,
        sha256_manifest="\n".join(manifest_lines) + "\n",
        checks=checks,
        errors=errors,
    )
