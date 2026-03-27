/**
 * @route /debug/doctor-pages
 *
 * Interactive doctor app mockup — fully navigable with static data.
 * No backend needed. Click patients, tasks, records — all state-driven.
 *
 * Use this to iterate on UI design without running the server.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, ICON, COLOR } from "../../../theme";

import {
  MOCK_PATIENTS, MOCK_RECORDS, MOCK_TASKS,
  MOCK_SUGGESTIONS, MOCK_BRIEFING, MOCK_CHAT_MESSAGES,
  MOCK_OVERDUE, MOCK_INTERVIEW_STATE, MOCK_CARRY_FORWARD, MOCK_PATIENT_MESSAGES,
} from "./MockData";

import DiagnosisCard from "../../../components/doctor/DiagnosisCard";
import InterviewCompleteDialog from "../../../components/doctor/InterviewCompleteDialog";
import FieldReviewCard from "../../../components/doctor/FieldReviewCard";

import SubpageHeader from "../../../components/SubpageHeader";
import PageSkeleton from "../../../components/PageSkeleton";
import FilterBar from "../../../components/FilterBar";
import ListCard from "../../../components/ListCard";
import NewItemCard from "../../../components/NewItemCard";
import AppButton from "../../../components/AppButton";
import PatientAvatar from "../../../components/PatientAvatar";
import SectionLabel from "../../../components/SectionLabel";
import AskAIBar from "../../../components/AskAIBar";
import BarButton from "../../../components/BarButton";
import RecordCard from "../../../components/RecordCard";
import RecordFields from "../../../components/RecordFields";
import ActionPanel from "../../../components/ActionPanel";
import SuggestionChips from "../../../components/SuggestionChips";
import ConfirmDialog from "../../../components/ConfirmDialog";
import StatusBadge from "../../../components/StatusBadge";

import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import AddIcon from "@mui/icons-material/Add";
import MicIcon from "@mui/icons-material/Mic";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import IosShareIcon from "@mui/icons-material/IosShare";

/* ── Field labels for interview missing-fields hints ── */
const FIELD_LABELS = {
  chief_complaint: "主诉", present_illness: "现病史", past_history: "既往史",
  allergy_history: "过敏史", family_history: "家族史", personal_history: "个人史",
  marital_reproductive: "婚育史", physical_exam: "体格检查", specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查", diagnosis: "诊断", treatment_plan: "治疗方案",
  orders_followup: "医嘱及随访",
};

/* ── Task status color map ── */
const TASK_STATUS_COLOR = {
  "待处理": COLOR.warning,
  "已完成": COLOR.primary,
  "已逾期": COLOR.danger,
};

/* ── Bottom Nav ── */

const TABS = [
  { key: "home", label: "首页", Icon: HomeOutlinedIcon },
  { key: "patients", label: "患者", Icon: PeopleOutlineIcon },
  { key: "tasks", label: "任务", Icon: AssignmentOutlinedIcon },
  { key: "settings", label: "设置", Icon: SettingsOutlinedIcon },
];

function MockBottomNav({ active, onNav }) {
  return (
    <Box sx={{
      position: "absolute", bottom: 0, left: 0, right: 0, height: 64,
      display: "flex", bgcolor: COLOR.surface, borderTop: `0.5px solid #d9d9d9`,
    }}>
      {TABS.map(({ key, label, Icon }) => (
        <Box key={key} onClick={() => onNav(key)} sx={{
          flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", cursor: "pointer",
          color: active === key ? COLOR.primary : COLOR.text4,
          fontWeight: active === key ? 600 : 400,
        }}>
          <Icon sx={{ fontSize: ICON.lg }} />
          <Typography sx={{ fontSize: 10, mt: 0.3 }}>{label}</Typography>
        </Box>
      ))}
    </Box>
  );
}

/* ── Home ── */

