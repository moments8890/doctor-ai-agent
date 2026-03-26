/**
 * @route /debug/doctor-components
 *
 * Doctor sub-component showcase — visual reference for all components
 * in pages/doctor/components/. Each component rendered in isolation.
 */
import { useState } from "react";
import { Box, Typography, TextField } from "@mui/material";
import { TYPE, ICON, COLOR } from "../../../theme";

import ActionPanel from "./ActionPanel";
import BriefingCard from "./BriefingCard";
import CarryForwardCard from "./CarryForwardCard";
import DiagnosisCard from "./DiagnosisCard";
import InterviewCompleteDialog from "./InterviewCompleteDialog";
import WorkingContextHeader from "./WorkingContextHeader";

/* ── Helpers ── */

function Section({ title, file, children }) {
  return (
    <Box sx={{ mb: 4 }}>
      <Typography sx={{ fontSize: 16, fontWeight: 700, mb: 0.5 }}>{title}</Typography>
      <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1.5, fontFamily: "monospace" }}>
        pages/doctor/components/{file}
      </Typography>
      <Box sx={{ border: `1px solid ${COLOR.border}`, borderRadius: 2, p: 2, bgcolor: COLOR.white }}>
        {children}
      </Box>
    </Box>
  );
}

/* ── Main ── */

