# CircuitAgent Community Client & Specification (CircuitAgent 社区版)

> **CircuitAgent** 是一个由 AI 驱动的全流程硬件合成系统（Prompt → Schematic → Layout → 3D Enclosure → Fabrication Bundle）。
> 本仓库为 **开源协议、客户端 SDK、MCP 服务端及数据规范（Public Community Edition）**。
> 包含自然语言硬件 DSL（CircuitBlocks）、立创元器件实时选型查询客户端、标准网表数据模型及 REST/MCP 交互接口。

---

## 🌟 核心特性 (Features)

- **自然语言硬件积木 DSL (CircuitBlocks)**:
  - 将自然语言需求映射为确定性硬件电路块（如 Type-C 供电、LDO 降压、晶振电路、RC 复位、消抖按键、I2C 传感器接口等）；
  - 避免大语言模型直接生成非法底层走线或产生引脚短路。
- **立创商城 / LCSC 免 Key 动态元器件查询客户端**:
  - 提供轻量级元器件检索接口，毫秒级提取料号（LCSC C号）、封装、单价与在库库存；
  - 自动识别嘉立创基础库（Basic Part）与扩展库（Extended Part），提供 PCBA 成本预算。
- **标准化数据契约 (Data Contracts)**:
  - 规范化的 `Netlist`、`PinAssignment`、`ModuleSpecification` 模型，严格基于 Pydantic 驱动；
  - 导出符合 JLCPCB SMT 贴片要求的标准 BOM 与 CPL 坐标格式。
- **双模通信支持 (REST API + MCP Server)**:
  - 提供标准的 FastAPI Web 接口；
  - 内置 Model Context Protocol (MCP) 接口，可无缝接入 Claude Desktop、Cursor、Hermes 等 AI Agent 环境。

---

## 🏗️ 架构概览 (Architecture Overview)

```text
       [Natural Language / Prompt]
                   │
                   ▼
       ┌────────────────────────┐
       │   CircuitBlocks DSL    │ ── (Natural Language to Hardware Blocks)
       └────────────────────────┘
                   │
                   ▼
       ┌────────────────────────┐
       │     Pydantic SSOT      │ ── (Strict Netlist & Module Specifications)
       └────────────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────────┐ ┌──────────────────┐
│ LCSC Live Client │ │ MCP / REST APIs  │
└──────────────────┘ └──────────────────┘
```

> **注意 (Note)**:
> 涉及高精度多层板物理布局布线求解器、FreeCAD 参数化 3D 壳体布尔几何切削引擎、以及 Senior EE 规则门禁的物理仿真后端属于闭源工业核心资产，本仓库提供完整的社区版数据交换协议与本地/远程客户端调用实现。

---

## 🚀 快速上手 (Quick Start)

### 1. 环境准备
```bash
git clone https://github.com/mo9652962-ai/circuit-agent.git
cd circuit-agent
pip install -r requirements.txt
```

### 2. 本地检索立创商城元器件
```python
from client.lcsc_client import search_lcsc_parts

# 搜索指定元器件
results = search_lcsc_parts("CH340N", limit=3)
for part in results:
    print(f"[{part['part_number']}] {part['title']} | 封装: {part['package']} | 库存: {part['stock']}")
```

### 3. 自然语言生成硬件网表
```python
from client.synthesizer import synthesize_from_prompt

# 一句话生成基于 ESP32-C3 的温湿度采集节点
spec = synthesize_from_prompt("基于 ESP32-C3 的环境监测节点，带 Type-C 供电、I2C 传感器插座、2个按键")
print("生成的引脚网络与元器件数:", len(spec["modules"]))
```

---

## 📦 规范契约 (Specifications)

- `specs/netlist_schema.json`: 标准电路网表 JSON Schema 约束；
- `specs/cpl_standard.md`: 嘉立创 SMT 坐标规范与各芯片封装角度补偿表；
- `examples/`: 经典微控制器（STM32F103、ESP32-C3、RP2040）的标准网表输入参考样例。

---

## 📄 开源许可证 (License)

本项目基于 [MIT License](LICENSE) 开源。欢迎社区开发者提交 Issue 与 PR 扩充 CircuitBlocks 硬件积木库！
