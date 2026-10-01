# CircuitAgent 前端企业级视觉与交互重构方案（专供 Antigravity / 前端重构）

> **目标定位**：将当前单列朴素的创客 demo 页面，升级为媲美 **Linear / Vercel / Flux.ai** 的**工业级硬件 EDA 云端工作台（SaaS Dashboard）**。
> 兼顾「专业硬核感」与「现代极简美学」，大幅提升接单展示、客户交付与商业演示的说服力。

---

## 一、视觉设计语言规范 (Design System & Tokens)

### 1. 配色方案：现代硬核暗黑 / 工业浅色（推荐深色模式作为默认，突显电路与光效）
- **深色工业风（Dark Industrial - 推荐默认）**：
  - `Surface 0 (Canvas)`: `#0a0b0e`（极深冷灰黑，沉浸式底色）
  - `Surface 1 (Card/Panel)`: `#12151c`（卡片底色，带微弱冷蓝调）
  - `Surface 2 (Hover/Input)`: `#1a1f2c`（交互悬停与输入框）
  - `Border / Divider`: `rgba(255, 255, 255, 0.08)` / `#232a3b`（超细 1px 微边框）
  - `Text Primary`: `#f1f5f9`（高对比清脆白）
  - `Text Secondary / Muted`: `#94a3b8` / `#64748b`（低饱和度辅助灰）
  - `Brand Accent`: `#3b82f6`（科技电光蓝） / `#6366f1`（Indigo 强调）
  - `Status Colors`:
    - `Success / 0 DRC`: `#10b981`（翠绿光环徽标）
    - `Warning / Extended Part`: `#f59e0b`（琥珀金）
    - `Critical / Error`: `#ef4444`（警戒珊瑚红）
    - `Copper / PCB Gold`: `#eab308`（PCB 沉金质感）

### 2. 字体与排版 (Typography)
- **UI 字体**: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- **代码与数据 (Monospace)**: `"JetBrains Mono", "Fira Code", ui-monospace, monospace`（数字一律启用 `font-variant-numeric: tabular-nums`，确保表格数据严谨对齐）
- **层级**:
  - Page Title: 20px / 600 weight / letter-spacing: -0.02em
  - Section Header: 14px / 600 weight / uppercase / letter-spacing: 0.05em
  - Body: 13.5px / 400 weight / line-height: 1.5
  - Metrics / Numbers: 13px / 600 weight / Mono

---

## 二、界面布局架构重构 (Layout Architecture)