function MockHome({ onNav }) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto", position: "relative" }}>
      <Box sx={{ p: 1.5, pb: 8 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, mb: 1 }}>
          <Box onClick={() => onNav("patients")} sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5, cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}>
            <Typography sx={{ fontSize: 24, fontWeight: 700, color: COLOR.primary }}>{MOCK_BRIEFING.today_patients}</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>今日患者</Typography>
          </Box>
          <Box onClick={() => onNav("tasks")} sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5, cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}>
            <Typography sx={{ fontSize: 24, fontWeight: 700, color: COLOR.primary }}>{MOCK_BRIEFING.pending_tasks}</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>待办任务</Typography>
          </Box>
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5, mb: 1 }}>
          <Typography sx={{ fontSize: 24, fontWeight: 700, color: COLOR.text4 }}>{MOCK_BRIEFING.completed_tasks}</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>已完成</Typography>
        </Box>
        {/* Overdue tasks section */}
        {MOCK_OVERDUE.length > 0 && (
          <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5, mb: 1 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
              <Typography sx={{ fontWeight: 600, fontSize: TYPE.heading.fontSize }}>逾期任务</Typography>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger }}>{MOCK_OVERDUE.length}项</Typography>
            </Box>
            {MOCK_OVERDUE.map(t => (
              <Box key={t.id} sx={{ display: "flex", justifyContent: "space-between", py: 0.8, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>{t.patient_name} {t.title}</Typography>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger }}>{t.due}</Typography>
              </Box>
            ))}
          </Box>
        )}
        <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 2 }}>
          <Typography sx={{ fontWeight: 600, mb: 1 }}>欢迎使用鲸鱼随行！</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.8 }}>
            1. 发送消息给 AI 助手创建第一条病历{"\n"}
            2. 在患者页面添加患者{"\n"}
            3. 在任务页面创建任务
          </Typography>
        </Box>
      </Box>
      <Box sx={{ position: "absolute", bottom: 6, left: 0, right: 0, px: 1.5 }}>
        <AskAIBar onClick={() => onNav("chat")} />
      </Box>
    </Box>
  );

  return <PageSkeleton title="首页" isMobile listPane={content} />;
}

/* ── Patients ── */

function MockPatients({ onSelectPatient }) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      <Box sx={{ px: 1.5, py: 1, bgcolor: COLOR.white }}>
        <Box sx={{ bgcolor: COLOR.surface, borderRadius: 1, px: 1.5, py: 1, color: COLOR.text4, fontSize: TYPE.secondary.fontSize }}>
          搜索患者 (共{MOCK_PATIENTS.length}人)
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
          onClick={() => onSelectPatient(p)}
          chevron
        />
      ))}
    </Box>
  );

  return <PageSkeleton title="患者" isMobile listPane={content} />;
}

/* ── Patient Detail ── */

