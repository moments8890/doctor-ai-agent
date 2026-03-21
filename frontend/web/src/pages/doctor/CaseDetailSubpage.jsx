import { useState, useEffect } from "react";
import { Box, Typography, CircularProgress } from "@mui/material";
import SubpageHeader from "../../pages/doctor/SubpageHeader";
import { getCaseDetail } from "../../api";
import { TYPE } from "../../theme";

export default function CaseDetailSubpage({ caseId, doctorId, onBack }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCaseDetail(caseId, doctorId)
      .then(setDetail)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [caseId, doctorId]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
        <SubpageHeader title="病例详情" onBack={onBack} />
        <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <CircularProgress size={20} />
        </Box>
      </Box>
    );
  }

  if (!detail) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
        <SubpageHeader title="病例详情" onBack={onBack} />
        <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Typography color="text.secondary">未找到病例</Typography>
        </Box>
      </Box>
    );
  }

  const fields = [
    ["主诉", detail.chief_complaint],
    ["现病史", detail.present_illness],
    ["最终诊断", detail.final_diagnosis],
    ["治疗方案", detail.treatment],
    ["结局", detail.outcome],
    ["备注", detail.notes],
  ].filter(([, v]) => v);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title="病例详情" onBack={onBack} />
      <Box sx={{ flex: 1, overflowY: "auto", p: 1.5 }}>
        {/* Status banner */}
        <Box sx={{ bgcolor: "#E8F5E9", borderLeft: "3px solid #07C160", borderRadius: "6px", p: 1.5, mb: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 500, color: "#1A1A1A" }}>
            已确认 — 此病例正在参与AI诊断推理
          </Typography>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#666", mt: 0.3 }}>
            AI引用 {detail.reference_count || 0}次
            {detail.created_at && ` · ${detail.created_at.slice(0, 10)}`}
          </Typography>
        </Box>

        {/* Field cards */}
        {fields.map(([label, value]) => (
          <Box key={label} sx={{ bgcolor: "#fff", borderRadius: "6px", p: 2, mb: 1, border: "0.5px solid #E5E5E5" }}>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }}>{label}</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#1A1A1A", mt: 0.5, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
              {value}
            </Typography>
          </Box>
        ))}

        {/* Embedding status */}
        <Box sx={{ bgcolor: "#fff", borderRadius: "6px", p: 2, border: "0.5px solid #E5E5E5", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Box>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>向量索引</Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: detail.embedding_model ? "#07C160" : "#E8533F", mt: 0.3 }}>
              {detail.embedding_model ? `已索引 · ${detail.embedding_model}` : "未索引"}
            </Typography>
          </Box>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }}>用于相似病例匹配</Typography>
        </Box>
      </Box>
    </Box>
  );
}
