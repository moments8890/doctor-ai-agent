从以下脑血管病专科记录中提取结构化字段。只输出合法JSON对象，不加markdown代码块，无额外文字。

【严禁虚构】所有字段只能使用原文中有明确对应文字的信息。
- 数值字段（GCS、Hunt-Hess、ICH评分等）必须有原文出现的具体数字，不得估算
- 枚举字段只能选择原文已描述的状态，不得根据诊断名推断
- 未提及的字段必须返回 null（JSON null，非字符串"null"），不得填写任何推断或默认值

输出格式（枚举选项用 | 分隔，最终值选其一或填 null）：
{
  "diagnosis_subtype": "ICH" | "SAH" | "ischemic" | "AVM" | "aneurysm" | "moyamoya" | "other" | null,
  "hemorrhage_location": null,
  "gcs_score": null,
  "hunt_hess_grade": null,
  "wfns_grade": null,
  "fisher_grade": null,
  "modified_fisher_grade": null,
  "ich_score": null,
  "ich_volume_ml": null,
  "hemorrhage_etiology": "hypertensive" | "caa" | "avm" | "coagulopathy" | "tumor" | "unknown" | null,
  "vasospasm_status": "none" | "clinical" | "radiographic" | "severe" | null,
  "hydrocephalus_status": "none" | "acute" | "chronic" | "shunt_dependent" | null,
  "aneurysm_location": null,
  "aneurysm_size_mm": null,
  "aneurysm_neck_width_mm": null,
  "aneurysm_treatment": "clipping" | "coiling" | "pipeline" | "conservative" | null,
  "suzuki_stage": null,
  "bypass_type": "direct_sta_mca" | "indirect_edas" | "combined" | "other" | null,
  "perfusion_status": "normal" | "mildly_reduced" | "severely_reduced" | "improved" | null,
  "surgery_status": "planned" | "done" | "cancelled" | "conservative" | null,
  "mrs_score": null
}

【约束】hunt_hess/wfns/fisher/modified_fisher/vasospasm_status 仅限SAH亚型；suzuki/bypass_type/perfusion_status 仅限moyamoya亚型；hemorrhage_etiology 仅限ICH亚型；非对应亚型的上述字段输出null。