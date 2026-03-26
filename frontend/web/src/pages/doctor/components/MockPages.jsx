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
  MOCK_SUGGESTIONS, MOCK_BRIEFING, MOCK_CHAT_MESSAGES, MOCK_INTERVIEW_FIELDS,
} from "./MockData";

import DiagnosisCard from "./DiagnosisCard";
import InterviewCompleteDialog from "./InterviewCompleteDialog";

import SubpageHeader from "../../../components/SubpageHeader";
import FilterBar from "../../../components/FilterBar";
import ListCard from "../../../components/ListCard";
import NewItemCard from "../../../components/NewItemCard";
import AppButton from "../../../components/AppButton";
import PatientAvatar from "../../../components/PatientAvatar";
import SectionLabel from "../../../components/SectionLabel";
import AskAIBar from "../../../components/AskAIBar";
import BarButton from "../../../components/BarButton";

import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";

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
  return (
    <Box sx={{ height: "100%", position: "relative" }}>
      <SubpageHeader title="首页" />
      <Box sx={{ p: 1.5, overflowY: "auto", height: "calc(100% - 48px - 64px)" }}>
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
        <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5, mb: 1.5 }}>
          <Typography sx={{ fontSize: 24, fontWeight: 700, color: COLOR.text4 }}>{MOCK_BRIEFING.completed_tasks}</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>已完成</Typography>
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 2 }}>
          <Typography sx={{ fontWeight: 600, mb: 1 }}>欢迎使用鲸鱼随行！</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.8 }}>
            1. 发送消息给 AI 助手创建第一条病历{"\n"}
            2. 在患者页面添加患者{"\n"}
            3. 在任务页面创建任务
          </Typography>
        </Box>
      </Box>
      <Box sx={{ position: "absolute", bottom: 70, left: 0, right: 0, px: 1.5 }}>
        <AskAIBar onClick={() => onNav("chat")} />
      </Box>
    </Box>
  );
}

/* ── Patients ── */

function MockPatients({ onSelectPatient }) {
  return (
    <Box>
      <SubpageHeader title="患者" />
      <Box sx={{ px: 1.5, py: 1, bgcolor: COLOR.white }}>
        <Box sx={{ bgcolor: COLOR.surface, borderRadius: 1, px: 1.5, py: 1, color: COLOR.text4, fontSize: TYPE.secondary.fontSize }}>
          🔍 搜索患者 (共{MOCK_PATIENTS.length}人)
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
        />
      ))}
    </Box>
  );
}

/* ── Patient Detail ── */

function MockPatientDetail({ patient, onBack, onReview, onInterview }) {
  const records = MOCK_RECORDS.filter(r => r.patient_id === patient.id);
  const age = 2026 - patient.year_of_birth;
  const genderStr = patient.gender === "male" ? "男" : "女";

  return (
    <Box>
      <SubpageHeader title={patient.name} onBack={onBack} right={<BarButton onClick={onInterview}>门诊</BarButton>} />
      {/* Collapsed profile */}
      <Box sx={{ bgcolor: COLOR.white, px: 2.5, py: 1.5, mb: 0.8 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
          <Typography sx={{ fontWeight: 700, fontSize: TYPE.action.fontSize }}>{patient.name}</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{genderStr} · {age}岁 · 门诊{records.length} · 最近{records[0]?.created_at?.slice(5, 10) || "—"}</Typography>
        </Box>
      </Box>
      {/* Records */}
      <Box sx={{ bgcolor: COLOR.white, px: 2.5, py: 1.5 }}>
        <Typography sx={{ fontWeight: 600, mb: 1 }}>病历记录</Typography>
        <FilterBar
          items={[{ key: "", label: "全部" }, { key: "visit", label: "病历" }, { key: "interview", label: "问诊" }]}
          active="" counts={{ "": records.length }} onChange={() => {}}
        />
        {records.length === 0 ? (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, py: 3, textAlign: "center" }}>暂无病历记录</Typography>
        ) : records.map((r) => (
          <Box key={r.id} onClick={r.status === "pending_review" ? () => onReview(r) : undefined}
            sx={{ py: 1.2, borderBottom: `0.5px solid ${COLOR.borderLight}`, cursor: r.status === "pending_review" ? "pointer" : "default" }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: r.status === "pending_review" ? COLOR.warning : COLOR.primary }} />
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: r.status === "pending_review" ? COLOR.warning : COLOR.primary, fontWeight: 600 }}>
                  {r.record_type === "visit" ? "门诊记录" : "问诊总结"}
                </Typography>
                {r.status === "pending_review" && (
                  <Box sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.warning, border: `0.5px solid ${COLOR.warning}`, borderRadius: "3px", px: 0.5 }}>待审核</Box>
                )}
              </Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{r.created_at?.slice(0, 10)}</Typography>
                {r.status === "pending_review" && <Typography sx={{ color: COLOR.text4 }}>→</Typography>}
              </Box>
            </Box>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.3 }}>
              {r.structured?.chief_complaint || r.content}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

/* ── Tasks ── */

