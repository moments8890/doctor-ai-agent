/**
 * InterviewCompleteDialog — shows extracted NHC fields with save / save+diagnose actions.
 *
 * Props:
 *  - open: boolean
 *  - fields: { chief_complaint: "...", present_illness: "...", ... }
 *  - fieldCount: { filled: number, total: number }
 *  - onSave: () => void
 *  - onSaveAndDiagnose: () => void
 *  - onClose: () => void
 */
import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from "@mui/material";
import { COLOR } from "../../theme";

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
  const entries = Object.entries(FIELD_LABELS)
    .filter(([key]) => fields?.[key])
    .map(([key, label]) => ({ key, label, value: fields[key] }));

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: 16, fontWeight: 600, pb: 0.5 }}>
        病历预览
      </DialogTitle>

      <DialogContent sx={{ pt: 1 }}>
        {entries.length === 0 && (
          <Typography sx={{ fontSize: 13, color: COLOR.text4, py: 2, textAlign: "center" }}>
            暂无提取到的字段
          </Typography>
        )}

        {entries.map(({ key, label, value }) => (
          <Box key={key} sx={{ py: 0.8, borderBottom: `1px solid ${COLOR.borderLight}` }}>
            <Typography sx={{ fontSize: 12, color: COLOR.text4, mb: 0.3 }}>
              {label}
            </Typography>
            <Typography sx={{ fontSize: 13, color: COLOR.text2, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
              {value}
            </Typography>
          </Box>
        ))}

        {/* Field count */}
        {fieldCount && (
          <Typography variant="caption" sx={{ display: "block", mt: 1, color: COLOR.text4, textAlign: "right" }}>
            已提取 {fieldCount.filled}/{fieldCount.total} 字段
          </Typography>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button
          onClick={onClose}
          sx={{ fontSize: 14, color: COLOR.text4 }}
        >
          返回
        </Button>
        <Button
          variant="outlined"
          onClick={onSave}
          sx={{ flex: 1, fontSize: 14, borderColor: COLOR.border, color: COLOR.text2 }}
        >
          保存
        </Button>
        <Button
          variant="contained"
          disableElevation
          onClick={onSaveAndDiagnose}
          sx={{
            flex: 1, fontSize: 14,
            bgcolor: "#07C160",
            color: "#fff",
            "&:hover": { bgcolor: "#06ad56" },
          }}
        >
          保存并诊断 →
        </Button>
      </DialogActions>
    </Dialog>
  );
}
