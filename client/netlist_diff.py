"""网表 ECO 比对引擎 (Engineering Change Order Netlist Diff).

工业背景与变更管理基准：
- PLM / ECO 变更管理 (Engineering Change Order)：
  硬件改版 (Rev A → Rev B) 后，必须向制造/采购/测试部门准确传递「改了什么」：
  1. 元件增删 (Added / Removed Components) —— 影响 BOM 采购与贴片程序；
  2. 元件属性变更 (Value / Package 变更) —— 影响物料替代与钢网/吸嘴选型；
  3. 网络增删 (Added / Removed Nets) —— 影响 ICT/飞针测试程序与探针针床；
  4. 引脚归属变更 (Pin Membership Moves) —— 影响飞针测试路径与 ICT 压针点。
- 变更等级 (ECO Severity)：
  * MAJOR：元件或网络增删 —— BOM/贴片/测试程序全部重做；
  * MINOR：仅元件值/封装变更 —— 物料替代评审即可；
  * NONE：两版网表完全一致。
- 对标 KiCad "Compare PCB" / Altium Design狸 Compare 与 IPC-2581 revision 工作流。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ComponentChange:
    ref: str
    field: str  # "value" / "package" / "kind"
    old: str
    new: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NetChange:
    net: str
    added_pins: list[str] = field(default_factory=list)
    removed_pins: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NetlistDiffReport:
    added_components: list[str] = field(default_factory=list)
    removed_components: list[str] = field(default_factory=list)
    changed_components: list[ComponentChange] = field(default_factory=list)
    added_nets: list[str] = field(default_factory=list)
    removed_nets: list[str] = field(default_factory=list)
    changed_nets: list[NetChange] = field(default_factory=list)
    eco_severity: str = "NONE"  # "NONE" / "MINOR" / "MAJOR"
    total_changes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_components": self.added_components,
            "removed_components": self.removed_components,
            "changed_components": [c.to_dict() for c in self.changed_components],
            "added_nets": self.added_nets,
            "removed_nets": self.removed_nets,
            "changed_nets": [n.to_dict() for n in self.changed_nets],
            "eco_severity": self.eco_severity,
            "total_changes": self.total_changes,
        }


def _net_pin_map(connections: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for conn in connections or []:
        net = str(conn.get("net", ""))
        out.setdefault(net, set()).update(str(p) for p in (conn.get("points") or []))
    return out


def diff_netlists(
    old_modules: dict[str, dict],
    old_connections: list[dict],
    new_modules: dict[str, dict],
    new_connections: list[dict],
) -> NetlistDiffReport:
    """比对改版前后两份网表，输出元件/网络/引脚级 ECO 变更清单与变更等级。"""
    old_modules = old_modules or {}
    new_modules = new_modules or {}

    report = NetlistDiffReport()

    # 1. 元件增删
    old_refs = {r for r in old_modules if r != "__meta__"}
    new_refs = {r for r in new_modules if r != "__meta__"}
    report.added_components = sorted(new_refs - old_refs)
    report.removed_components = sorted(old_refs - new_refs)

    # 2. 元件属性变更 (value / package / kind)
    for ref in sorted(old_refs & new_refs):
        om, nm = old_modules[ref], new_modules[ref]
        for fld in ("value", "package", "kind"):
            ov = str(om.get(fld, ""))
            nv = str(nm.get(fld, ""))
            if ov != nv:
                report.changed_components.append(ComponentChange(ref=ref, field=fld, old=ov, new=nv))

    # 3. 网络增删与引脚归属变更
    old_nets = _net_pin_map(old_connections)
    new_nets = _net_pin_map(new_connections)
    report.added_nets = sorted(set(new_nets) - set(old_nets))
    report.removed_nets = sorted(set(old_nets) - set(new_nets))

    for net in sorted(set(old_nets) & set(new_nets)):
        added = sorted(new_nets[net] - old_nets[net])
        removed = sorted(old_nets[net] - new_nets[net])
        if added or removed:
            report.changed_nets.append(NetChange(net=net, added_pins=added, removed_pins=removed))

    # 4. 变更等级
    structural = bool(report.added_components or report.removed_components or report.added_nets or report.removed_nets or report.changed_nets)
    report.total_changes = (
        len(report.added_components)
        + len(report.removed_components)
        + len(report.changed_components)
        + len(report.added_nets)
        + len(report.removed_nets)
        + len(report.changed_nets)
    )
    if structural:
        report.eco_severity = "MAJOR"
    elif report.changed_components:
        report.eco_severity = "MINOR"
    else:
        report.eco_severity = "NONE"

    return report
