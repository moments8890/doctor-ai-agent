/**
 * @route /debug/components
 *
 * Component Showcase — visual reference for all shared UI components.
 *
 * Each component rendered in isolation on a clean background with
 * its name, file path, and key props demonstrated.
 */
import { useState } from "react";
import { Box, Typography, TextField } from "@mui/material";
import { TYPE, ICON, COLOR } from "../../theme";

// Shared components
import AppButton from "../../components/AppButton";
import AskAIBar from "../../components/AskAIBar";
import CancelConfirm from "../../components/CancelConfirm";
import BarButton from "../../components/BarButton";
import BottomSheet from "../../components/BottomSheet";
import DetailCard from "../../components/DetailCard";
import EmptyState from "../../components/EmptyState";
import ListCard from "../../components/ListCard";
import NewItemCard from "../../components/NewItemCard";
import RecordAvatar from "../../components/RecordAvatar";
import RecordFields from "../../components/RecordFields";
import SectionLabel from "../../components/SectionLabel";
import StatusBadge from "../../components/StatusBadge";
import SuggestionChips from "../../components/SuggestionChips";
import FilterBar from "../../components/FilterBar";

// Page-level components
import SubpageHeader from "../../components/SubpageHeader";
// Newly moved shared components
import PatientAvatar from "../../components/PatientAvatar";
import RecordCard from "../../components/RecordCard";
import RecordEditDialog from "../../components/RecordEditDialog";
import ExportSelectorDialog from "../../components/ExportSelectorDialog";
import ImportChoiceDialog from "../../components/ImportChoiceDialog";
import PatientPickerDialog from "../../components/PatientPickerDialog";
import VoiceInput from "../../components/VoiceInput";
import DoctorBubble from "../../components/DoctorBubble";
import TaskChecklist from "../../components/TaskChecklist";

// Icons for demos
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";

/* ── Helpers ── */

function Section({ title, file, children }) {
  return (
    <Box sx={{ mb: 4 }}>
      <Typography sx={{ fontSize: 16, fontWeight: 700, mb: 0.5 }}>{title}</Typography>
      <Typography sx={{ fontSize: 11, color: "#999", mb: 1.5, fontFamily: "monospace" }}>{file}</Typography>
      <Box sx={{ border: "1px solid #e5e5e5", borderRadius: 2, p: 2, bgcolor: "#fff" }}>
        {children}
      </Box>
    </Box>
  );
}

function ColorSwatch({ name, hex }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
      <Box sx={{ width: 24, height: 24, borderRadius: 1, bgcolor: hex, border: "1px solid #e5e5e5" }} />
      <Typography sx={{ fontSize: 12, fontFamily: "monospace" }}>{name} {hex}</Typography>
    </Box>
  );
}

/* ── Main ── */

