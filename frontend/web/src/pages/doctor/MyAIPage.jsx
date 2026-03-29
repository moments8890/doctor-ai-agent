/**
 * @route /doctor/my-ai
 *
 * MyAIPage -- "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 */
import { useEffect, useState } from "react";
import { Badge, Box, CircularProgress, Skeleton, Typography } from "@mui/material";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import ContentPasteOutlinedIcon from "@mui/icons-material/ContentPasteOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import { useDoctorStore } from "../../store/doctorStore";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import SectionLabel from "../../components/SectionLabel";
import ListCard from "../../components/ListCard";
import KnowledgeCard from "../../components/KnowledgeCard";
import AppButton from "../../components/AppButton";
import NameAvatar from "../../components/NameAvatar";
import IconBadge from "../../components/IconBadge";
import {
  ICON_BADGES,
  getOnboardingState,
  isOnboardingStepDone,
  ONBOARDING_STEP,
} from "./constants";
import { TYPE, ICON, COLOR } from "../../theme";

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  const now = new Date();
  const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "今天";
  if (diffDays === 1) return "昨天";
  if (diffDays < 7) return `${diffDays}天前`;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function AIAvatar({ size = 44 }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: "6px", flexShrink: 0,
      bgcolor: COLOR.primary,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <Typography sx={{ color: COLOR.white, fontSize: size * 0.45, fontWeight: 600, lineHeight: 1 }}>
        AI
      </Typography>
    </Box>
  );
}

function StatColumn({ value, label, onClick }) {
  return (
    <Box onClick={onClick} sx={{ flex: 1, textAlign: "center", cursor: onClick ? "pointer" : "default", "&:active": onClick ? { opacity: 0.5 } : {} }}>
      <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.text1 }}>
        {value ?? <Skeleton width={20} sx={{ mx: "auto" }} />}
      </Typography>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 0.2 }}>
        {label}
      </Typography>
    </Box>
  );
}

function QuickActionIcon({ bg, children }) {
  return (
    <Box sx={{
      width: 36, height: 36, borderRadius: "6px", flexShrink: 0,
      bgcolor: bg, display: "flex", alignItems: "center", justifyContent: "center",
      color: COLOR.white, fontSize: 16,
    }}>
      {children}
    </Box>
  );
}

function InlineBadge({ count, color = COLOR.warning }) {
  if (!count) return null;
  return (
    <Box sx={{
      fontSize: TYPE.micro.fontSize, fontWeight: 500, color: COLOR.white,
      bgcolor: color, borderRadius: "8px", px: 0.75, minWidth: 16, textAlign: "center",
      lineHeight: "18px",
    }}>
      {count}
    </Box>
  );
}

