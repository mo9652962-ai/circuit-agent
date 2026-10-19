# LLM 不会画线，但能设计硬件：CircuitAgent 积木化电路综合与 IPC 合规 EDA 引擎开源实录

> **作者**：mo9652962-ai  
> **开源项目**：[circuit-agent](https://github.com/mo9652962-ai/circuit-agent) (MIT License)  
> **在线 EDA 工作台**：[https://mo9652962-ai.github.io/circuit-agent/](https://mo9652962-ai.github.io/circuit-agent/)

---

## 一、为什么“让大模型直接画 PCB”注定失败？

过去一年中，大模型席卷了代码生成领域。许多开发者尝试将同样的思路套用到硬件工程：给大语言模型一段 Prompt（如“生成一个带 Type-C 的 ESP32 开发板”），期望大模型直接吐出 PCB 的焊盘坐标、铜皮走线和封装几何。

实验结果无一例外：**引脚错位、网络开路、电源直连短路、阻抗毫无物理依据**。
原因非常本质：
1. **大模型的本质是自回归序列预测器**，它擅长文本与符号关系推理，但对 2D 连续空间距离、微米级制造公差、高频电磁场寄生效应天然缺乏求解能力。
2. **硬件试错成本与软件完全不同**：软件代码有 bug 可以即时热更新；而 PCB 打样投产一旦短路，就是真实的打样费、贴片费与硬件周期损耗。

为了解决这一行业困境，我们开源了 **CircuitAgent** —— 提出 **“架构归大模型，物理归确定性编译器”** 的双层硬件设计范式。

---

## 二、CircuitAgent 的核心解法：积木化 DSL + 确定性编译器

CircuitAgent 严禁大模型直接输出底层物理坐标，而是将硬件设计抽象为经过严格工业单测的 **电路积木协议（CircuitBlocks DSL）**：

### 1. 24+ 款工业级电路积木
大模型只需扮演“系统架构师”，在系统级层面选型积木并声明互联关系：
- **微控制器核心**：ESP32-C3-WROOM-02、STM32F103C8T6、RP2040 双核；
- **电源管理系统**：Type-C 5V 诱骗输入、TPS62825 3A 同步降压、AMS1117-3.3 LDO、TP4056 锂电充放电；
- **工业总线与接口**：ISO 11898-2 CAN-FD 差分收发器、MAX485/SP3485 差分总线、W5500 SPI 以太网控制器、PC817 5kV 高压光耦隔离；
- **电机与传感**：DRV8825 45V 2.5A 细分步进电机驱动、INA219 高精度 I2C 双向电流/功率监控。

### 2. 确定性物理求解器
一旦积木拓扑确定，底层由 Python 确定性物理引擎接管计算：
- **IPC-2141A 微带线阻抗求解**：根据介质厚度 $H$、线宽 $W$、铜厚 $T$ 精准反求 $50\Omega / 90\Omega$ 目标阻抗；
- **LDO 与电源热耗散 $P_d$ 与结温 $T_j$ 预警**：根据压差与电流预估结温，防止热击穿；
- **差分对等长与时延偏斜求解**：计算 USB 2.0 / CAN-FD 时延差并输出蛇形绕线参数。

---

## 三、44 条电气与制造规则门禁 (ERC)

系统内置了 44 条严谨的电气合规检查，杜绝打样报废：
- **高压电气间隙与爬电距离**（IEC 62368-1 Table 25）：根据工作电压核算强弱电隔离距离，不足时自动报警；
- **差分总线 120Ω 终端电阻缺失审计**（MISSING_DIFF_TERMINATION）；
- **浮空引脚与多驱动冲突审计**；
- **去耦电容就近布局约束**（DECOUPLING_CAPACITOR_DEFICIT）。

---

## 四、全链工业格式直出（摆脱手动重绘）

CircuitAgent 不仅能输出网表，还打通了主流开源 EDA 制造链：
1. **KiCad 8/9/10 原生原理图 (`.kicad_sch`)**：采用标准 S-Expression 语法生成，直接在 Eeschema 中双击打开、修改与出图；
2. **Specctra 15.0 DSN 自动布局布线文件**：无缝对接 Freerouting 与 KiCad 自动布线流程；
3. **交互式装配导航网页 (`ibom.html`)**：对标 InteractiveHtmlBom，车间焊接人员可双向高亮查看焊盘与位号；
4. **立创商城实时元器件清单 (`bom_lcsc.csv`)**：自动匹配 JLC 在库常备料号，支持直接上传打样。

---

## 五、零摩擦在线体验与开源地址

- **在线 EDA 云端工作台**：[https://mo9652962-ai.github.io/circuit-agent/](https://mo9652962-ai.github.io/circuit-agent/)（纯静态无需后端，支持三栏暗黑 EDA 交互、实时网络高亮与布局缩放）；
- **MCP Server 一键接入**：
  ```bash
  uvx --from circuit-agent-client circuit-agent-mcp
  ```
- **开源仓库**：[https://github.com/mo9652962-ai/circuit-agent](https://github.com/mo9652962-ai/circuit-agent)（383 项测试全绿，MIT 协议）。
