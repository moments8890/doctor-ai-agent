/**
 * @route /debug/doctor-pages
 *
 * Doctor page showcase — renders all doctor pages with static mock data.
 * No backend needed. Use this to iterate on UI without running the server.
 *
 * Each page section can be viewed independently by scrolling.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../../../theme";

import {
  MOCK_DOCTOR, MOCK_PATIENTS, MOCK_RECORDS, MOCK_TASKS,
  MOCK_SUGGESTIONS, MOCK_BRIEFING, MOCK_CHAT_MESSAGES, MOCK_INTERVIEW_FIELDS,
} from "./MockData";

// Doctor sub-components for inline demos
import PatientDetail from "./PatientDetail";
import DiagnosisCard from "./DiagnosisCard";
import WorkingContextHeader from "./WorkingContextHeader";
import InterviewCompleteDialog from "./InterviewCompleteDialog";

// Shared components used in page demos
import SubpageHeader from "../../../components/SubpageHeader";
import FilterBar from "../../../components/FilterBar";
import ListCard from "../../../components/ListCard";
import NewItemCard from "../../../components/NewItemCard";
import EmptyState from "../../../components/EmptyState";
import AppButton from "../../../components/AppButton";
import PatientAvatar from "../../../components/PatientAvatar";
import SectionLabel from "../../../components/SectionLabel";
import AskAIBar from "../../../components/AskAIBar";
import RecordCard from "../../../components/RecordCard";

import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";

/* ── Page Section wrapper ── */

function PageSection({ title, route, children }) {
  return (
    <Box sx={{ mb: 5 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 1, px: 1 }}>
        <Typography sx={{ fontSize: 18, fontWeight: 700 }}>{title}</Typography>
        <Typography sx={{ fontSize: 11, color: COLOR.text4, fontFamily: "monospace" }}>{route}</Typography>
      </Box>
      <Box sx={{
        border: `1px solid ${COLOR.border}`, borderRadius: 2, overflow: "hidden",
        height: 700, overflowY: "auto", bgcolor: "#ededed",
      }}>
        {children}
      </Box>
    </Box>
  );
}

/* ── Mock Home Page ── */

function MockHomePage() {
  return (
    <Box sx={{ height: "100%" }}>
      <SubpageHeader title="首页" />
      <Box sx={{ p: 1.5 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, mb: 1 }}>
          {[
            { label: "今日患者", value: MOCK_BRIEFING.today_patients, color: COLOR.primary },
            { label: "待办任务", value: MOCK_BRIEFING.pending_tasks, color: COLOR.primary },
          ].map((s) => (
            <Box key={s.label} sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5 }}>
              <Typography sx={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>{s.label}</Typography>
            </Box>
          ))}
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5 }}>
          <Typography sx={{ fontSize: 24, fontWeight: 700, color: COLOR.text4 }}>{MOCK_BRIEFING.completed_tasks}</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>已完成</Typography>
        </Box>
      </Box>
      <Box sx={{ position: "absolute", bottom: 70, left: 0, right: 0, px: 1.5 }}>
        <AskAIBar onClick={() => {}} />
      </Box>
    </Box>
  );
}

/* ── Mock Patient List ── */

function MockPatientsPage() {
  return (
    <Box>
      <SubpageHeader title="患者" />
      <Box sx={{ px: 1.5, py: 1, bgcolor: COLOR.white }}>
        <Box sx={{ bgcolor: COLOR.surface, borderRadius: 1, px: 1.5, py: 1, color: COLOR.text4, fontSize: TYPE.secondary.fontSize }}>
          🔍 搜索患者 (共{MOCK_PATIENTS.length}人)，或用自然语言描述
        </Box>
      </Box>
      <NewItemCard title="新建患者" subtitle="添加新的患者档案" />
      <SectionLabel>最近 · {MOCK_PATIENTS.length}位患者</SectionLabel>
      {MOCK_PATIENTS.map((p) => (
        <ListCard key={p.id}
          avatar={<PatientAvatar name={p.name} size={36} />}
          title={p.name}
          subtitle={`${p.gender === "male" ? "男" : "女"} · ${2026 - p.year_of_birth}岁 · ${p.record_count}份病历`}
          right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{p.created_at.slice(5)}</Typography>}
        />
      ))}
    </Box>
  );
}

/* ── Mock Tasks Page ── */

function MockTasksPage() {
  const [filter, setFilter] = useState("all");
  const chips = [
    { key: "all", label: "全部" },
    { key: "pending", label: "待办" },
    { key: "done", label: "已完成" },
  ];
  const counts = { all: MOCK_TASKS.length, pending: MOCK_TASKS.filter(t => t.status === "pending").length, done: MOCK_TASKS.filter(t => t.status === "done").length };

  return (
    <Box>
      <SubpageHeader title="任务" />
      <FilterBar items={chips} active={filter} counts={counts} onChange={setFilter} />
      <NewItemCard title="新建任务" subtitle="添加随访、检查、用药等任务" />
      {MOCK_TASKS.filter(t => filter === "all" || t.status === filter).map((t) => (
        <ListCard key={t.id}
          avatar={<Box sx={{ width: 36, height: 36, borderRadius: 1, bgcolor: t.task_type === "follow_up" ? COLOR.primary : t.task_type === "medication" ? COLOR.accent : COLOR.warning, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <AssignmentOutlinedIcon sx={{ fontSize: 18, color: COLOR.white }} />
          </Box>}
          title={t.title}
          subtitle={t.content}
          right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: t.status === "done" ? COLOR.text4 : COLOR.warning }}>{t.due_at?.slice(5)}</Typography>}
        />
      ))}
    </Box>
  );
}

/* ── Mock Chat Page ── */