function MockPatientDetail({ patient, onBack, onReview, onInterview }) {
  const records = MOCK_RECORDS.filter(r => r.patient_id === patient.id);
  const completedRecords = records.filter(r => r.status === "completed");
  const pendingRecords = records.filter(r => r.status === "pending_review");
  const age = 2026 - patient.year_of_birth;
  const genderStr = patient.gender === "male" ? "男" : "女";
  const [profileExpanded, setProfileExpanded] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const patientMessages = MOCK_PATIENT_MESSAGES.filter(m => m.patient_id === patient.id);

  const content = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {/* Profile — collapsed by default */}
      <Box sx={{ bgcolor: COLOR.white, px: 2.5, py: 1.5, mb: 0.8 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
            <Typography sx={{ fontWeight: 700, fontSize: TYPE.action.fontSize }}>{patient.name}</Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{genderStr} · {age}岁 · 门诊{records.length}</Typography>
          </Box>
          <Typography onClick={() => setProfileExpanded(!profileExpanded)}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}>
            {profileExpanded ? "收起 ▴" : "展开 ▾"}
          </Typography>
        </Box>
        {/* Expanded: actions hidden here until tapped */}
        {profileExpanded && (
          <Box sx={{ mt: 1.5, pt: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.5 }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>最近就诊</Typography>
              <Typography sx={{ fontSize: TYPE.caption.fontSize }}>{records[0]?.created_at?.slice(0, 10) || "—"}</Typography>
            </Box>
            <Box sx={{ display: "flex", justifyContent: "space-between", mt: 1.5 }}>
              <Typography onClick={() => setDeleteConfirmOpen(true)}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.danger, cursor: "pointer" }}>删除</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, cursor: "pointer" }}>导出</Typography>
            </Box>
          </Box>
        )}
      </Box>

      {/* Pending review — quiet amber dot, no badge */}
      {pendingRecords.length > 0 && (
        <Box sx={{ bgcolor: COLOR.white, px: 2.5, py: 1.5, mb: 0.8 }}>
          {pendingRecords.map((r) => (
            <Box key={r.id} onClick={() => onReview(r)}
              sx={{ py: 1, cursor: "pointer", "&:active": { bgcolor: COLOR.surfaceAlt } }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
                  <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: COLOR.warning }} />
                  <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2 }}>
                    {r.record_type === "visit" ? "门诊记录" : "问诊总结"}
                  </Typography>
                  <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.warning }}>待审核</Typography>
                </Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{r.created_at?.slice(5, 10)}</Typography>
                  <Typography sx={{ color: COLOR.text4, fontSize: TYPE.caption.fontSize }}>›</Typography>
                </Box>
              </Box>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.3 }}>
                {r.structured?.chief_complaint || r.content}
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      {/* Records — using shared RecordCard component */}
      <Box sx={{ bgcolor: COLOR.white, py: 1.5 }}>
        <FilterBar
          items={[{ key: "", label: "全部" }, { key: "visit", label: "病历" }, { key: "interview_summary", label: "问诊" }]}
          active="" counts={{ "": completedRecords.length }} onChange={() => {}}
        />
        {completedRecords.length === 0 ? (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, py: 3, textAlign: "center" }}>暂无病历记录</Typography>
        ) : completedRecords.map((r) => (
          <RecordCard key={r.id} record={r} doctorId="mock_doctor" onUpdated={() => {}} onDeleted={() => {}} />
        ))}
      </Box>

      {/* Patient messages — quiet, just red dot for escalation */}
      {patientMessages.length > 0 && (
        <Box sx={{ bgcolor: COLOR.white, px: 2.5, py: 1.5, mt: 0.8 }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 1 }}>患者消息</Typography>
          {patientMessages.map((msg) => (
            <Box key={msg.id} sx={{ py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.3 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  {msg.triage_category === "escalation" && (
                    <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: COLOR.danger }} />
                  )}
                  <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2 }}>{msg.content}</Typography>
                </Box>
                <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, flexShrink: 0, ml: 1 }}>
                  {msg.created_at?.slice(11, 16)}
                </Typography>
              </Box>
            </Box>
          ))}
        </Box>
      )}

      <ConfirmDialog
        open={deleteConfirmOpen}
        title="删除患者"
        message={`确认删除患者「${patient.name}」？此操作不可恢复。`}
        confirmLabel="删除"
        cancelLabel="取消"
        confirmTone="danger"
        onConfirm={() => { setDeleteConfirmOpen(false); onBack(); }}
        onCancel={() => setDeleteConfirmOpen(false)}
      />
    </Box>
  );

  return (
    <PageSkeleton
      title={patient.name}
      onBack={onBack}
      headerRight={<BarButton onClick={onInterview}>门诊</BarButton>}
      isMobile
      listPane={content}
    />
  );
}

/* ── Tasks ── */

function groupTasks(tasks) {
  const today = "2026-03-26";
  const endOfWeek = "2026-03-29"; // Sun
  const groups = { overdue: [], today: [], week: [], later: [] };
  tasks.forEach(t => {
    if (t.status === "done") {
      groups.later.push(t);
    } else if (t.due_at < today) {
      groups.overdue.push(t);
    } else if (t.due_at === today) {
      groups.today.push(t);
    } else if (t.due_at <= endOfWeek) {
      groups.week.push(t);
    } else {
      groups.later.push(t);
    }
  });
  return groups;
}

const GROUP_LABELS = { overdue: "已逾期", today: "今天", week: "本周", later: "之后" };

function TaskDetailView({ task, onBack }) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto", p: 1.5 }}>
      <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 2, mb: 1.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, mb: 1 }}>{task.title}</Typography>
        <Box sx={{ display: "flex", gap: 1, mb: 1.5 }}>
          <StatusBadge
            label={task.status === "done" ? "已完成" : "待处理"}
            colorMap={TASK_STATUS_COLOR}
          />
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.8, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>患者</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>{task.patient_name}</Typography>
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.8, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>截止日期</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>{task.due_at}</Typography>
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.8, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>类型</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>{task.task_type}</Typography>
        </Box>
        <Box sx={{ py: 0.8, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 0.3 }}>详情</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, lineHeight: 1.6 }}>{task.content}</Typography>
        </Box>
      </Box>
      {/* Action buttons */}
      <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(3, 1fr)" }}>
        <AppButton variant="primary" size="md" fullWidth onClick={onBack}>完成</AppButton>
        <AppButton variant="secondary" size="md" fullWidth onClick={onBack}>推迟</AppButton>
        <AppButton variant="danger" size="md" fullWidth onClick={onBack}>取消</AppButton>
      </Box>
    </Box>
  );

  return <PageSkeleton title="任务详情" onBack={onBack} isMobile listPane={content} />;
}

