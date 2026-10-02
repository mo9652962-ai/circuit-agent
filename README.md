<p align="center">
  <img src="docs/images/banner-1200x640.png" alt="CircuitAgent Banner" width="100%">
</p>

# CircuitAgent · Community Edition

<!-- mcp-name: io.github.mo9652962-ai/circuit-agent-client -->

**Prompt → Schematic → Layout → 3D Enclosure → Fabrication Bundle**

<p align="center">
  <a href="https://github.com/mo9652962-ai/circuit-agent/actions/workflows/ci.yml"><img src="https://github.com/mo9652962-ai/circuit-agent/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="tests/"><img src="https://img.shields.io/badge/tests-120%20passing-brightgreen.svg" alt="Tests"></a>
  <a href="https://github.com/mo9652962-ai/circuit-agent/releases"><img src="https://img.shields.io/badge/release-v0.1.5-blueviolet.svg" alt="Release"></a>
</p>

<p align="center">
  <a href="README.md"><b>中文说明</b></a> | <a href="README_EN.md"><b>English</b></a>
</p>

> **Status: alpha.** This repository is the open community layer of CircuitAgent: the
> hardware DSL, the LCSC live-selection client, and the data contracts that the
> full compiler consumes. The block set is deliberately small and every block is
> unit-tested — correctness over coverage.

---

## 为什么需要这一层 (Why this layer exists)

让大语言模型直接生成底层走线、焊盘与封装，几乎必然产出非法几何或引脚短路。
CircuitAgent 的做法是把 LLM 的输出**约束在预验证的电路积木上**，再用 Pydantic
契约把它变成确定性网表 —— 模型只负责"选积木"，不负责"画线"。

<p align="center">
  <img src="docs/images/demo.gif" alt="CircuitAgent Pro 工作台演示" width="85%">
</p>

```text
Natural language prompt
        │
        ▼
┌────────────────────────┐
│  CircuitBlocks DSL     │  keyword → audited sub-circuits (deterministic)
└────────────────────────┘
        │
        ▼
┌────────────────────────┐
│  Netlist contract      │  Pydantic / JSON Schema (SSOT)
└────────────────────────┘
        │
   ┌────┴─────┐
   ▼          ▼
┌────────┐ ┌──────────────────┐
│ LCSC   │ │ REST / MCP APIs  │
│ client │ │ (community layer)│
└────────┘ └──────────────────┘
```

---

## 快速上手 (Quick Start)

**方式 A · 从 PyPI 安装（推荐）**

```bash
pip install circuit-agent-client
```

**方式 B · 从源码使用**

```bash
git clone https://github.com/mo9652962-ai/circuit-agent.git
cd circuit-agent
```

**零运行时依赖** —— 纯 Python 标准库实现，装完即用，不拉任何第三方包。
跑测试才需要 dev extra：`pip install -e ".[dev]"`

### 1 · 一句话生成硬件网表

```python
from client.synthesizer import synthesize_from_prompt

spec = synthesize_from_prompt(
    "基于 ESP32-C3 的环境监测节点，带 Type-C 供电、I2C 传感器插座、指示灯和2个按键"
)

print(spec["chip_id"])                            # ESP32-C3
print(len(spec["modules"]))                       # 元器件数
print(spec["netlist"]["connections"][0])          # 第一条网络连接
print(spec["unmatched"])                          # 未识别的意图（不会被静默丢弃）
```

映射是**确定性的**：同一句话永远产出逐字节相同的结果（CI 中有对应断言）。

### 2 · 查询立创商城实时库存与单价

```python
from client.lcsc_client import search_lcsc_parts

for part in search_lcsc_parts("CH340N", limit=3):
    print(f"[{part['lcsc_part']}] {part['part_number']} | {part['package']} | "
          f"库存 {part['stock']} | ${part['price_usd']} | {part['part_class']}")
```