function MockChatPage() {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <SubpageHeader title="对话工作区" onBack={() => {}} right={<Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.primary }}>清空</Typography>} />
      <Box sx={{ flex: 1, overflowY: "auto", p: 1.5 }}>
        {MOCK_CHAT_MESSAGES.map((m, i) => (
          <Box key={i} sx={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", mb: 1.5 }}>
            <Box sx={{
              maxWidth: "80%", px: 1.5, py: 1, borderRadius: 2,
              bgcolor: m.role === "user" ? "#95EC69" : COLOR.white,
              fontSize: TYPE.secondary.fontSize, whiteSpace: "pre-wrap", lineHeight: 1.6,
            }}>
              {m.content}
            </Box>
          </Box>
        ))}
      </Box>
      <Box sx={{ px: 1.5, py: 0.5, display: "flex", gap: 0.5 }}>
        {["今日摘要", "新增病历", "查询患者"].map((c) => (
          <Box key={c} sx={{ px: 1.2, py: 0.5, border: `1px solid ${COLOR.border}`, borderRadius: 2, fontSize: TYPE.caption.fontSize, color: COLOR.text3 }}>{c}</Box>
        ))}
        <Box sx={{ px: 1.2, py: 0.5, border: `1px solid ${COLOR.border}`, borderRadius: 2, fontSize: TYPE.caption.fontSize, color: COLOR.text4, opacity: 0.5 }}>诊断建议</Box>
      </Box>
      <Box sx={{ px: 1.5, py: 1, display: "flex", gap: 1, alignItems: "center" }}>
        <Box sx={{ flex: 1, bgcolor: COLOR.surface, borderRadius: 2, px: 1.5, py: 1, fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>输入消息...</Box>
        <Box sx={{ width: 36, height: 36, borderRadius: "50%", bgcolor: COLOR.text4, display: "flex", alignItems: "center", justifyContent: "center", color: COLOR.white, fontSize: 16 }}>▸</Box>
      </Box>
    </Box>
  );
}

/* ── Mock Review Page ── */

function MockReviewPage() {
  const [expandedId, setExpandedId] = useState(null);
  const record = MOCK_RECORDS[1]; // pending_review record
  const differentials = MOCK_SUGGESTIONS.filter(s => s.section === "differential");
  const workup = MOCK_SUGGESTIONS.filter(s => s.section === "workup");
  const treatment = MOCK_SUGGESTIONS.filter(s => s.section === "treatment");
  const decided = MOCK_SUGGESTIONS.filter(s => s.decision).length;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <SubpageHeader title="诊断审核" onBack={() => {}} right={<Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.primary }}>完成</Typography>} />
      <Box sx={{ flex: 1, overflowY: "auto", pb: 10 }}>
        {/* Record summary */}
        <Box sx={{ bgcolor: COLOR.white, m: 1.5, p: 1.5, borderRadius: 1 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600 }}>{record.patient_name}</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{record.created_at?.slice(0, 10)} · {record.record_type}</Typography>
        </Box>

        {/* Sections */}
        {[
          { label: "鉴别诊断", items: differentials },
          { label: "检查建议", items: workup },
          { label: "治疗方向", items: treatment },
        ].map(({ label, items }) => (
          <Box key={label} sx={{ mb: 2 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", px: 1.5, mb: 0.5 }}>
              <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text2 }}>{label}</Typography>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>0/{items.length}</Typography>
            </Box>
            <Box sx={{ mx: 1.5, mb: 0.5, px: 1.5, py: 1, border: `1px dashed ${COLOR.primary}`, borderRadius: 1, textAlign: "center", color: COLOR.primary, fontSize: TYPE.body.fontSize }}>+ 添加</Box>
            <Box sx={{ mx: 1.5, borderRadius: 1, overflow: "hidden", border: `0.5px solid ${COLOR.borderLight}` }}>
              {items.map((s, i) => (
                <Box key={s.id} sx={{ borderTop: i > 0 ? `0.5px solid ${COLOR.borderLight}` : "none" }}>
                  <DiagnosisCard suggestion={s} expanded={expandedId === s.id} onToggle={() => setExpandedId(expandedId === s.id ? null : s.id)} onDecide={() => {}} />
                </Box>
              ))}
            </Box>
          </Box>
        ))}
      </Box>
      {/* Bottom bar */}
      <Box sx={{ px: 1.5, py: 1.5, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{decided}/{MOCK_SUGGESTIONS.length} 已处理</Typography>
        <AppButton variant="primary">完成审核</AppButton>
      </Box>
    </Box>
  );
}

/* ── Main ── */

export default function MockPages() {
  return (
    <Box sx={{ maxWidth: 520, mx: "auto", p: 2, bgcolor: "#f0f0f0", minHeight: "100vh" }}>
      <Typography sx={{ fontSize: 22, fontWeight: 700, mb: 0.5 }}>Doctor Pages (Mock Data)</Typography>
      <Typography sx={{ fontSize: 13, color: COLOR.text4, mb: 3 }}>
        All doctor pages rendered with static data. No backend needed.<br />
        Visit: /debug/doctor-pages
      </Typography>

      <PageSection title="首页" route="/doctor">
        <MockHomePage />
      </PageSection>

      <PageSection title="患者列表" route="/doctor/patients">
        <MockPatientsPage />
      </PageSection>

      <PageSection title="任务" route="/doctor/tasks">
        <MockTasksPage />
      </PageSection>

      <PageSection title="对话" route="/doctor/chat">
        <MockChatPage />
      </PageSection>

      <PageSection title="诊断审核" route="/doctor/review/:recordId">
        <MockReviewPage />
      </PageSection>
    </Box>
  );
}
