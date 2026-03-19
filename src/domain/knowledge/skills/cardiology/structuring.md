---
name: cardiology-structuring
description: 心内科病历结构化规则
type: structuring
specialty: cardiology
---

# 心内科结构化规则

## 必须保留的专科缩写
STEMI, NSTEMI, PCI, CABG, BNP, NT-proBNP, EF, LVEF, NYHA, ACC/AHA, CCS,
TnI, TnT, CK-MB, ECG, Holter, IABP, ECMO, ICD, CRT, CRT-D

## 关键临床参数
- 心功能分级（NYHA I-IV）必须保留原始分级
- 射血分数（EF/LVEF）百分比数值
- BNP/NT-proBNP 数值及单位
- 血压数值（收缩压/舒张压 mmHg）
- 心率数值（次/分）

## 药物规范
- 抗血小板：阿司匹林、氯吡格雷、替格瑞洛（含剂量/频次）
- 他汀类：阿托伐他汀、瑞舒伐他汀（含剂量）
- ACEI/ARB：培哚普利、缬沙坦等（含剂量）
- β受体阻滞剂：美托洛尔、比索洛尔（含剂量）
- 抗凝药：华法林（含 INR 目标）、利伐沙班、达比加群

## 风险评分
- GRACE 评分、TIMI 评分、CHADS₂-VASc 评分、HAS-BLED 评分
- 保留原始数值，标注在 specialty_scores 中

## 介入记录关键信息
- 靶血管（如 LAD、LCx、RCA）
- 支架类型和尺寸
- 术中并发症
- 术后 TIMI 血流分级