告别当前的「单列大通铺」，重构为 **经典工业 EDA 三栏工作台**：

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  Top Navbar: [CircuitAgent Pro] [Chip Selector] [Layer Badge]  [Status: 🟢 0 DRC] [Generate] │
├─────────────────────────┬──────────────────────────────────────┬───────────────────────┤
│ Left Panel: 参数与控制     │ Center Workspace: 实时工程视窗        │ Right Panel: 智能体检  │
│ (320px 紧凑侧边栏)        │ (自适应 Tab 切换大屏)                 │ 与造价核算 (340px)     │
│                         │                                      │                       │
│ 1. ✨ AI 语义生成 Prompt  │ [ 原理图 SVG ] [ PCB 走线 ] [ 3D 渲染 ] │ 1. 💰 PCBA 造价核算表 │
│ 2. 目标 MCU (STM32/ESP) │ ──────────────────────────────────── │    - 物料总计 / 换料费 │
│ 3. 硬件外设积木点选       │                                      │    - 库存警报明细      │
│ 4. 层数与阻抗开关         │ 交互式平移缩放 (Pan & Zoom) 画布      │ 2. 📜 Senior EE 审查  │
│ 5. 制造参数 (嘉立创规范)   │ 支持分层铜箔高亮、引脚测量标尺         │    - 评分徽章 (A+ 98) │
│                         │                                      │    - PI / SI / DFM    │
│                         │                                      │ 3. 📦 制造交付包下载  │
└─────────────────────────┴──────────────────────────────────────┴───────────────────────┘
```

---

## 三、五大高价值体验细节 (Key UX Enhancements)

### 1. ✨ 自然语言输入框升级为「AI Copilot 智能指令台」
- **样式**：类似 Raycast / Spotlight 的拟物悬浮框，带有柔和的电光蓝内发光（Glow Effect）；
- **快捷 Prompt 标签（Chips）**：
  - `[物联网环境采集节点 (ESP32-C3)]`
  - `[经典工业主控最小系统 (STM32F103)]`
  - `[双核高频嵌入式控制板 (RP2040)]`
  - 一键点击自动将提示词填入并高亮。

### 2. 💰 PCBA 物料与造价核算（新落地的重点呈现）
- 顶部大数字指标卡（Metric Cards）：
  - **总造价**: `¥138.22` (大字粗体)
  - **元器件成本**: `¥18.22` (24 颗)
  - **SMT 换料费**: `¥120.00` (6 种扩展库，标黄提示)
- 表格支持 **免换料费（Basic Part）绿色胶囊徽章** 与 **扩展库（Extended Part +¥20）琥珀色警告徽章**；
- 缺货元器件自动以闪烁红点提示，点击可触发替代料建议。

### 3. 📜 Senior EE 硬件体检报告（工业质感化）
- 顶部 **大圆形/环形分数进度条 (Score Donut)**：`98 / 100`，伴随柔和的墨绿色呼吸光晕；
- **四维雷达维度展开**：
  - `⚡ 电源完整性 (PI)`: 去耦电容平均物理距离 `1.85mm` (≤4.0mm 规范通过)
  - `📶 信号完整性 (SI)`: 90Ω USB 差分对等长偏差 `ΔL = 0.42mm` (≤1.0mm 规范通过)
  - `🛡️ 接口保护 (IF)`: Type-C 5.1k 下拉、复位 RC、反向续流二极管完整
  - `🏭 可制造性 (DFM)`: 4层板孔径间距 0.2mm 完美对齐嘉立创工艺。

### 4. 视觉视窗增强（Center Canvas）
- 原理图与 PCB 预览图区域支持 **全屏（Full-screen Mode）** 和 **平移缩放（Pan-Zoom）**；
- PCB 走线图提供 **图层切换开关（F.Cu 顶层 / B.Cu 底层 / In1 地 / In2 电源）**，点击可单独高亮铜皮；
- 底部悬浮快捷下载条（Glassmorphism 磨砂玻璃效果）：
  - 一键下载 `📦 jlcpcb_production_pack.zip`（直发嘉立创打样）
  - 一键下载 `📜 Senior EE 报告 (MD)` 与 `💰 造价核算单 (CSV)`。

### 5. 生成过程动态反馈（Progress Stepper）
- 不再是单调的小菊花旋转，而是展示高科技感的 **流水线状态指示器**：
  - `[✓] 1. 语义网表合成 (0.2s)`
  - `[✓] 2. 立创实时库存与单价对齐 (1.1s)`
  - `[✓] 3. 拓扑与去耦亲和性布局 (0.8s)`
  - `[⟳] 4. 四层板免穿透混合布线中 (12.4s)...`
  - `[ ] 5. Senior EE 物理审查与 3D 壳体成型`

---

## 四、技术栈与实现建议（零负担纯原生或轻量打包）

- **方案 A（保持零构建单文件，推荐）**：
  - 继续保持单文件 `web/index.html`，无需引入 npm/vite；
  - 引入 Tailwind CSS CDN（或纯原生现代 CSS Grid + Flexbox）；
  - 使用原生 Lucide Icons (SVG) 或 Phosphor Icons 增强视觉质感；
  - 配色全面采用 CSS Variables，支持平滑暗黑模式。
- **方案 B（独立现代化 SPA）**：
  - 若反重力希望工程化，可初始化一个轻量 Vite + React + Tailwind + shadcn/ui 工程，打包至 `web/dist` 后由 FastAPI 挂载。

---

## 五、交付验收标准 (Acceptance Criteria)

1. **第一眼惊艳度**：告别“学生作业感”，达到可以截图直接放在 GitHub README 首页展示的工业级审美；
2. **信息架构合理**：输入、大图预览、体检评分、造价账单三区分立，核心指标一览无余；
3. **接口 100% 兼容**：现有所有后端接口（`POST /synthesize`, `POST /runs`, `GET /parts/search`, `GET /runs/{id}/artifacts`）无缝对接，不改动后端任何核心逻辑。