```text
[C506813] CH340N | SOP-8_L5.0-W4.0-P1.27-LS6.0-BL | 库存 196 | $0.5537 | Extended Part
```

客户端自带**重试退避 + 硬超时 + 24 小时磁盘缓存 + 防御式解析**：上游改结构不会
抛异常，断网时回落到缓存（缓存也没有则返回空列表，调用方永远不必处理传输层异常）。

### 3 · 直接用积木搭电路

```python
from client.circuit_blocks import block_usb_c_power, block_power_ldo_3v3

blk = block_power_ldo_3v3()
for comp in blk.components:
    print(comp.ref, comp.value, comp.package, comp.lcsc)
```

---

## 积木清单 (Block Catalogue)

| Block | 说明 | 关键设计点 |
|:---|:---|:---|
| `block_usb_c_power` | Type-C 供电输入 | 双 5.1k CC 下拉（sink 角色，非 56k 上拉） |
| `block_power_ldo_3v3` | AMS1117-3.3V 稳压 | 10µF 输入/输出储能电容 |
| `block_crystal_clock` | 无源晶振 + 负载电容 | 标记 `guard_ring` 属性供后端加地屏蔽环 |
| `block_button` | 消抖按键 | 10k 上拉 + 100nF RC，位号可参数化 |
| `block_led` | 状态指示灯 | 限流电阻 + 颜色/阻值可参数化 |
| `block_buzzer` | 蜂鸣器驱动 | S8050 NPN + 1N4148W 反向续流二极管 |
| `block_i2c_header` | I2C 扩展排针 | SCL/SDA 各 4.7k 上拉 |
| `block_rs485_transceiver` | SP3485 半双工差分串口 | 120Ω 终端电阻 + 100nF 去耦 + 3P 排针引出 |
| `block_can_transceiver` | SN65HVD230 3.3V CAN 节点 | 120Ω 终端匹配 + 10k 斜率控制 (高速模式) |
| `block_battery_tp4056` | TP4056 1A 线性锂电充电 | 1.2k 限流 + 充/满双色指示灯 + 2P 电池端子 |

每个积木的引脚号、LCSC 料号、封装名在冻结前均对照数据手册与立创商城列表核验过。
`tests/test_circuit_blocks.py` 会强制校验：位号唯一、每个元件都有封装与料号、
网络端点必须指向已声明的元件、每个积木都必须接 `/GND`。

---

## MCP Server (AI Agent 工具服务)

CircuitAgent 内置标准 JSON-RPC 2.0 stdio MCP Server，基于纯 Python 标准库构建（无需任何第三方 pip 库），可无缝接入 **Claude Desktop**、**Cursor** 或 **Windsurf**。

### 运行方式
```bash
python -m client.mcp_server
```

### Claude Desktop 配置 (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "circuit-agent": {
      "command": "python",
      "args": ["-m", "client.mcp_server"],
      "cwd": "/path/to/circuit-agent"
    }
  }
}
```

### 暴露的工具 (Tools)
1. `synthesize_circuit`: 输入自然语言，输出确定性硬件网表与积木清单。
2. `search_lcsc_parts`: 免 Key 实时查询立创商城的元器件库存、封装、阶梯单价与基础库/扩展库属性。
3. `list_circuit_blocks`: 列出 DSL 中全部可用的 10 大已审计电路积木规格。
4. `validate_netlist`: 根据正式 JSON Schema 校验网表数据结构合法性。
5. `calculate_trace_impedance`: 基于 IPC-2141 解析公式计算微带线与差分对走线阻抗（50Ω RF / 90Ω USB / 120Ω CAN/485）。
6. `calculate_bom_cost`: PCBA 成本核算器，自动精算元器件裸成本与嘉立创扩展库换料费（¥20/种）。

### 暴露的资源 (Resources)
支持通过 `circuit://` URI 直接将规范加载到大模型上下文，无需执行额外工具：
- `circuit://specs/netlist-schema`: 完整的网表 Draft-07 JSON Schema。
- `circuit://specs/cpl-standard`: 嘉立创 SMT 坐标规范与封装偏角补偿表。
- `circuit://blocks/catalog`: 10 大电路积木的元器件、引脚与网络全量清单。
- `circuit://rules/jlc-smt`: 嘉立创四层板叠层 (JLC04161H) 与生产物理规则。
- `circuit://examples/esp32c3-minimal`: ESP32-C3 极简温湿度节点参考网表。
- `circuit://examples/stm32f103-controller`: STM32F103 工业控制板参考网表。
- `circuit://examples/rp2040-dualcore`: RP2040 双核传感器扩展板参考网表。

