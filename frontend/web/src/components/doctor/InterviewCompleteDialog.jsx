/**
 * InterviewCompleteDialog — shows extracted NHC fields with save / save+diagnose actions.
 *
 * Props:
 *  - open: boolean
 *  - fields: { chief_complaint: "...", present_illness: "...", _patient_name: "...", ... }
 *  - fieldCount: { filled: number, total: number }
 *  - onSave: (nameOverride?: string) => void
 *  - onSaveAndDiagnose: (nameOverride?: string) => void
 *  - onClose: () => void
 */
import { useEffect, useState } from "react";
import { Box, TextField, Typography } from "@mui/material";
import { TYPE, COLOR } from "../../theme";
import AppButton from "../AppButton";
import SheetDialog from "../SheetDialog";

const FIELD_LABELS = {
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  allergy_history: "过敏史",
  family_history: "家族史",
  personal_history: "个人史",
  marital_reproductive: "婚育史",
  physical_exam: "体格检查",
  specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查",
  diagnosis: "初步诊断",
  treatment_plan: "治疗方案",
  orders_followup: "医嘱",
  department: "科别",
};

export default function InterviewCompleteDialog({ open, fields, fieldCount, onSave, onSaveAndDiagnose, onClose }) {
  const patientName = fields?._patient_name || "";
  const patientGender = fields?._patient_gender;
  const patientAge = fields?._patient_age;

  const [nameInput, setNameInput] = useState(patientName);
  useEffect(() => { setNameInput(patientName); }, [patientName]);

  const effectiveName = nameInput.trim();
  const hasName = !!effectiveName;
  // Only pass override if the user typed a different name than what the LLM extracted
  const nameOverride = effectiveName !== patientName ? effectiveName : undefined;

  const entries = Object.entries(FIELD_LABELS)
    .map(([key, label]) => ({ key, label, value: fields?.[key] || null }));

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="病历预览"
      desktopMaxWidth={420}
      mobileMaxHeight="75vh"
      contentSx={{ pb: 1, maxHeight: "60vh" }}
      footer={
        <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <AppButton variant="secondary" size="md" fullWidth onClick={onClose}>返回</AppButton>
          <AppButton variant="secondary" size="md" fullWidth onClick={() => onSave(nameOverride)} disabled={!hasName}>保存</AppButton>
          <Box sx={{ gridColumn: "1 / -1" }}>
            <AppButton variant="primary" size="md" fullWidth onClick={() => onSaveAndDiagnose(nameOverride)} disabled={!hasName}>保存并诊断 →</AppButton>
          </Box>
        </Box>
      }
    >
        {/* Patient demographics header — editable name when missing */}
        <Box sx={{ py: 1.5, mb: 0.5, borderBottom: `1px solid ${COLOR.border}`, display: "flex", alignItems: "baseline", gap: 1 }}>
          {patientName ? (
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
              {patientName}
            </Typography>
          ) : (
            <TextField
              size="small"
              placeholder="请输入患者姓名"
              value={nameInput}
              onChange={e => setNameInput(e.target.value)}
              autoFocus
              sx={{ flex: 1, "& .MuiInputBase-input": { fontSize: TYPE.heading.fontSize, fontWeight: 600, py: 0.5 } }}
            />
          )}
          {(patientGender || patientAge) && (
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>
              {[patientGender, patientAge ? `${patientAge}岁` : null].filter(Boolean).join(" · ")}
            </Typography>
          )}
        </Box>

        {entries.length === 0 && (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, py: 2, textAlign: "center" }}>
            暂无提取到的字段
          </Typography>
        )}

        {entries.map(({ key, label, value }) => (
          <Box key={key} sx={{ py: 1, borderBottom: `1px solid ${COLOR.borderLight}` }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.3 }}>
              {label}
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: value ? COLOR.text2 : COLOR.text4, whiteSpace: "pre-wrap", lineHeight: 1.6, fontStyle: value ? "normal" : "italic" }}>
              {value || "—"}
            </Typography>
          </Box>
        ))}

        {fieldCount && (
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, textAlign: "right", mt: 1 }}>
            已提取 {fieldCount.filled}/{fieldCount.total} 字段
          </Typography>
        )}
    </SheetDialog>
  );
}