function MockTasks({ onSelectTask }) {
  const [filter, setFilter] = useState("all");
  const chips = [
    { key: "all", label: "全部" },
    { key: "pending", label: "待办" },
    { key: "done", label: "已完成" },
  ];
  const counts = { all: MOCK_TASKS.length, pending: MOCK_TASKS.filter(t => t.status === "pending").length, done: MOCK_TASKS.filter(t => t.status === "done").length };
  const filtered = MOCK_TASKS.filter(t => filter === "all" || t.status === filter);
  const groups = groupTasks(filtered);

  const content = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      <FilterBar items={chips} active={filter} counts={counts} onChange={setFilter} />
      <NewItemCard title="新建任务" subtitle="添加随访、检查、用药等任务" />
      {["overdue", "today", "week", "later"].map(groupKey => {
        const items = groups[groupKey];
        if (items.length === 0) return null;
        return (
          <Box key={groupKey}>
            <SectionLabel>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                {GROUP_LABELS[groupKey]}
                {groupKey === "overdue" && (
                  <Box component="span" sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger, fontWeight: 600 }}>
                    {items.length}
                  </Box>
                )}
              </Box>
            </SectionLabel>
            {items.map((t) => (
              <ListCard key={t.id}
                avatar={<Box sx={{ width: 36, height: 36, borderRadius: 1, bgcolor: t.task_type === "follow_up" ? COLOR.primary : t.task_type === "medication" ? COLOR.accent : COLOR.warning, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <AssignmentOutlinedIcon sx={{ fontSize: 18, color: COLOR.white }} />
                </Box>}
                title={t.title}
                subtitle={t.content}
                right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: groupKey === "overdue" ? COLOR.danger : t.status === "done" ? COLOR.text4 : COLOR.warning }}>{t.due_at?.slice(5)}</Typography>}
                chevron
                onClick={() => onSelectTask(t)}
              />
            ))}
          </Box>
        );
      })}
    </Box>
  );

  return <PageSkeleton title="任务" isMobile listPane={content} />;
}

/* ── Chat ── */

