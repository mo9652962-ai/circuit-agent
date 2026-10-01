# JLCPCB SMT CPL (Component Placement List) 坐标规范与各芯片偏角补偿约定

在将 KiCad 导出的原始元件位置文件（POS）转换为嘉立创 SMT 生产所需的 CPL 坐标时，需遵循以下标准转换规则：

---

## 1. 坐标系转换 (Coordinate System)

- **KiCad POS 坐标系**: 左上角为原点，Y 轴向下为正；
- **嘉立创 CPL 坐标系**: 笛卡尔坐标系，Y 轴向上为正；
- **转换公式**: 
  $$Y_{\text{CPL}} = -Y_{\text{KiCad}}$$

---

## 2. 封装编带旋转角补偿规则 (Rotation Compensation)

由于 KiCad 封装的原点/编带方向与嘉立创供料盘（Tape & Reel）方向存在差异，必须进行角度修正：

| 封装类别 | 正则表达式匹配 | 补偿角度 (Offset) | 示例器件 |
|:---|:---|:---:|:---|
| **0402 / 0603 / 0805 阻容** | `r"^(R|C|L)[0-9]+"` | **0°** | 常用贴片阻容感 |
| **QFN / DFN 系列** | `r"(^|[_:])(QFN|DFN)[-_]"` | **+270°** | RP2040, ESP32-C3 |
| **LQFP / TQFP / SOP 系列** | `r"(^|[_:])(LQFP|TQFP|SOP|SOIC|TSSOP)[-_]"` | **+270°** | STM32F103, CH340N |
| **SOT-23 / SOD-123 晶体管二极管** | `r"(^|[_:])(SOT[-_]23|SOT[-_]223|SOD[-_]123)"` | **+180°** | S8050, 1N4148W |
| **贴片微动按键** | `r"(^|[_:])(SW[-_]|Button)"` | **+90°** | 3x6 贴片轻触按键 |

---

## 3. 标准 CPL 表头定义
```csv
Designator,Val,Package,Mid X,Mid Y,Rotation,Layer
U1,STM32F103C8T6,LQFP-48_7x7mm_P0.5mm,27.75,-27.75,270.00,Top
C1,100nF,C_0603_1608Metric,20.42,-22.13,0.00,Top
```
