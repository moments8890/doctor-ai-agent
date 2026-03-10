/**
 * 脑血管专科病情卡片：展示脑出血、蛛网膜下腔出血等临床专科数据。
 */
import { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import { getCvdContext } from "../../api";
import {
  CVD_SUBTYPE_LABEL, CVD_SURGERY_STATUS_LABEL, CVD_VASOSPASM_LABEL,
  CVD_HYDROCEPHALUS_LABEL, CVD_BYPASS_LABEL, CVD_PERFUSION_LABEL, MRS_COLOR,
} from "./constants";

function buildCvdRows(ctx) {
  return [
    ctx.diagnosis_subtype && ["诊断亚型", CVD_SUBTYPE_LABEL[ctx.diagnosis_subtype] || ctx.diagnosis_subtype],
    ctx.hemorrhage_location && ["出血部位", ctx.hemorrhage_location],
    ctx.gcs_score != null && ["GCS", ctx.gcs_score],
    ctx.ich_score != null && ["ICH评分", `${ctx.ich_score} 分`],
    ctx.ich_volume_ml != null && ["出血量", `${ctx.ich_volume_ml} mL`],
    ctx.hemorrhage_etiology && ["出血病因", ctx.hemorrhage_etiology],
    ctx.hunt_hess_grade != null && ["Hunt-Hess", `${ctx.hunt_hess_grade} 级`],
    ctx.fisher_grade != null && ["Fisher", `${ctx.fisher_grade} 级`],
    ctx.wfns_grade != null && ["WFNS", `${ctx.wfns_grade} 级`],
    ctx.modified_fisher_grade != null && ["改良Fisher", `${ctx.modified_fisher_grade} 级`],
    ctx.vasospasm_status && ctx.vasospasm_status !== "none" && ["血管痉挛", CVD_VASOSPASM_LABEL[ctx.vasospasm_status] || ctx.vasospasm_status],
    ctx.nimodipine_regimen && ["尼莫地平方案", ctx.nimodipine_regimen],
    ctx.hydrocephalus_status && ctx.hydrocephalus_status !== "none" && ["脑积水", CVD_HYDROCEPHALUS_LABEL[ctx.hydrocephalus_status] || ctx.hydrocephalus_status],
    ctx.spetzler_martin_grade != null && ["Spetzler-Martin", `${ctx.spetzler_martin_grade} 级`],
    ctx.aneurysm_location && ["动脉瘤位置", ctx.aneurysm_location],
    ctx.aneurysm_size_mm != null && ["动脉瘤大小", `${ctx.aneurysm_size_mm} mm`],
    ctx.aneurysm_neck_width_mm != null && ["瘤颈宽度", `${ctx.aneurysm_neck_width_mm} mm`],
    ctx.aneurysm_daughter_sac === "yes" && ["子囊", "有"],
    ctx.aneurysm_treatment && ["动脉瘤处理", ctx.aneurysm_treatment],
    ctx.phases_score != null && ["PHASES评分", `${ctx.phases_score} 分`],
    ctx.suzuki_stage != null && ["铃木分期", `${ctx.suzuki_stage} 期`],
    ctx.bypass_type && ["搭桥方式", CVD_BYPASS_LABEL[ctx.bypass_type] || ctx.bypass_type],
    ctx.perfusion_status && ["灌注状态", CVD_PERFUSION_LABEL[ctx.perfusion_status] || ctx.perfusion_status],
    ctx.surgery_type && ["手术方式", ctx.surgery_type],
    ctx.surgery_status && ["手术状态", CVD_SURGERY_STATUS_LABEL[ctx.surgery_status] || ctx.surgery_status],
    ctx.surgery_date && ["手术日期", ctx.surgery_date],
    ctx.mrs_score != null && ["mRS", ctx.mrs_score],
    ctx.barthel_index != null && ["Barthel指数", ctx.barthel_index],
  ].filter(Boolean);
}

export default function NeuroCVDContextCard({ patientId, doctorId }) {
  const [ctx, setCtx] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!patientId) return;
    getCvdContext(patientId, doctorId)
      .then((d) => { setCtx(d); setLoaded(true); })
      .catch(() => setLoaded(true));
  }, [patientId, doctorId]);

  if (!loaded || !ctx) return null;

  const rows = buildCvdRows(ctx);
  if (rows.length === 0) return null;

  return (
    <Box sx={{ bgcolor: "#fff", mb: 0.8, px: 2, pt: 1.5, pb: 1.8 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 1, gap: 0.8 }}>
        <Box sx={{ width: 3, height: 14, borderRadius: 1, bgcolor: "#009688", flexShrink: 0 }} />
        <Typography sx={{ fontSize: 13, fontWeight: 700, color: "#009688" }}>脑血管专科病情</Typography>
        <Typography sx={{ fontSize: 11, color: "#bbb", ml: "auto" }}>更新于 {ctx.created_at}</Typography>
      </Box>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: "8px 16px" }}>
        {rows.map(([label, value]) => (
          <Box key={label}>
            <Typography sx={{ fontSize: 10, color: "#999", display: "block", mb: 0.2 }}>{label}</Typography>
            <Typography sx={{ fontWeight: 600, fontSize: 13, color: label === "mRS" ? MRS_COLOR(value) : "#222" }}>
              {value}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