export default function DoctorComponentShowcase() {
  const [dialogOpen, setDialogOpen] = useState(false);

  const mockSuggestionUnreviewed = {
    id: 1, section: "differential",
    content: "蛛网膜下腔出血",
    detail: "突发雷击样头痛，伴颈部僵硬，符合SAH典型表现。需立即头颅CT排除。",
    confidence: "高", decision: null, is_custom: false,
  };
  const mockSuggestionConfirmed = {
    ...mockSuggestionUnreviewed, id: 2,
    content: "高血压性头晕", confidence: "中", decision: "confirmed",
  };
  const mockSuggestionRejected = {
    ...mockSuggestionUnreviewed, id: 3,
    content: "偏头痛", confidence: "低", decision: "rejected",
  };
  const mockSuggestionEdited = {
    ...mockSuggestionUnreviewed, id: 4,
    content: "脑动脉瘤破裂", decision: "edited",
    edited_text: "医生修改后的诊断描述",
  };
  const mockSuggestionCustom = {
    id: 5, section: "differential",
    content: "颅内静脉窦血栓",
    detail: "口服避孕药史，需MRV排除",
    decision: "custom", is_custom: true,
  };

  const mockWorkup = {
    id: 6, section: "workup",
    content: "头颅MRA",
    detail: "评估椎基底动脉血流，帮助外科医生制定手术方案。",
    urgency: "紧急", decision: null, is_custom: false,
  };

  const mockTreatment = {
    id: 7, section: "treatment",
    content: "钙通道阻滞剂",
    detail: "优化降压方案，控制血压波动。",
    intervention: "药物", decision: null, is_custom: false,
  };

  return (
    <Box sx={{ maxWidth: 480, mx: "auto", p: 2, bgcolor: "#f5f5f5", minHeight: "100vh" }}>
      <Typography sx={{ fontSize: 22, fontWeight: 700, mb: 0.5 }}>Doctor Sub-Components</Typography>
      <Typography sx={{ fontSize: 13, color: COLOR.text4, mb: 3 }}>
        Components in pages/doctor/components/. Visit: /debug/doctor-components
      </Typography>

      {/* ── WorkingContextHeader ── */}
      <Section title="WorkingContextHeader" file="WorkingContextHeader.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>With patient context:</Typography>
        <WorkingContextHeader context={{ patient_name: "李复诊", pending_draft: true }} isMobile={true} />
        <Box sx={{ mt: 1.5 }} />
        <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>No context:</Typography>
        <WorkingContextHeader context={null} isMobile={true} />
      </Section>

      {/* ── BriefingCard ── */}
      <Section title="BriefingCard" file="BriefingCard.jsx">
        <BriefingCard title="今日患者" value={5} color={COLOR.primary} onClick={() => {}} />
        <Box sx={{ mt: 1 }} />
        <BriefingCard title="待办任务" value={3} color={COLOR.primary} onClick={() => {}} />
        <Box sx={{ mt: 1 }} />
        <BriefingCard title="已完成" value={0} onClick={() => {}} />
      </Section>

      {/* ── DiagnosisCard — all 5 states ── */}
      <Section title="DiagnosisCard — 5 States + Workup + Treatment" file="DiagnosisCard.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Unreviewed (collapsed):</Typography>
        <DiagnosisCard suggestion={mockSuggestionUnreviewed} expanded={false} onToggle={() => {}} onDecide={() => {}} />

        <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 2, mb: 1 }}>Expanded with actions (排除 | 修改 | 确认):</Typography>
        <DiagnosisCard suggestion={mockSuggestionUnreviewed} expanded={true} onToggle={() => {}} onDecide={() => {}} />

        <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 2, mb: 1 }}>Confirmed:</Typography>
        <DiagnosisCard suggestion={mockSuggestionConfirmed} expanded={false} onToggle={() => {}} onDecide={() => {}} />

        <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 2, mb: 1 }}>Rejected:</Typography>
        <DiagnosisCard suggestion={mockSuggestionRejected} expanded={false} onToggle={() => {}} onDecide={() => {}} />

        <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 2, mb: 1 }}>Edited:</Typography>
        <DiagnosisCard suggestion={mockSuggestionEdited} expanded={false} onToggle={() => {}} onDecide={() => {}} />

        <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 2, mb: 1 }}>Doctor-added (custom):</Typography>
        <DiagnosisCard suggestion={mockSuggestionCustom} expanded={false} onToggle={() => {}} onDecide={() => {}} />

        <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 2, mb: 1 }}>Workup (紧急):</Typography>
        <DiagnosisCard suggestion={mockWorkup} expanded={false} onToggle={() => {}} onDecide={() => {}} />

        <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 2, mb: 1 }}>Treatment (药物):</Typography>
        <DiagnosisCard suggestion={mockTreatment} expanded={false} onToggle={() => {}} onDecide={() => {}} />
      </Section>

      {/* ── CarryForwardCard ── */}
      <Section title="CarryForwardCard" file="CarryForwardCard.jsx">
        <CarryForwardCard
          items={[
            { field: "past_history", label: "既往史", value: "高血压5年，服用氨氯地平" },
            { field: "allergy_history", label: "过敏史", value: "磺胺类药物过敏" },
            { field: "family_history", label: "家族史", value: "母亲糖尿病" },
          ]}
          onConfirm={() => {}}
          onDismiss={() => {}}
          onConfirmAll={() => {}}
        />
      </Section>

      {/* ── InterviewCompleteDialog ── */}
      <Section title="InterviewCompleteDialog" file="InterviewCompleteDialog.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Tap button to preview:</Typography>
        <Box
          onClick={() => setDialogOpen(true)}
          sx={{
            py: 1, textAlign: "center", borderRadius: 1,
            border: `1px dashed ${COLOR.primary}`, color: COLOR.primary,
            fontSize: TYPE.body.fontSize, cursor: "pointer",
          }}
        >
          打开病历预览对话框
        </Box>
        <InterviewCompleteDialog
          open={dialogOpen}
          fields={{
            chief_complaint: "头痛3天伴恶心呕吐",
            present_illness: "3天前无明显诱因出现持续性头痛",
            past_history: "高血压5年",
            allergy_history: "磺胺类药物过敏",
          }}
          fieldCount={{ filled: 4, total: 14 }}
          onSave={() => setDialogOpen(false)}
          onSaveAndDiagnose={() => setDialogOpen(false)}
          onClose={() => setDialogOpen(false)}
        />
      </Section>

      {/* ── ActionPanel ── */}
      <Section title="ActionPanel" file="ActionPanel.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>
          ⊕ action menu shown in chat — renders as overlay. Preview only:
        </Typography>
        <Box sx={{ display: "flex", gap: 2, justifyContent: "center", py: 1 }}>
          {[
            { label: "拍照", color: COLOR.primary },
            { label: "相册", color: COLOR.accent },
            { label: "文档", color: COLOR.warning },
            { label: "患者", color: "#9b59b6" },
          ].map((a) => (
            <Box key={a.label} sx={{ textAlign: "center" }}>
              <Box sx={{ width: 44, height: 44, borderRadius: 2, bgcolor: a.color, mx: "auto", mb: 0.5, opacity: 0.15 }} />
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text3 }}>{a.label}</Typography>
            </Box>
          ))}
        </Box>
      </Section>

      <Box sx={{ height: 40 }} />
    </Box>
  );
}