function ChecklistPill({ done, locked, current }) {
  let text = "去查看";
  let bg = COLOR.surface;
  let color = COLOR.text4;
  if (done) {
    text = "已完成";
    bg = COLOR.primaryLight;
    color = COLOR.primary;
  } else if (locked) {
    text = "待解锁";
  } else if (current) {
    text = "下一步";
    bg = COLOR.warningLight;
    color = COLOR.warning;
  }
  return (
    <Box
      sx={{
        fontSize: TYPE.micro.fontSize,
        fontWeight: 600,
        color,
        bgcolor: bg,
        px: 0.9,
        py: 0.25,
        borderRadius: "999px",
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </Box>
  );
}

function OnboardingChecklist({ rows, completedCount }) {
  return (
    <>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
        <SectionLabel>开始体验</SectionLabel>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          {completedCount}/{rows.length} 完成
        </Typography>
      </Box>
      <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        {rows.map((row, index) => (
          <ListCard
            key={row.key}
            avatar={<IconBadge config={row.icon} />}
            title={row.title}
            subtitle={row.subtitle}
            right={<ChecklistPill done={row.done} locked={row.locked} current={row.current} />}
            chevron={!row.locked}
            onClick={row.locked ? undefined : row.onClick}
            sx={index === rows.length - 1 ? { borderBottom: "none" } : undefined}
          />
        ))}
      </Box>
    </>
  );
}

// RuleDot removed — knowledge preview now uses ListCard + IconBadge

// ── Activity helpers ─────────────────────────────────────────────────────────

/** Map activity type to a short Chinese label and badge color. */
function activityBadge(item) {
  const desc = (item.description || "").toLowerCase();
  if (desc.includes("紧急") || desc.includes("急查")) return { label: "紧急", color: COLOR.danger };
  if (item.type === "draft") return { label: "AI已起草回复", color: COLOR.primary };
  if (item.type === "diagnosis") return { label: "AI诊断建议", color: COLOR.warning };
  if (item.type === "citation") return { label: "知识库引用", color: COLOR.text4 };
  if (item.type === "task") return { label: "待办任务", color: COLOR.warning };
  return { label: "AI处理", color: COLOR.text4 };
}

/** Format an ISO timestamp to a short relative label. */
function formatActivityTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now - d;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}小时前`;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (dt.getTime() === today.getTime()) return `今天 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (dt.getTime() === yesterday.getTime()) return "昨天";
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MyAIPage({ doctorId }) {
  const navigate = useAppNavigate();
  const { doctorName } = useDoctorStore();
  const api = useApi();

  // State
  const [knowledge, setKnowledge] = useState(null);
  const [reviewQueue, setReviewQueue] = useState(null);
  const [activity, setActivity] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch all dashboard data
  useEffect(() => {
    if (!doctorId) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      const fetchKnowledge = api.getKnowledgeItems || (() => Promise.resolve(null));
      const fetchReview = api.getReviewQueue || (() => Promise.resolve(null));
      const fetchActivity = api.fetchAIActivity || (() => Promise.resolve(null));

      const results = await Promise.allSettled([
        fetchKnowledge(doctorId).catch(() => null),
        fetchReview(doctorId).catch(() => null),
        fetchActivity(doctorId, 3).catch(() => null),
      ]);
      if (cancelled) return;
      setKnowledge(results[0].status === "fulfilled" ? results[0].value : null);
      setReviewQueue(results[1].status === "fulfilled" ? results[1].value : null);
      setActivity(results[2].status === "fulfilled" ? results[2].value : null);
      setLoading(false);
    }

    load();
    return () => { cancelled = true; };
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Derived values — all stats computed from actual data
  const aiName = `${doctorName || "医生"}AI`;
  const knowledgeList = Array.isArray(knowledge) ? knowledge : (knowledge?.items || []);
  const knowledgeCount = knowledgeList.length;
  const topRules = knowledgeList.slice(0, 3);
  const activityList = Array.isArray(activity) ? activity : (activity?.activity || activity?.items || []);
  const recentActivity = activityList.slice(0, 3);

  const weekCitations = loading ? null : knowledgeList.reduce((sum, k) => sum + (k.reference_count || 0), 0);
  const pendingReview = loading ? null : (reviewQueue?.pending || []).length;
  const completedToday = loading ? null : (() => {
    const today = new Date().toISOString().slice(0, 10);
    return (reviewQueue?.completed || []).filter((c) => (c.time || "").includes(today) || (c.time || "").includes("刚刚") || (c.time || "").includes("今天")).length;
  })();

  // Badge counts for quick actions
  const reviewBadge = pendingReview || 0;
  const followupBadge = 0; // TODO: derive from tasks data when fetched
  const onboarding = getOnboardingState(doctorId);
  const doneKnowledge = isOnboardingStepDone(onboarding, ONBOARDING_STEP.knowledge);
  const doneDiagnosis = isOnboardingStepDone(onboarding, ONBOARDING_STEP.diagnosis);
  const doneReply = isOnboardingStepDone(onboarding, ONBOARDING_STEP.reply);
  const donePreview = isOnboardingStepDone(onboarding, ONBOARDING_STEP.patientPreview);
  const doneTasks = isOnboardingStepDone(onboarding, ONBOARDING_STEP.followupTask);
  const checklistRows = [
    {
      key: ONBOARDING_STEP.knowledge,
      title: "教 AI 一条规则",
      subtitle: "从网址、图片/文件或文本开始",
      icon: ICON_BADGES.kb_add,
      done: doneKnowledge,
      locked: false,
      current: !doneKnowledge,
      onClick: () => navigate("/doctor/settings/knowledge/add?onboarding=1"),
    },
    {
      key: ONBOARDING_STEP.diagnosis,
      title: "看 AI 如何用于诊断审核",
      subtitle: onboarding.lastSavedRuleTitle ? `基于“${onboarding.lastSavedRuleTitle}”进入示例` : "打开一个带来源的审核示例",
      icon: ICON_BADGES.review,
      done: doneDiagnosis,
      locked: !doneKnowledge,
      current: doneKnowledge && !doneDiagnosis,
      onClick: () => navigate("/doctor/review?tab=pending&source=knowledge_proof"),
    },
    {
      key: ONBOARDING_STEP.reply,
      title: "看 AI 如何起草患者回复",
      subtitle: "先看患者原始消息，再看 AI 草稿",
      icon: ICON_BADGES.followup,
      done: doneReply,
      locked: !doneDiagnosis,
      current: doneKnowledge && doneDiagnosis && !doneReply,
      onClick: () => navigate("/doctor/review?tab=replies&source=reply_proof"),
    },
    {
      key: ONBOARDING_STEP.patientPreview,
      title: "体验患者预问诊",
      subtitle: "先建档，再生成可扫码/可预览入口",
      icon: ICON_BADGES.qr_code,
      done: donePreview,
      locked: !doneDiagnosis || !doneReply,
      current: doneDiagnosis && doneReply && !donePreview,
      onClick: () => navigate("/doctor/settings/qr?onboarding=1"),
    },
    {
      key: ONBOARDING_STEP.followupTask,
      title: "查看生成任务",
      subtitle: doneTasks ? "已完成审核后的随访任务" : "审核完成后会自动高亮任务",
      icon: ICON_BADGES.task_general,
      done: doneTasks,
      locked: !donePreview && !doneTasks,
      current: donePreview && !doneTasks,
      onClick: () => {
        const taskIds = (onboarding.lastFollowUpTaskIds || []).join(",");
        const origin = doneTasks ? "review_finalize" : "patient_submit";
        const highlight = taskIds || onboarding.lastReviewTaskId || "";
        navigate(`/doctor/tasks?tab=followups${highlight ? `&highlight_task_ids=${highlight}` : ""}&origin=${origin}`);
      },
    },
  ];
  const completedChecklistCount = checklistRows.filter((row) => row.done).length;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      {/* Top bar — no action buttons on main page nav bar */}
      <SubpageHeader title="我的AI" />

      {/* Scrollable content */}
      <Box sx={{ flex: 1, overflow: "auto", pb: "80px" }}>

        {/* ── A. Hero Identity Card ──────────────────────────────── */}
        <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {/* Identity row */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.75, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <AIAvatar />
            <Box sx={{ flex: 1 }}>
              <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.text1 }}>
                {aiName}
              </Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.2 }}>
                {knowledgeCount > 0 ? `已学会 ${knowledgeCount} 条知识` : "尚未添加知识"}
              </Typography>
            </Box>
            <Box
              onClick={() => navigate("/doctor/settings")}
              sx={{
                display: "flex", alignItems: "center", gap: 0.5,
                cursor: "pointer", px: 1, py: 0.5, borderRadius: "8px",
                "&:active": { bgcolor: COLOR.surfaceAlt },
              }}
            >
              <SettingsOutlinedIcon sx={{ fontSize: ICON.lg, color: COLOR.text4 }} />
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>设置</Typography>
            </Box>
          </Box>

          {/* Stats row */}
          <Box sx={{ display: "flex", py: 1.5, px: 2, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <StatColumn value={weekCitations} label="7天引用" />
            <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.5 }} />
            <StatColumn value={pendingReview} label="待确认" onClick={() => navigate("/doctor/review?tab=pending")} />
            <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.5 }} />
            <StatColumn value={completedToday} label="今日处理" onClick={() => navigate("/doctor/tasks?tab=sent")} />
          </Box>

          {/* Onboarding hint when no knowledge yet */}
          {!loading && knowledgeCount === 0 && (
            <Box sx={{ px: 2, py: 1.2 }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, lineHeight: 1.5 }}>
                上传你的诊疗规则或常用模板后，它才会按你的方法工作
              </Typography>
            </Box>
          )}

          {/* CTA row */}
          <Box sx={{ display: "flex", gap: 1.2, px: 2, py: 1.5 }}>
            <AppButton
              variant="primary" size="md" fullWidth
              onClick={() => navigate("/doctor/settings/knowledge")}
            >
              我的知识库
            </AppButton>
            <AppButton
              variant="secondary" size="md" fullWidth
              onClick={() => navigate("/doctor/settings/knowledge/add")}
              sx={{ border: `0.5px solid ${COLOR.border}` }}
            >
              继续教AI
            </AppButton>
          </Box>
        </Box>

        <OnboardingChecklist rows={checklistRows} completedCount={completedChecklistCount} />

        {/* ── B. Quick Actions ───────────────────────────────────── */}
        <SectionLabel>快捷入口</SectionLabel>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.new_record} />}
            title="新建病历"
            subtitle="语音或文字录入患者信息"
            chevron
            onClick={() => navigate("/doctor/patients/new")}
          />
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.review} />}
            title="待审核"
            subtitle="AI建议等你确认"
            right={<InlineBadge count={reviewBadge} />}
            chevron
            onClick={() => navigate("/doctor/review")}
          />
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.followup} />}
            title="处理随访"
            subtitle="患者消息可快速处理"
            right={<InlineBadge count={followupBadge} color="#ef4444" />}
            chevron
            onClick={() => navigate("/doctor/review?tab=replies")}
          />
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.qr_code} />}
            title="患者预问诊码"
            subtitle="患者扫码自助填写病史"
            chevron
            onClick={() => navigate("/doctor/settings/qr")}
            sx={{ borderBottom: "none" }}
          />
        </Box>

        {/* ── C. 我的方法 (Knowledge Preview) ─────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
          <SectionLabel>
            {knowledgeCount === 0 ? "我的知识库 · 快速入门" : "我的知识库 · 继续教AI"}
          </SectionLabel>
          {knowledgeCount > 0 && (
            <Typography
              onClick={() => navigate("/doctor/settings/knowledge")}
              sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}
            >
              全部 {knowledgeCount} 条 ›
            </Typography>
          )}
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {topRules.length === 0 && !loading && (
            <>
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.upload} />}
                title="上传指南"
                subtitle="PDF / Word 文档"
                onClick={() => navigate("/doctor/settings/knowledge/add")}
                chevron
              />
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.new_record} />}
                title="粘贴常用回复"
                subtitle="你常用的回复模板"
                onClick={() => navigate("/doctor/settings/knowledge/add")}
                chevron
              />
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.kb_doctor} />}
                title="导入已确认病例"
                subtitle="从病历中提取规则"
                onClick={() => navigate("/doctor/chat")}
                chevron
                sx={{ borderBottom: "none" }}
              />
            </>
          )}
          {loading && topRules.length === 0 && (
            <Box sx={{ py: 3, display: "flex", justifyContent: "center" }}>
              <CircularProgress size={20} sx={{ color: COLOR.text4 }} />
            </Box>
          )}
          {topRules.map((rule, idx) => (
            <KnowledgeCard
              key={rule.id || idx}
              title={rule.title || rule.content?.slice(0, 20) || "规则"}
              summary={rule.summary || rule.content?.slice(0, 40) || ""}
              referenceCount={rule.reference_count || 0}
              source={rule.source}
              date={rule.created_at ? formatRelativeDate(rule.created_at) : ""}
              onClick={() => navigate(`/doctor/settings/knowledge/${rule.id}`)}
              sx={idx === topRules.length - 1 ? { borderBottom: "none" } : {}}
            />
          ))}
        </Box>

        {/* ── D. 最近由AI处理 ────────────────────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
          <SectionLabel>最近由AI处理</SectionLabel>
          <Typography
            onClick={() => navigate("/doctor/tasks")}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}
          >
            全部 {activityList.length} 条 ›
          </Typography>
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {recentActivity.length === 0 && !loading && (
            <Box sx={{ py: 3, textAlign: "center" }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
                暂无AI处理记录
              </Typography>
            </Box>
          )}
          {loading && recentActivity.length === 0 && (
            <Box sx={{ py: 3, display: "flex", justifyContent: "center" }}>
              <CircularProgress size={20} sx={{ color: COLOR.text4 }} />
            </Box>
          )}
          {recentActivity.map((item, idx) => {
            const badge = activityBadge(item);
            const timeStr = formatActivityTime(item.timestamp);
            return (
              <ListCard
                key={item.id || idx}
                avatar={<NameAvatar name={item.patient_name || "?"} size={36} />}
                title={
                  <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                    {item.patient_name || "患者"}
                    <Box component="span" sx={{
                      fontSize: TYPE.micro.fontSize, fontWeight: 500, color: COLOR.white,
                      bgcolor: badge.color, borderRadius: "4px", px: 0.6, py: 0.1,
                      lineHeight: "16px", ml: 0.3, flexShrink: 0,
                    }}>
                      {badge.label}
                    </Box>
                  </Box>
                }
                subtitle={item.description || item.action_description || "AI处理"}
                right={
                  <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, whiteSpace: "nowrap" }}>
                    {timeStr}
                  </Typography>
                }
                onClick={() => {
                  if (item.type === "diagnosis" && item.record_id) navigate(`/doctor/review/${item.record_id}`);
                  else if (item.patient_id) navigate(`/doctor/patients/${item.patient_id}`);
                  else navigate("/doctor/tasks");
                }}
                sx={idx === recentActivity.length - 1 ? { borderBottom: "none" } : {}}
              />
            );
          })}
        </Box>

      </Box>
    </Box>
  );
}