function MockChat({ onBack }) {
  const [actionPanelOpen, setActionPanelOpen] = useState(false);

  // Build a simple record for RecordFields to display
  const mockDraftRecord = {
    content: "主诉：头痛3天\n\n请继续补充现病史、既往史等信息。",
    tags: ["草稿"],
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", position: "relative" }}>
      <SubpageHeader title="对话工作区" onBack={onBack} right={<BarButton>清空</BarButton>} />
      <Box sx={{ flex: 1, overflowY: "auto", p: 1.5 }}>
        {MOCK_CHAT_MESSAGES.map((m, i) => (
          <Box key={i} sx={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", mb: 1.5 }}>
            <Box sx={{ maxWidth: "80%" }}>
              <Box sx={{
                px: 1.5, py: 1, borderRadius: 2,
                bgcolor: m.role === "user" ? "#95EC69" : COLOR.white,
                fontSize: TYPE.secondary.fontSize, whiteSpace: "pre-wrap", lineHeight: 1.6,
              }}>
                {m.content}
              </Box>
              {/* Show RecordFields for messages with has_record */}
              {m.has_record && (
                <RecordFields record={mockDraftRecord} />
              )}
            </Box>
          </Box>
        ))}
      </Box>
      {/* Suggestion chips */}
      <SuggestionChips
        items={["今日摘要", "新增病历", "查询患者"]}
        selected={[]}
        onToggle={() => {}}
        onDismiss={() => {}}
      />
      {/* Input bar with + and mic buttons */}
      <Box sx={{ px: 1.5, py: 1, display: "flex", gap: 1, alignItems: "center" }}>
        <Box onClick={() => setActionPanelOpen(true)} sx={{
          width: 36, height: 36, borderRadius: "50%", border: `1px solid ${COLOR.border}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          cursor: "pointer", flexShrink: 0, "&:active": { bgcolor: COLOR.surface },
        }}>
          <AddIcon sx={{ fontSize: ICON.lg, color: COLOR.text3 }} />
        </Box>
        <Box sx={{ flex: 1, bgcolor: COLOR.surface, borderRadius: 2, px: 1.5, py: 1, fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>输入消息...</Box>
        <Box sx={{
          width: 36, height: 36, borderRadius: "50%", border: `1px solid ${COLOR.border}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          cursor: "pointer", flexShrink: 0, "&:active": { bgcolor: COLOR.surface },
        }}>
          <MicIcon sx={{ fontSize: ICON.lg, color: COLOR.text3 }} />
        </Box>
      </Box>
      {/* Action Panel overlay */}
      <ActionPanel open={actionPanelOpen} onClose={() => setActionPanelOpen(false)} onAction={() => setActionPanelOpen(false)} />
    </Box>
  );
}

/* ── Review ── */

function MockReview({ record, onBack }) {
  const [expandedId, setExpandedId] = useState(null);
  const [decisions, setDecisions] = useState({});
  const suggestions = MOCK_SUGGESTIONS.filter(s => s.record_id === record.id);
  const decidedCount = Object.keys(decisions).length;

  function handleDecide(id, decision) {
    setDecisions(prev => ({ ...prev, [id]: decision }));
  }

  const sections = [
    { key: "differential", label: "鉴别诊断" },
    { key: "workup", label: "检查建议" },
    { key: "treatment", label: "治疗方向" },
  ];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <SubpageHeader title="诊断审核" onBack={onBack} right={<BarButton>完成</BarButton>} />
      <Box sx={{ flex: 1, overflowY: "auto", pb: 10 }}>
        <Box sx={{ bgcolor: COLOR.white, m: 1.5, p: 1.5, borderRadius: 1 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600 }}>{record.patient_name}</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{record.created_at?.slice(0, 10)}</Typography>
        </Box>
        {sections.map(({ key, label }) => {
          const items = suggestions.filter(s => s.section === key);
          if (items.length === 0) return null;
          const sectionDecided = items.filter(s => decisions[s.id]).length;
          return (
            <Box key={key} sx={{ mb: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", px: 1.5, mb: 0.5 }}>
                <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text2 }}>{label}</Typography>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{sectionDecided}/{items.length}</Typography>
              </Box>
              <Box sx={{ mx: 1.5, mb: 0.5, px: 1.5, py: 1, border: `1px dashed ${COLOR.primary}`, borderRadius: 1, textAlign: "center", color: COLOR.primary, fontSize: TYPE.body.fontSize, cursor: "pointer" }}>+ 添加</Box>
              <Box sx={{ mx: 1.5, borderRadius: 1, overflow: "hidden", border: `0.5px solid ${COLOR.borderLight}` }}>
                {items.map((s, i) => {
                  const withDecision = decisions[s.id] ? { ...s, decision: decisions[s.id] } : s;
                  return (
                    <Box key={s.id} sx={{ borderTop: i > 0 ? `0.5px solid ${COLOR.borderLight}` : "none" }}>
                      <DiagnosisCard
                        suggestion={withDecision}
                        expanded={expandedId === s.id}
                        onToggle={() => setExpandedId(expandedId === s.id ? null : s.id)}
                        onDecide={(id, decision) => handleDecide(id, decision)}
                      />
                    </Box>
                  );
                })}
              </Box>
            </Box>
          );
        })}
      </Box>
      <Box sx={{ px: 1.5, py: 1.5, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{decidedCount}/{suggestions.length} 已处理</Typography>
        <AppButton variant="primary" onClick={onBack}>完成审核</AppButton>
      </Box>
    </Box>
  );
}

/* ── Interview ── */

function MockInterview({ onBack, onComplete }) {
  const [showComplete, setShowComplete] = useState(false);
  const state = MOCK_INTERVIEW_STATE;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <SubpageHeader title="新建病历" onBack={onBack} right={
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.primary }}>
          {state.progress.pct}%
        </Typography>
      } />
      {/* Progress bar */}
      <Box sx={{ height: 3, bgcolor: COLOR.borderLight }}>
        <Box sx={{ height: "100%", width: `${state.progress.pct}%`, bgcolor: COLOR.primary, transition: "width 0.3s" }} />
      </Box>
      {/* Carry-forward section */}
      <Box sx={{ mx: 1.5, mt: 0.5 }}>
        <FieldReviewCard
          title="历史病史"
          subtitle="来自上次就诊记录"
          items={MOCK_CARRY_FORWARD.map(f => ({ field: f.field, label: f.label, value: f.value }))}
          onConfirmAll={() => {}}
          onDismissAll={() => {}}
        />
      </Box>
      {/* Conversation */}
      <Box sx={{ flex: 1, overflowY: "auto", px: 1.5, py: 1 }}>
        {state.conversation.map((m, i) => (
          <Box key={i} sx={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", mb: 1 }}>
            <Box sx={{ maxWidth: "80%", px: 1.5, py: 1, borderRadius: 2,
              bgcolor: m.role === "user" ? "#95EC69" : COLOR.white,
              fontSize: TYPE.secondary.fontSize }}>
              {m.content}
            </Box>
          </Box>
        ))}
      </Box>
      {/* Missing fields hints */}
      <Box sx={{ px: 1.5, py: 0.5, display: "flex", gap: 0.5, flexWrap: "wrap" }}>
        {state.missing.slice(0, 4).map(f => (
          <Box key={f} sx={{ px: 1, py: 0.3, border: `1px solid ${COLOR.border}`, borderRadius: 1, fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
            {FIELD_LABELS[f] || f}
          </Box>
        ))}
        {state.missing.length > 4 && <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>+{state.missing.length - 4}</Typography>}
      </Box>
      {/* Suggestions */}
      <SuggestionChips items={state.suggestions} selected={[]} onToggle={() => {}} onDismiss={() => {}} />
      {/* Input */}
      <Box sx={{ px: 1.5, py: 1, display: "flex", gap: 1, alignItems: "center" }}>
        <Box sx={{ flex: 1, bgcolor: COLOR.surface, borderRadius: 2, px: 1.5, py: 1, fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>输入消息...</Box>
        <AppButton variant="primary" size="sm" onClick={() => setShowComplete(true)}>完成</AppButton>
      </Box>
      <InterviewCompleteDialog
        open={showComplete}
        fields={state.collected}
        fieldCount={{ filled: state.progress.filled, total: state.progress.total }}
        onSave={() => { setShowComplete(false); onComplete?.(); }}
        onSaveAndDiagnose={() => { setShowComplete(false); onComplete?.(); }}
        onClose={() => setShowComplete(false)}
      />
    </Box>
  );
}

/* ── Settings ── */

function MockSettingsTemplate({ onBack }) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      <Box sx={{ px: 2, py: 1.5 }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>共 3 个模板</Typography>
      </Box>
      <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        {[
          { name: "门诊病历模板", desc: "默认模板，包含主诉、现病史、既往史等字段", badge: "默认" },
          { name: "神经外科专科模板", desc: "包含GCS评分、瞳孔检查、神经系统查体等专科字段" },
          { name: "术后随访模板", desc: "术后恢复情况、伤口愈合、并发症筛查" },
        ].map((t, i) => (
          <Box key={t.name} sx={{
            display: "flex", alignItems: "center", px: 2, py: 1.5, cursor: "pointer",
            borderTop: i > 0 ? `0.5px solid ${COLOR.borderLight}` : "none",
            "&:active": { bgcolor: COLOR.surfaceAlt },
          }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
                <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500 }}>{t.name}</Typography>
                {t.badge && (
                  <Box sx={{ px: 0.8, py: 0.2, borderRadius: "4px", fontSize: TYPE.micro.fontSize, fontWeight: 500, bgcolor: "#E8F5E9", color: COLOR.primary }}>
                    {t.badge}
                  </Box>
                )}
              </Box>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.3 }}>{t.desc}</Typography>
            </Box>
            <Typography sx={{ color: COLOR.text4 }}>›</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );

  return <PageSkeleton title="报告模板" onBack={onBack} isMobile listPane={content} />;
}

import KnowledgeSubpage from "../subpages/KnowledgeSubpage";

const MOCK_KNOWLEDGE_ITEMS = [
  { id: 1, category: "red_flag", text: "蛛网膜下腔出血（SAH）：突发剧烈头痛（雷击样），伴恶心呕吐、颈强直、意识障碍。Fisher分级指导治疗。Hunt-Hess分级评估预后。", source: "agent_auto", created_at: "2026-03-20", reference_count: 5 },
  { id: 2, category: "red_flag", text: "急性脑梗死：突发偏瘫、失语、视野缺损。NIHSS评分＞4分考虑溶栓或取栓。4.5h窗口期rtPA，24h窗口期机械取栓。", source: "doctor", created_at: "2026-03-18", reference_count: 3 },
  { id: 3, category: "interview_guide", text: "高血压患者首诊：必须询问头痛、头晕、视物模糊、胸闷。必须测量双上肢血压。询问家族史、用药依从性。", source: "doctor", created_at: "2026-03-15", reference_count: 8 },
  { id: 4, category: "diagnosis_rule", text: "高血压分级：1级（140-159/90-99）2级（160-179/100-109）3级（≥180/≥110）。危险分层：低危/中危/高危/很高危。", source: "agent_auto", created_at: "2026-03-10", reference_count: 12 },
  { id: 5, category: "treatment_protocol", text: "脑动脉瘤术后管理：尼莫地平60mg/d预防血管痉挛14天。术后3天CT排除再出血。7天DSA评估效果。每日TCD监测。", source: "doctor", created_at: "2026-03-22", reference_count: 2 },
];

function MockSettingsKnowledge({ onBack }) {
  return (
    <KnowledgeSubpage
      items={MOCK_KNOWLEDGE_ITEMS}
      onBack={onBack}
      onAdd={() => {}}
      onDelete={(id) => {}}
      onEdit={(id, text) => {}}
    />
  );
}

function MockSettingsAbout({ onBack }) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
      <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 2, textAlign: "center", mb: 1 }}>
        <Box sx={{ width: 64, height: 64, borderRadius: 2, bgcolor: COLOR.primary, display: "flex", alignItems: "center", justifyContent: "center", color: COLOR.white, fontSize: 24, fontWeight: 700, mx: "auto", mb: 1.5 }}>
          鲸
        </Box>
        <Typography sx={{ fontWeight: 700, fontSize: TYPE.action.fontSize, mb: 0.5 }}>鲸鱼随行</Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 1 }}>AI 医疗助手</Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>版本 0.1.0 (mock)</Typography>
      </Box>
      <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.8 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>构建日期</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>2026-03-26</Typography>
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.8, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>LLM 引擎</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>Qwen3:32b</Typography>
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.8, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>运行环境</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>开发模式</Typography>
        </Box>
      </Box>
    </Box>
  );

  return <PageSkeleton title="关于" onBack={onBack} isMobile listPane={content} />;
}