### 快捷工程 Prompt (Slash-Commands)
- `/design_hardware_project`: 全流程硬件设计指令（积木匹配 → 阻抗计算 → BOM核算 → 网表校验）。
- `/audit_schematic_netlist`: Senior EE 硬件体检审查指令（去耦电容亲和性、差分对等长、Type-C 下拉阻抗）。
- `/optimize_bom_cost`: PCBA 降本优化指令（分析扩展库物料并推荐免换料费的基础库替代料）。

---

## 数据契约 (Contracts)

- [`specs/netlist_schema.json`](specs/netlist_schema.json) — 网表 JSON Schema
- [`specs/cpl_standard.md`](specs/cpl_standard.md) — 嘉立创 SMT 坐标规范与封装偏角补偿表
- [`examples/`](examples/) — STM32F103 / ESP32-C3 / RP2040 参考网表，CI 强制校验其符合 Schema

---

## 测试与 CI

```bash
pytest tests/ -q      # 120 passed
```

CI 在 `ubuntu-latest` + `windows-latest` × Python 3.10/3.11/3.12 上跑全量测试，
并额外做两件事：校验 `examples/` 全部符合 Schema、离线跑通 README 里的快速上手命令。

---

## 范围与路线图 (Scope & Roadmap)

**本仓库包含**：硬件 DSL 与积木库、立创实时选型客户端、网表/CPL 数据契约、标准 MCP Server、REST 交互接口。

**暂不包含**：多层板物理布局与布线求解、参数化 3D 壳体布尔几何、Senior EE 物理规则门禁。
这些是上游编译器的高级能力，仍在开发中；本仓库通过稳定的数据契约与客户端接口与其对接，
契约本身是公开且版本化的。

路线图：

- [x] 积木库 + 确定性映射 + 单元测试
- [x] 立创实时选型客户端（重试/缓存/降级）
- [x] JSON Schema + 三份参考样例 + CI
- [x] 工业级实用积木（RS485 / CAN / TP4056 锂电）
- [x] 标准 MCP Server 实现（纯标准库，4 大工具）
- [x] 中英双语文档与官方门面 (Banner + Demo GIF)
- [ ] 更多传感器积木（AHT20 温湿度 / MPU6050 六轴）
- [ ] 支持自定义第三方芯片引脚分配映射规则

---

## 参与贡献 (Contributing)

最欢迎的贡献是**新增经过核验的电路积木**：带上数据手册依据的引脚定义与立创料号，
并补上对应单测即可提 PR。Issue 里也欢迎贴出你希望支持的芯片型号。

---

## 名称说明 (Naming)

"CircuitAgent" 是一个较通用的名字，社区中已有若干同名或近名的项目（例如
`singularguy/CircuitManus` 内部的 `CircuitAgent` 类、`Circuit-LLM/circuit-sdk`
的 `CircuitAgent` 基类、以及高能物理领域的 PhEDEx `CircuitAgent`）。
本项目与它们**没有任何关系**，也不主张该名称的独占权。如果你的项目或商标与此冲突，
欢迎开 Issue 告知，我们可以协商改名。

## 许可证 (License)

[MIT](LICENSE) © 2026 sora