function MockTasks() {
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

/* ── Chat ── */

function MockChat({ onBack }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <SubpageHeader title="对话工作区" onBack={onBack} right={<BarButton>清空</BarButton>} />
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
      </Box>
      <Box sx={{ px: 1.5, py: 1, display: "flex", gap: 1, alignItems: "center" }}>
        <Box sx={{ flex: 1, bgcolor: COLOR.surface, borderRadius: 2, px: 1.5, py: 1, fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>输入消息...</Box>
        <Box sx={{ width: 36, height: 36, borderRadius: "50%", bgcolor: COLOR.text4, display: "flex", alignItems: "center", justifyContent: "center", color: COLOR.white, fontSize: 16 }}>▸</Box>
      </Box>
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

/* ── Settings ── */

function MockSettings() {
  return (
    <Box>
      <SubpageHeader title="设置" />
      <SectionLabel>账户</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white, p: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5 }}>
          <Box sx={{ width: 48, height: 48, borderRadius: 1, bgcolor: COLOR.primary, display: "flex", alignItems: "center", justifyContent: "center", color: COLOR.white, fontSize: 20, fontWeight: 600 }}>张</Box>
          <Box>
            <Typography sx={{ fontWeight: 600 }}>张医生</Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>mock_doctor</Typography>
          </Box>
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ color: COLOR.text3 }}>昵称</Typography>
          <Typography>张医生</Typography>
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ color: COLOR.text3 }}>科室专业</Typography>
          <Typography>神经外科</Typography>
        </Box>
      </Box>
      <SectionLabel>工具</SectionLabel>
      <ListCard title="报告模板" subtitle="自定义门诊病历报告格式" right={<Typography sx={{ color: COLOR.text4 }}>→</Typography>} />
      <ListCard title="知识库" subtitle="管理 AI 助手参考资料" right={<Typography sx={{ color: COLOR.text4 }}>→</Typography>} />
      <SectionLabel>通用</SectionLabel>
      <ListCard title="关于" subtitle="版本信息" right={<Typography sx={{ color: COLOR.text4 }}>→</Typography>} />
      <SectionLabel>账户操作</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white, py: 1.5, textAlign: "center" }}>
        <Typography sx={{ color: COLOR.danger, fontSize: TYPE.body.fontSize }}>退出登录</Typography>
      </Box>
    </Box>
  );
}

/* ── Main: Interactive Mock App ── */

export default function MockPages() {
  // Navigation state
  const [tab, setTab] = useState("home");         // bottom nav tab
  const [subpage, setSubpage] = useState(null);    // "patient-detail" | "review" | "chat" | "interview-dialog"
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  function navTo(key) {
    setTab(key);
    setSubpage(null);
    setSelectedPatient(null);
    setSelectedRecord(null);
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

  function openInterviewDialog() {
    setDialogOpen(true);
  }

  function goBack() {
    if (subpage === "review" && selectedPatient) {
      setSubpage("patient-detail");
      setSelectedRecord(null);
    } else {
      setSubpage(null);
      setSelectedPatient(null);
      setSelectedRecord(null);
    }
  }

  // Determine active nav highlight
  const activeTab = subpage === "chat" ? "home" : tab;

  // Render content based on state
  function renderContent() {
    if (subpage === "review" && selectedRecord) {
      return <MockReview record={selectedRecord} onBack={goBack} />;
    }
    if (subpage === "chat") {
      return <MockChat onBack={goBack} />;
    }
    if (subpage === "patient-detail" && selectedPatient) {
      return (
        <Box sx={{ overflowY: "auto", height: "calc(100% - 64px)" }}>
          <MockPatientDetail patient={selectedPatient} onBack={goBack} onReview={openReview} onInterview={openInterviewDialog} />
        </Box>
      );
    }

    switch (tab) {
      case "home": return <MockHome onNav={(key) => key === "chat" ? openChat() : navTo(key)} />;
      case "patients": return (
        <Box sx={{ overflowY: "auto", height: "calc(100% - 64px)" }}>
          <MockPatients onSelectPatient={openPatient} />
        </Box>
      );
      case "tasks": return (
        <Box sx={{ overflowY: "auto", height: "calc(100% - 64px)" }}>
          <MockTasks />
        </Box>
      );
      case "settings": return (
        <Box sx={{ overflowY: "auto", height: "calc(100% - 64px)" }}>
          <MockSettings />
        </Box>
      );
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
        bgcolor: "#ededed",
        transform: "translateZ(0)",
      }}>
        {renderContent()}
        {subpage !== "chat" && <MockBottomNav active={activeTab} onNav={navTo} />}

        {/* Interview complete dialog */}
        <InterviewCompleteDialog
          open={dialogOpen}
          fields={MOCK_INTERVIEW_FIELDS}
          fieldCount={{ filled: Object.keys(MOCK_INTERVIEW_FIELDS).length, total: 14 }}
          onSave={() => setDialogOpen(false)}
          onSaveAndDiagnose={() => { setDialogOpen(false); openReview(MOCK_RECORDS[1]); }}
          onClose={() => setDialogOpen(false)}
        />
      </Box>
    </Box>
  );
}