function MockSettings({ onSubpage }) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      <SectionLabel>账户</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white, p: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5 }}>
          <Box sx={{ width: 48, height: 48, borderRadius: 1, bgcolor: COLOR.primary, display: "flex", alignItems: "center", justifyContent: "center", color: COLOR.white, fontSize: 20, fontWeight: 600 }}>张</Box>
          <Box>
            <Typography sx={{ fontWeight: 600 }}>张医生</Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>mock_doctor</Typography>
          </Box>
        </Box>
        <ListCard
          title="昵称"
          right={<Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>张医生</Typography>}
          chevron
          onClick={() => {}}
          sx={{ mx: -2, borderBottom: `0.5px solid ${COLOR.borderLight}` }}
        />
        <ListCard
          title="科室专业"
          right={<Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>神经外科</Typography>}
          chevron
          onClick={() => {}}
          sx={{ mx: -2, borderBottom: "none" }}
        />
      </Box>
      <SectionLabel>工具</SectionLabel>
      <ListCard title="报告模板" subtitle="自定义门诊病历报告格式" chevron onClick={() => onSubpage("template")} />
      <ListCard title="知识库" subtitle="管理 AI 助手参考资料" chevron onClick={() => onSubpage("knowledge")} />
      <SectionLabel>通用</SectionLabel>
      <ListCard title="关于" subtitle="版本信息" chevron onClick={() => onSubpage("about")} />
      <SectionLabel>账户操作</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white, py: 1.5, textAlign: "center" }}>
        <Typography sx={{ color: COLOR.danger, fontSize: TYPE.body.fontSize }}>退出登录</Typography>
      </Box>
    </Box>
  );

  return <PageSkeleton title="设置" isMobile listPane={content} />;
}

