/**
 * @route /debug/doctor-components
 *
 * Doctor sub-component showcase — components from components/doctor/.
 * Grouped with collapsible sections.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../../theme";
import AppButton from "../AppButton";

import DiagnosisCard from "./DiagnosisCard";
import FieldReviewCard from "./FieldReviewCard";
import InterviewCompleteDialog from "./InterviewCompleteDialog";

/* ── Helpers ── */

function Section({ title, file, children }) {
  return (
    <Box sx={{ mb: 3, borderLeft: `3px solid ${COLOR.primary}`, pl: 1.5 }}>
      <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, mb: 0.3 }}>{title}</Typography>
      <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1, fontFamily: "monospace" }}>{file}</Typography>
      <Box sx={{ border: `1px solid ${COLOR.border}`, borderRadius: 1, p: 1.5, bgcolor: COLOR.white }}>
        {children}
      </Box>
    </Box>
  );
}

function Group({ title, count, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Box sx={{ mb: 2 }}>
      <Box onClick={() => setOpen(!open)} sx={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        py: 1.2, px: 1.5, bgcolor: COLOR.white, borderRadius: 1, cursor: "pointer",
        border: `1px solid ${COLOR.border}`, "&:active": { bgcolor: COLOR.surface },
      }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 700 }}>{title}</Typography>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, bgcolor: COLOR.surface, px: 0.8, borderRadius: 1 }}>{count}</Typography>
        </Box>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary }}>{open ? "收起 ▴" : "展开 ▾"}</Typography>
      </Box>
      {open && <Box sx={{ mt: 1.5 }}>{children}</Box>}
    </Box>
  );
}

/* ── Main ── */

export default function DoctorComponentShowcase() {
  const [dialogOpen, setDialogOpen] = useState(false);

  const mockSuggestion = { id: 1, section: "differential", content: "蛛网膜下腔出血", detail: "突发雷击样头痛，伴颈部僵硬，符合SAH典型表现。需立即头颅CT排除。", confidence: "高", decision: null, is_custom: false };
  const mockConfirmed = { ...mockSuggestion, id: 2, content: "高血压性头晕", confidence: "中", decision: "confirmed" };
  const mockRejected = { ...mockSuggestion, id: 3, content: "偏头痛", confidence: "低", decision: "rejected" };
  const mockEdited = { ...mockSuggestion, id: 4, content: "脑动脉瘤破裂", decision: "edited", edited_text: "医生修改内容" };
  const mockCustom = { id: 5, section: "differential", content: "颅内静脉窦血栓", detail: "口服避孕药史", decision: "custom", is_custom: true };
  const mockWorkup = { id: 6, section: "workup", content: "头颅MRA", detail: "评估椎基底动脉血流。", urgency: "紧急", decision: null, is_custom: false };
  const mockTreatment = { id: 7, section: "treatment", content: "钙通道阻滞剂", detail: "优化降压方案。", intervention: "药物", decision: null, is_custom: false };

  return (
    <Box sx={{ height: "100%", overflowY: "auto", bgcolor: COLOR.surfaceAlt, p: 1.5 }}>
      <Typography sx={{ fontSize: 18, fontWeight: 700, mb: 0.3 }}>Doctor Components</Typography>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 2 }}>
        components/doctor/ — 3 components
      </Typography>

      {/* ═══════ Diagnosis ═══════ */}
      <Group title="Diagnosis" count={1} defaultOpen={true}>
        <Section title="DiagnosisCard — 8 states" file="DiagnosisCard.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Unreviewed:</Typography>
          <DiagnosisCard suggestion={mockSuggestion} expanded={false} onToggle={() => {}} onDecide={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Expanded (排除|修改|确认):</Typography>
          <DiagnosisCard suggestion={mockSuggestion} expanded={true} onToggle={() => {}} onDecide={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Confirmed:</Typography>
          <DiagnosisCard suggestion={mockConfirmed} expanded={false} onToggle={() => {}} onDecide={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Rejected:</Typography>
          <DiagnosisCard suggestion={mockRejected} expanded={false} onToggle={() => {}} onDecide={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Edited:</Typography>
          <DiagnosisCard suggestion={mockEdited} expanded={false} onToggle={() => {}} onDecide={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Custom:</Typography>
          <DiagnosisCard suggestion={mockCustom} expanded={false} onToggle={() => {}} onDecide={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Workup (紧急):</Typography>
          <DiagnosisCard suggestion={mockWorkup} expanded={false} onToggle={() => {}} onDecide={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Treatment (药物):</Typography>
          <DiagnosisCard suggestion={mockTreatment} expanded={false} onToggle={() => {}} onDecide={() => {}} />
        </Section>
      </Group>

      {/* ═══════ Interview ═══════ */}
      <Group title="Interview" count={2}>
        <Section title="FieldReviewCard" file="FieldReviewCard.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Collapsed (tap to expand):</Typography>
          <FieldReviewCard
            title="上次记录 (2026-03-20)" subtitle="3 项可沿用"
            items={[
              { field: "past_history", label: "既往史", value: "高血压5年，服用氨氯地平" },
              { field: "allergy_history", label: "过敏史", value: "磺胺类药物过敏" },
              { field: "family_history", label: "家族史", value: "母亲糖尿病" },
            ]}
            onConfirm={() => {}} onDismiss={() => {}} onConfirmAll={() => {}} onDismissAll={() => {}}
          />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Expanded (editable):</Typography>
          <FieldReviewCard
            title="已从拍照导入" subtitle="2 项已识别" defaultCollapsed={false} editable
            items={[
              { field: "chief_complaint", label: "主诉", value: "头痛3天伴恶心呕吐" },
              { field: "past_history", label: "既往史", value: "高血压10年，糖尿病5年" },
            ]}
            confirmLabel="确认" dismissLabel="编辑" confirmAllLabel="全部确认" dismissAllLabel="全部忽略"
            onConfirm={() => {}} onEdit={() => {}} onConfirmAll={() => {}} onDismissAll={() => {}}
          />
        </Section>

        <Section title="InterviewCompleteDialog" file="InterviewCompleteDialog.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Triggered by "完成" in interview:</Typography>
          <AppButton variant="primary" size="sm" onClick={() => setDialogOpen(true)}>完成</AppButton>
          <InterviewCompleteDialog
            open={dialogOpen}
            fields={{ chief_complaint: "头痛3天伴恶心呕吐", present_illness: "3天前无明显诱因", past_history: "高血压5年", allergy_history: "磺胺类过敏" }}
            fieldCount={{ filled: 4, total: 14 }}
            onSave={() => setDialogOpen(false)} onSaveAndDiagnose={() => setDialogOpen(false)} onClose={() => setDialogOpen(false)}
          />
        </Section>
      </Group>

      {/* Navigation links */}
      <Box sx={{ display: "flex", gap: 1, justifyContent: "center", mt: 2, mb: 4 }}>
        <Box onClick={() => window.location.href = "/debug/components"}
          sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.accent, cursor: "pointer", textDecoration: "underline" }}>
          Shared Components
        </Box>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>·</Typography>
        <Box onClick={() => window.location.href = "/debug/doctor"}
          sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.accent, cursor: "pointer", textDecoration: "underline" }}>
          Mock Pages
        </Box>
      </Box>
    </Box>
  );
}