export default function ComponentShowcasePage() {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [selectedChips, setSelectedChips] = useState([]);

  // DiagnosisCard and doctor-specific components: see /debug/doctor-components

  return (
    <Box sx={{ maxWidth: 480, mx: "auto", p: 2, bgcolor: "#f5f5f5", minHeight: "100vh" }}>
      <Typography sx={{ fontSize: 22, fontWeight: 700, mb: 0.5 }}>Component Showcase</Typography>
      <Typography sx={{ fontSize: 13, color: "#999", mb: 3 }}>All shared UI components rendered in isolation. Visit: /debug/components</Typography>

      {/* ── Colors ── */}
      <Section title="Color Tokens" file="src/theme.js → COLOR">
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1 }}>
          <ColorSwatch name="primary" hex={COLOR.primary} />
          <ColorSwatch name="accent" hex={COLOR.accent} />
          <ColorSwatch name="success" hex={COLOR.success} />
          <ColorSwatch name="danger" hex={COLOR.danger} />
          <ColorSwatch name="warning" hex={COLOR.warning} />
          <ColorSwatch name="text1" hex={COLOR.text1} />
          <ColorSwatch name="text2" hex={COLOR.text2} />
          <ColorSwatch name="text3" hex={COLOR.text3} />
          <ColorSwatch name="text4" hex={COLOR.text4} />
          <ColorSwatch name="border" hex={COLOR.border} />
          <ColorSwatch name="surface" hex={COLOR.surface} />
          <ColorSwatch name="surfaceAlt" hex={COLOR.surfaceAlt} />
        </Box>
      </Section>

      {/* ── Typography ── */}
      <Section title="Typography Scale" file="src/theme.js → TYPE">
        {Object.entries(TYPE).map(([key, { fontSize, fontWeight }]) => (
          <Typography key={key} sx={{ fontSize, fontWeight, mb: 0.5 }}>
            {key} — {fontSize}px / {fontWeight} — 医生AI助手示例文字
          </Typography>
        ))}
      </Section>

      {/* ── AppButton ── */}
      <Section title="AppButton" file="src/components/AppButton.jsx">
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <AppButton variant="primary">保存</AppButton>
          <AppButton variant="secondary">取消</AppButton>
          <AppButton variant="danger">删除</AppButton>
          <AppButton variant="primary" disabled>禁用</AppButton>
        </Box>
      </Section>

      {/* ── BarButton ── */}
      <Section title="BarButton" file="src/components/BarButton.jsx">
        <Box sx={{ display: "flex", gap: 2, alignItems: "center", bgcolor: "#fff", px: 2, py: 1, borderRadius: 1 }}>
          <BarButton>门诊</BarButton>
          <BarButton>清空</BarButton>
          <BarButton color="#999">导出</BarButton>
        </Box>
      </Section>

      {/* ── CancelConfirm ── */}
      <Section title="CancelConfirm" file="src/components/CancelConfirm.jsx">
        <Typography sx={{ fontSize: 11, color: "#999", mb: 1 }}>Two-step cancel — prevents accidental data loss:</Typography>
        <CancelConfirm open={false} onConfirm={() => {}} onCancel={() => {}} />
        <Box sx={{ border: "1px solid #e5e5e5", borderRadius: "12px", p: 3, textAlign: "center" }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, mb: 0.5 }}>确认离开？</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 2.5 }}>未保存的内容将会丢失</Typography>
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Box sx={{ flex: 1, py: 1, textAlign: "center", borderRadius: "4px", fontSize: TYPE.body.fontSize, color: COLOR.danger, border: `0.5px solid ${COLOR.border}` }}>确认</Box>
            <Box sx={{ flex: 1, py: 1, textAlign: "center", borderRadius: "4px", fontSize: TYPE.body.fontSize, fontWeight: 600, color: "#fff", bgcolor: COLOR.primary }}>返回</Box>
          </Box>
        </Box>
      </Section>

      {/* ── SubpageHeader ── */}
      <Section title="SubpageHeader" file="src/pages/doctor/SubpageHeader.jsx">
        <SubpageHeader title="李复诊" onBack={() => {}} right={<BarButton>门诊</BarButton>} />
      </Section>

      {/* ── ListCard ── */}
      <Section title="ListCard" file="src/components/ListCard.jsx">
        <ListCard
          avatar={<Box sx={{ width: 36, height: 36, borderRadius: 1, bgcolor: COLOR.primary, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 14, fontWeight: 600 }}>李</Box>}
          title="李复诊"
          subtitle="女 · 56岁 · 1份病历"
          right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>今天 05:32</Typography>}
        />
        <Box sx={{ borderTop: "0.5px solid #f0f0f0" }} />
        <ListCard
          avatar={<Box sx={{ width: 36, height: 36, borderRadius: 1, bgcolor: "#9b59b6", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 14, fontWeight: 600 }}>张</Box>}
          title="张三"
          subtitle="男 · 45岁 · 3份病历"
          right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>昨天</Typography>}
        />
      </Section>

      {/* ── NewItemCard ── */}
      <Section title="NewItemCard" file="src/components/NewItemCard.jsx">
        <NewItemCard title="新建患者" subtitle="添加新的患者档案" />
      </Section>

      {/* ── SectionLabel ── */}
      <Section title="SectionLabel" file="src/components/SectionLabel.jsx">
        <SectionLabel>账户</SectionLabel>
        <Box sx={{ height: 30, bgcolor: "#fafafa", mb: 1 }} />
        <SectionLabel>最近 · 5位患者</SectionLabel>
        <Box sx={{ height: 30, bgcolor: "#fafafa" }} />
      </Section>

      {/* ── StatusBadge ── */}
      <Section title="StatusBadge" file="src/components/StatusBadge.jsx">
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <StatusBadge label="高" />
          <StatusBadge label="中" />
          <StatusBadge label="低" />
          <StatusBadge label="急诊" colorMap={{ "急诊": COLOR.danger }} />
          <StatusBadge label="紧急" colorMap={{ "紧急": COLOR.warning }} />
          <StatusBadge label="常规" />
          <StatusBadge label="待审核" colorMap={{ "待审核": COLOR.warning }} />
        </Box>
      </Section>

      {/* ── EmptyState ── */}
      <Section title="EmptyState" file="src/components/EmptyState.jsx">
        <EmptyState icon={<AssignmentOutlinedIcon />} title="暂无任务" subtitle="在聊天中说「今日任务」或点击新建" />
      </Section>

      {/* ── RecordAvatar ── */}
      <Section title="RecordAvatar" file="src/components/RecordAvatar.jsx">
        <Box sx={{ display: "flex", gap: 2 }}>
          {["visit", "lab", "imaging", "surgery", "interview_summary", "import"].map((t) => (
            <Box key={t} sx={{ textAlign: "center" }}>
              <RecordAvatar type={t} />
              <Typography sx={{ fontSize: 10, color: "#999", mt: 0.5 }}>{t}</Typography>
            </Box>
          ))}
        </Box>
      </Section>

      {/* ── RecordFields ── */}
      <Section title="RecordFields" file="src/components/RecordFields.jsx">
        <RecordFields record={{ content: "头痛3天伴恶心呕吐\n主诉：头痛3天\n既往史：高血压5年", tags: ["高血压", "头痛"] }} />
      </Section>

      {/* ── SuggestionChips ── */}
      <Section title="SuggestionChips" file="src/components/SuggestionChips.jsx">
        <SuggestionChips
          items={["头痛是否放射?", "呕吐是否喷射状?", "有无意识改变?"]}
          selected={selectedChips}
          onToggle={(text) => setSelectedChips((p) => p.includes(text) ? p.filter((t) => t !== text) : [...p, text])}
          onDismiss={() => setSelectedChips([])}
        />
      </Section>

      {/* ── FilterBar ── */}
      <Section title="FilterBar" file="src/components/FilterBar.jsx">
        <Typography sx={{ fontSize: 11, color: "#999", mb: 1 }}>Task filters:</Typography>
        <FilterBar
          items={[
            { key: "all", label: "全部" },
            { key: "review", label: "待审核" },
            { key: "pending", label: "待办" },
            { key: "done", label: "已完成" },
          ]}
          active="all"
          counts={{ all: 5, review: 0, pending: 3, done: 2 }}
          onChange={() => {}}
        />
        <Typography sx={{ fontSize: 11, color: "#999", mt: 2, mb: 1 }}>Record tabs:</Typography>
        <FilterBar
          items={[
            { key: "", label: "全部" },
            { key: "visit", label: "病历" },
            { key: "lab", label: "检验/影像" },
            { key: "interview", label: "问诊" },
          ]}
          active=""
          counts={{ "": 3, visit: 2, lab: 0, interview: 1 }}
          onChange={() => {}}
        />
      </Section>

      {/* ── AskAIBar ── */}
      <Section title="AskAIBar" file="src/components/AskAIBar.jsx">
        <AskAIBar onClick={() => {}} />
      </Section>

      {/* ── PatientAvatar ── */}
      <Section title="PatientAvatar" file="src/components/PatientAvatar.jsx">
        <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
          <PatientAvatar name="陈伟强" size={36} />
          <PatientAvatar name="李复诊" size={36} />
          <PatientAvatar name="王明" size={36} />
          <PatientAvatar name="张小红" size={36} />
          <PatientAvatar name="刘建国" size={36} />
        </Box>
      </Section>

      {/* ── DoctorBubble ── */}
      <Section title="DoctorBubble" file="src/components/DoctorBubble.jsx">
        <DoctorBubble doctorName="张医生" content="您好，我已经查看了您的检查报告，情况基本正常。" timestamp="2026-03-26 10:30" />
      </Section>

      {/* ── RecordCard ── */}
      <Section title="RecordCard" file="src/components/RecordCard.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Expandable record with NHC fields + actions:</Typography>
        <RecordCard
          record={{
            id: 1, record_type: "visit", status: "completed",
            content: "头痛3天伴恶心呕吐",
            created_at: "2026-03-26", tags: ["高血压", "头痛"],
            structured: { chief_complaint: "头痛3天伴恶心呕吐", past_history: "高血压10年", allergy_history: "磺胺类药物过敏" },
          }}
          doctorId="mock"
          onUpdated={() => {}}
          onDeleted={() => {}}
        />
      </Section>

      {/* ── CancelConfirm ── */}
      <Section title="CancelConfirm" file="src/components/CancelConfirm.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Two-step cancel (static preview):</Typography>
        <Box sx={{ border: `1px solid ${COLOR.border}`, borderRadius: "12px", p: 3, textAlign: "center" }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, mb: 0.5 }}>确认离开？</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 2.5 }}>未保存的内容将会丢失</Typography>
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Box sx={{ flex: 1, py: 1, textAlign: "center", borderRadius: "4px", fontSize: TYPE.body.fontSize, color: COLOR.danger, border: `0.5px solid ${COLOR.border}` }}>确认</Box>
            <Box sx={{ flex: 1, py: 1, textAlign: "center", borderRadius: "4px", fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.white, bgcolor: COLOR.primary }}>返回</Box>
          </Box>
        </Box>
      </Section>

      {/* ── VoiceInput ── */}
      <Section title="VoiceInput" file="src/components/VoiceInput.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4 }}>Long-press mic button → speech-to-text. Interactive — needs microphone permission.</Typography>
      </Section>

      {/* ── ImportChoiceDialog ── */}
      <Section title="ImportChoiceDialog" file="src/components/ImportChoiceDialog.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4 }}>PDF import vs WeChat chat paste chooser. Opens as a dialog.</Typography>
      </Section>

      {/* ── ExportSelectorDialog ── */}
      <Section title="ExportSelectorDialog" file="src/components/ExportSelectorDialog.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4 }}>Choose sections + date range for PDF export. Opens as a dialog.</Typography>
      </Section>

      {/* ── PatientPickerDialog ── */}
      <Section title="PatientPickerDialog" file="src/components/PatientPickerDialog.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4 }}>Search and select patient from list. Opens as a dialog in chat.</Typography>
      </Section>

      {/* ── TaskChecklist ── */}
      <Section title="TaskChecklist" file="src/components/TaskChecklist.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4 }}>Patient-facing task list with checkboxes. Used in patient portal tasks tab.</Typography>
      </Section>

      {/* ── RecordEditDialog ── */}
      <Section title="RecordEditDialog" file="src/components/RecordEditDialog.jsx">
        <Typography sx={{ fontSize: 11, color: COLOR.text4 }}>Per-field NHC editing dialog. Opens from RecordCard edit button.</Typography>
      </Section>

      {/* Doctor-specific components: see /debug/doctor-components */}

      {/* ── Action Button Layout ── */}
      <Section title="Action Button Layout" file="(pattern, not a component)">
        <Typography sx={{ fontSize: 11, color: "#999", mb: 1 }}>Destructive left, constructive right:</Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, pt: 1, borderTop: "0.5px solid #f0f0f0" }}>
          <Box sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.danger, cursor: "pointer", display: "flex", alignItems: "center", gap: 0.5 }}>
            删除
          </Box>
          <Box sx={{ flex: 1 }} />
          <Box sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", display: "flex", alignItems: "center", gap: 0.5 }}>
            编辑
          </Box>
        </Box>
      </Section>

      <Box sx={{ height: 40 }} />
    </Box>
  );
}