/* ── Main: Interactive Mock App ── */

export default function MockPages() {
  // Navigation state
  const [tab, setTab] = useState("home");         // bottom nav tab
  const [subpage, setSubpage] = useState(null);    // "patient-detail" | "review" | "chat" | "interview" | "task-detail" | "settings-sub"
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);
  const [settingsSub, setSettingsSub] = useState(null); // "template" | "knowledge" | "about"

  function navTo(key) {
    setTab(key);
    setSubpage(null);
    setSelectedPatient(null);
    setSelectedRecord(null);
    setSelectedTask(null);
    setSettingsSub(null);
  }

  function openPatient(patient) {
    setSelectedPatient(patient);
    setSubpage("patient-detail");
  }

  function openReview(record) {
    setSelectedRecord(record);
    setSubpage("review");
  }

  function openChat() {
    setSubpage("chat");
  }

  function openInterview() {
    setSubpage("interview");
  }

  function openTaskDetail(task) {
    setSelectedTask(task);
    setSubpage("task-detail");
  }

  function openSettingsSub(key) {
    setSettingsSub(key);
    setSubpage("settings-sub");
  }

  function goBack() {
    if (subpage === "review" && selectedPatient) {
      setSubpage("patient-detail");
      setSelectedRecord(null);
    } else if (subpage === "interview" && selectedPatient) {
      setSubpage("patient-detail");
    } else if (subpage === "task-detail") {
      setSubpage(null);
      setSelectedTask(null);
    } else if (subpage === "settings-sub") {
      setSubpage(null);
      setSettingsSub(null);
    } else {
      setSubpage(null);
      setSelectedPatient(null);
      setSelectedRecord(null);
      setSelectedTask(null);
    }
  }

  // Determine active nav highlight
  const activeTab = (subpage === "chat" || subpage === "interview") ? "home" : subpage === "task-detail" ? "tasks" : subpage === "settings-sub" ? "settings" : tab;

  // Full-screen subpages (no bottom nav)

  // Render content based on state
  function renderContent() {
    if (subpage === "review" && selectedRecord) {
      return <MockReview record={selectedRecord} onBack={goBack} />;
    }
    if (subpage === "chat") {
      return <MockChat onBack={goBack} />;
    }
    if (subpage === "interview" && selectedPatient) {
      return <MockInterview onBack={goBack} onComplete={() => { setSubpage("patient-detail"); }} />;
    }
    if (subpage === "task-detail" && selectedTask) {
      return <TaskDetailView task={selectedTask} onBack={goBack} />;
    }
    if (subpage === "settings-sub") {
      if (settingsSub === "template") return <MockSettingsTemplate onBack={goBack} />;
      if (settingsSub === "knowledge") return <MockSettingsKnowledge onBack={goBack} />;
      if (settingsSub === "about") return <MockSettingsAbout onBack={goBack} />;
      return null;
    }
    if (subpage === "patient-detail" && selectedPatient) {
      return <MockPatientDetail patient={selectedPatient} onBack={goBack} onReview={openReview} onInterview={openInterview} />;
    }

    switch (tab) {
      case "home": return <MockHome onNav={(key) => key === "chat" ? openChat() : navTo(key)} />;
      case "patients": return <MockPatients onSelectPatient={openPatient} />;
      case "tasks": return <MockTasks onSelectTask={openTaskDetail} />;
      case "settings": return <MockSettings onSubpage={openSettingsSub} />;
      default: return null;
    }
  }

  return (
    <Box sx={{
      width: "100vw", height: "100vh", display: "flex",
      justifyContent: "center", alignItems: "center", bgcolor: "#e8e8e8",
    }}>
      <Box sx={{
        width: "min(calc(95vh * 9 / 19.5), 90vw)",
        height: "min(calc(90vw * 19.5 / 9), 95vh)",
        maxWidth: 480,
        borderRadius: "16px",
        boxShadow: "0 4px 24px rgba(0,0,0,0.12)",
        overflow: "hidden",
        position: "relative",
        display: "flex",
        flexDirection: "column",
        bgcolor: "#ededed",
        transform: "translateZ(0)",
      }}>
        <Box sx={{ flex: 1, overflow: "hidden", position: "relative" }}>
          {renderContent()}
        </Box>
        <MockBottomNav active={activeTab} onNav={navTo} />
      </Box>
    </Box>
  );
}
