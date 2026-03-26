/**
 * @route /debug/components
 *
 * Shared Component Showcase — all components from src/components/
 * grouped by category with collapsible sections.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, ICON, COLOR } from "../../theme";

// All shared components
import AppButton from "../../components/AppButton";
import AskAIBar from "../../components/AskAIBar";
import BarButton from "../../components/BarButton";
import CancelConfirm from "../../components/CancelConfirm";
import DetailCard from "../../components/DetailCard";
import DoctorBubble from "../../components/DoctorBubble";
import EmptyState from "../../components/EmptyState";
import ExportSelectorDialog from "../../components/ExportSelectorDialog";
import FilterBar from "../../components/FilterBar";
import ImportChoiceDialog from "../../components/ImportChoiceDialog";
import ListCard from "../../components/ListCard";
import NewItemCard from "../../components/NewItemCard";
import PatientAvatar from "../../components/PatientAvatar";
import PatientPickerDialog from "../../components/PatientPickerDialog";
import RecordAvatar from "../../components/RecordAvatar";
import RecordCard from "../../components/RecordCard";
import RecordEditDialog from "../../components/RecordEditDialog";
import RecordFields from "../../components/RecordFields";
import SectionLabel from "../../components/SectionLabel";
import StatusBadge from "../../components/StatusBadge";
import SubpageHeader from "../../components/SubpageHeader";
import SuggestionChips from "../../components/SuggestionChips";
import TaskChecklist from "../../components/TaskChecklist";
import VoiceInput from "../../components/VoiceInput";

import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";

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

function Group({ id, title, count, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Box id={id} sx={{ mb: 3, scrollMarginTop: 16 }}>
      <Box onClick={() => setOpen(!open)} sx={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        py: 1.5, px: 2, bgcolor: COLOR.white, borderRadius: 1, cursor: "pointer",
        border: `1px solid ${COLOR.border}`,
        "&:active": { bgcolor: COLOR.surface },
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

export default function ComponentShowcasePage() {
  const [selectedChips, setSelectedChips] = useState([]);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  const groups = [
    "Design Tokens", "Buttons", "Navigation", "List & Cards",
    "Badges & Avatars", "Record & Fields", "Chat & Input",
    "Dialogs & Pickers", "Patient & Task", "Layout Patterns",
  ];

  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "#f5f5f5" }}>
      {/* Left floating nav */}
      <Box sx={{
        position: "fixed", left: 0, top: 0, bottom: 0, width: 160,
        bgcolor: COLOR.white, borderRight: `1px solid ${COLOR.border}`,
        overflowY: "auto", py: 2, px: 1.5, zIndex: 10,
        "@media (max-width: 700px)": { display: "none" },
      }}>
        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, fontWeight: 600, mb: 1, letterSpacing: 0.5 }}>COMPONENTS</Typography>
        {groups.map((g, i) => (
          <Box key={g} onClick={() => document.getElementById(`group-${i}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, py: 0.6, cursor: "pointer", "&:hover": { color: COLOR.primary }, "&:active": { color: COLOR.primary } }}>
            {g}
          </Box>
        ))}
        <Box sx={{ mt: 2, borderTop: `1px solid ${COLOR.borderLight}`, pt: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, fontWeight: 600, mb: 0.5, letterSpacing: 0.5 }}>OTHER</Typography>
          <Box onClick={() => window.location.href = "/debug/doctor-components"}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.accent, py: 0.4, cursor: "pointer" }}>Doctor Components</Box>
          <Box onClick={() => window.location.href = "/debug/doctor-pages"}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.accent, py: 0.4, cursor: "pointer" }}>Mock Pages</Box>
        </Box>
      </Box>

      {/* Main content */}
      <Box sx={{ maxWidth: 480, p: 2, width: "100%", "@media (min-width: 700px)": { ml: "180px" } }}>
        <Typography sx={{ fontSize: 22, fontWeight: 700, mb: 0.5 }}>Shared Components</Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 3 }}>
          All 27 components from src/components/. Tap group to expand.
        </Typography>

      {/* ═══════ 1. Design Tokens ═══════ */}
      <Group id="group-0" title="Design Tokens" count={3} defaultOpen={true}>
        <Section title="Color Tokens" file="theme.js → COLOR">
          <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0.5 }}>
            {Object.entries(COLOR).map(([name, hex]) => (
              <Box key={name} sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
                <Box sx={{ width: 16, height: 16, borderRadius: 0.5, bgcolor: hex, border: `1px solid ${COLOR.border}`, flexShrink: 0 }} />
                <Typography sx={{ fontSize: 10, fontFamily: "monospace" }}>{name}</Typography>
              </Box>
            ))}
          </Box>
        </Section>

        <Section title="Typography Scale" file="theme.js → TYPE">
          {Object.entries(TYPE).map(([key, { fontSize, fontWeight }]) => (
            <Typography key={key} sx={{ fontSize, fontWeight, mb: 0.3 }}>
              {key} — {fontSize}px/{fontWeight}
            </Typography>
          ))}
        </Section>

        <Section title="Icon Sizes" file="theme.js → ICON">
          <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
            {Object.entries(ICON).map(([key, size]) => (
              <Box key={key} sx={{ textAlign: "center" }}>
                <Box sx={{ width: size, height: size, bgcolor: COLOR.text4, borderRadius: 0.5, mx: "auto" }} />
                <Typography sx={{ fontSize: 9, color: COLOR.text4, mt: 0.3 }}>{key} {size}</Typography>
              </Box>
            ))}
          </Box>
        </Section>
      </Group>

      {/* ═══════ 2. Buttons ═══════ */}
      <Group id="group-1" title="Buttons" count={3}>
        <Section title="AppButton" file="AppButton.jsx">
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <AppButton variant="primary">保存</AppButton>
            <AppButton variant="secondary">取消</AppButton>
            <AppButton variant="danger">删除</AppButton>
            <AppButton variant="primary" disabled>禁用</AppButton>
          </Box>
        </Section>

        <Section title="BarButton" file="BarButton.jsx">
          <Box sx={{ display: "flex", gap: 2 }}>
            <BarButton>门诊</BarButton>
            <BarButton>清空</BarButton>
            <BarButton color={COLOR.text4}>导出</BarButton>
          </Box>
        </Section>

        <Section title="CancelConfirm" file="CancelConfirm.jsx">
          <Box onClick={() => setCancelOpen(true)} sx={{ py: 1, textAlign: "center", border: `1px dashed ${COLOR.danger}`, borderRadius: 1, color: COLOR.danger, cursor: "pointer", fontSize: TYPE.body.fontSize }}>
            触发取消确认
          </Box>
          <CancelConfirm open={cancelOpen} onConfirm={() => setCancelOpen(false)} onCancel={() => setCancelOpen(false)} />
        </Section>
      </Group>

      {/* ═══════ 3. Navigation ═══════ */}
      <Group id="group-2" title="Navigation" count={3}>
        <Section title="SubpageHeader" file="SubpageHeader.jsx">
          <SubpageHeader title="李复诊" onBack={() => {}} right={<BarButton>门诊</BarButton>} />
        </Section>

        <Section title="FilterBar" file="FilterBar.jsx">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Tasks:</Typography>
          <FilterBar items={[{ key: "all", label: "全部" }, { key: "pending", label: "待办" }, { key: "done", label: "已完成" }]} active="all" counts={{ all: 5, pending: 3, done: 2 }} onChange={() => {}} />
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mt: 1.5, mb: 1 }}>Records:</Typography>
          <FilterBar items={[{ key: "", label: "全部" }, { key: "visit", label: "病历" }, { key: "lab", label: "检验" }]} active="" counts={{ "": 3, visit: 2 }} onChange={() => {}} />
        </Section>

        <Section title="SectionLabel" file="SectionLabel.jsx">
          <SectionLabel>账户</SectionLabel>
          <Box sx={{ height: 24, bgcolor: COLOR.surface, mb: 1 }} />
          <SectionLabel>最近 · 5位患者</SectionLabel>
          <Box sx={{ height: 24, bgcolor: COLOR.surface }} />
        </Section>
      </Group>

      {/* ═══════ 4. List & Cards ═══════ */}
      <Group id="group-3" title="List & Cards" count={5}>
        <Section title="ListCard" file="ListCard.jsx">
          <ListCard
            avatar={<PatientAvatar name="陈伟强" size={36} />}
            title="陈伟强" subtitle="男 · 42岁 · 3份病历"
            right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>03-26</Typography>}
          />
          <Box sx={{ borderTop: `0.5px solid ${COLOR.borderLight}` }} />
          <ListCard
            avatar={<PatientAvatar name="李复诊" size={36} />}
            title="李复诊" subtitle="女 · 56岁 · 1份病历"
            right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>03-25</Typography>}
          />
        </Section>

        <Section title="NewItemCard" file="NewItemCard.jsx">
          <NewItemCard title="新建患者" subtitle="添加新的患者档案" />
        </Section>

        <Section title="DetailCard" file="DetailCard.jsx">
          <DetailCard title="随访 · 陈伟强" items={[{ label: "类型", value: "门诊随访" }, { label: "到期", value: "2026-04-01" }, { label: "状态", value: "待处理" }]} />
        </Section>

        <Section title="RecordCard" file="RecordCard.jsx">
          <RecordCard
            record={{ id: 1, record_type: "visit", status: "completed", content: "头痛3天", created_at: "2026-03-26", tags: ["高血压"], structured: { chief_complaint: "头痛3天伴恶心呕吐", past_history: "高血压10年" } }}
            doctorId="mock" onUpdated={() => {}} onDeleted={() => {}}
          />
        </Section>

        <Section title="EmptyState" file="EmptyState.jsx">
          <EmptyState icon={<AssignmentOutlinedIcon />} title="暂无任务" subtitle="在聊天中说「今日任务」或点击新建" />
        </Section>
      </Group>

      {/* ═══════ 5. Badges & Avatars ═══════ */}
      <Group id="group-4" title="Badges & Avatars" count={3}>
        <Section title="StatusBadge" file="StatusBadge.jsx">
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <StatusBadge label="高" />
            <StatusBadge label="中" />
            <StatusBadge label="低" />
            <StatusBadge label="急诊" colorMap={{ "急诊": COLOR.danger }} />
            <StatusBadge label="紧急" colorMap={{ "紧急": COLOR.warning }} />
            <StatusBadge label="待审核" colorMap={{ "待审核": COLOR.warning }} />
          </Box>
        </Section>

        <Section title="PatientAvatar" file="PatientAvatar.jsx">
          <Box sx={{ display: "flex", gap: 2 }}>
            {["陈伟强", "李复诊", "王明", "张小红", "刘建国"].map(n => <PatientAvatar key={n} name={n} size={36} />)}
          </Box>
        </Section>

        <Section title="RecordAvatar" file="RecordAvatar.jsx">
          <Box sx={{ display: "flex", gap: 2 }}>
            {["visit", "lab", "imaging", "surgery", "interview_summary", "import"].map(t => (
              <Box key={t} sx={{ textAlign: "center" }}>
                <RecordAvatar type={t} />
                <Typography sx={{ fontSize: 9, color: COLOR.text4, mt: 0.3 }}>{t}</Typography>
              </Box>
            ))}
          </Box>
        </Section>
      </Group>

      {/* ═══════ 6. Record & Fields ═══════ */}
      <Group id="group-5" title="Record & Fields" count={2}>
        <Section title="RecordFields" file="RecordFields.jsx">
          <RecordFields record={{ content: "头痛3天伴恶心呕吐\n主诉：头痛3天\n既往史：高血压5年", tags: ["高血压", "头痛"] }} />
        </Section>

        <Section title="RecordEditDialog" file="RecordEditDialog.jsx">
          <Box onClick={() => setEditOpen(true)} sx={{ py: 1, textAlign: "center", border: `1px dashed ${COLOR.primary}`, borderRadius: 1, color: COLOR.primary, cursor: "pointer" }}>
            打开病历编辑
          </Box>
          <RecordEditDialog open={editOpen} onClose={() => setEditOpen(false)} onSaved={() => setEditOpen(false)} doctorId="mock"
            record={{ id: 1, record_type: "visit", content: "头痛3天", tags: ["高血压"], structured: { chief_complaint: "头痛3天伴恶心呕吐", past_history: "高血压10年" } }} />
        </Section>
      </Group>

      {/* ═══════ 7. Chat & Input ═══════ */}
      <Group id="group-6" title="Chat & Input" count={4}>
        <Section title="AskAIBar" file="AskAIBar.jsx">
          <AskAIBar onClick={() => {}} />
        </Section>

        <Section title="SuggestionChips" file="SuggestionChips.jsx">
          <SuggestionChips
            items={["头痛是否放射?", "呕吐是否喷射状?", "有无意识改变?"]}
            selected={selectedChips}
            onToggle={(t) => setSelectedChips(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t])}
            onDismiss={() => setSelectedChips([])}
          />
        </Section>

        <Section title="DoctorBubble" file="DoctorBubble.jsx">
          <DoctorBubble doctorName="张医生" content="您好，检查报告基本正常。" timestamp="2026-03-26 10:30" />
        </Section>

        <Section title="VoiceInput" file="VoiceInput.jsx">
          <VoiceInput onResult={() => {}} />
        </Section>
      </Group>

      {/* ═══════ 8. Dialogs ═══════ */}
      <Group id="group-7" title="Dialogs & Pickers" count={3}>
        <Section title="ImportChoiceDialog" file="ImportChoiceDialog.jsx">
          <Box onClick={() => setImportOpen(true)} sx={{ py: 1, textAlign: "center", border: `1px dashed ${COLOR.primary}`, borderRadius: 1, color: COLOR.primary, cursor: "pointer" }}>
            打开导入选择
          </Box>
          <ImportChoiceDialog open={importOpen} onClose={() => setImportOpen(false)} onChoose={() => setImportOpen(false)} />
        </Section>

        <Section title="ExportSelectorDialog" file="ExportSelectorDialog.jsx">
          <Box onClick={() => setExportOpen(true)} sx={{ py: 1, textAlign: "center", border: `1px dashed ${COLOR.primary}`, borderRadius: 1, color: COLOR.primary, cursor: "pointer" }}>
            打开导出选择器
          </Box>
          <ExportSelectorDialog open={exportOpen} onClose={() => setExportOpen(false)} patientId={1} patientName="陈伟强" onExport={() => setExportOpen(false)} />
        </Section>

        <Section title="PatientPickerDialog" file="PatientPickerDialog.jsx">
          <Box onClick={() => setPickerOpen(true)} sx={{ py: 1, textAlign: "center", border: `1px dashed ${COLOR.primary}`, borderRadius: 1, color: COLOR.primary, cursor: "pointer" }}>
            打开患者选择器
          </Box>
          <PatientPickerDialog open={pickerOpen} onClose={() => setPickerOpen(false)} onSelect={() => setPickerOpen(false)} doctorId="mock" />
        </Section>
      </Group>

      {/* ═══════ 9. Patient & Task ═══════ */}
      <Group id="group-8" title="Patient & Task" count={1}>
        <Section title="TaskChecklist" file="TaskChecklist.jsx">
          <TaskChecklist
            tasks={[
              { id: 1, title: "门诊随访", subtitle: "陈伟强 · 头痛复查", due_at: "2026-04-01", status: "pending" },
              { id: 2, title: "血糖复查", subtitle: "李复诊 · HbA1c", due_at: "2026-03-28", status: "pending" },
              { id: 3, title: "用药调整", subtitle: "王明 · 降压药", due_at: "2026-03-24", status: "done" },
            ]}
            onComplete={() => {}}
          />
        </Section>
      </Group>

      {/* ═══════ 10. Patterns ═══════ */}
      <Group id="group-9" title="Layout Patterns" count={1}>
        <Section title="Action Button Layout" file="(convention)">
          <Typography sx={{ fontSize: 11, color: COLOR.text4, mb: 1 }}>Destructive left, constructive right:</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, pt: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
            <Box sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.danger }}>删除</Box>
            <Box sx={{ flex: 1 }} />
            <Box sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary }}>编辑</Box>
          </Box>
        </Section>
      </Group>

      <Typography sx={{ fontSize: 11, color: COLOR.text4, textAlign: "center", mt: 2, mb: 4 }}>
        Doctor-specific components: /debug/doctor-components
      </Typography>
    </Box>
    </Box>
  );
}
