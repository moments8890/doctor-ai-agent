/**
 * @route /doctor/my-ai
 *
 * MyAIPage -- "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 */
import { useState } from "react";
import { Badge, Box, CircularProgress, IconButton, Skeleton, Typography } from "@mui/material";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import ContentPasteOutlinedIcon from "@mui/icons-material/ContentPasteOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import { useDoctorStore } from "../../store/doctorStore";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import SectionLabel from "../../components/SectionLabel";
import ListCard from "../../components/ListCard";
import KnowledgeCard from "../../components/KnowledgeCard";
import AppButton from "../../components/AppButton";
import NameAvatar from "../../components/NameAvatar";
import IconBadge from "../../components/IconBadge";
import EmptyState from "../../components/EmptyState";
import SectionLoading from "../../components/SectionLoading";
import PullToRefresh from "../../components/PullToRefresh";
import { ICON_BADGES } from "./constants";
import { isWizardDone, clearWizardDone } from "./onboardingWizardState";
import StatColumn from "../../components/StatColumn";
import { TYPE, ICON, COLOR, RADIUS } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
import { useKnowledgeItems, useReviewQueue, useAIActivity, usePersona } from "../../lib/doctorQueries";
import { relativeDate as formatRelativeDate } from "../../utils/time";
import CloseIcon from "@mui/icons-material/Close";

// ── Sub-components ────────────────────────────────────────────────────────────

function AIAvatar({ size = 44 }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: RADIUS.md, flexShrink: 0,
      bgcolor: COLOR.primary,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <Typography sx={{ color: COLOR.white, fontSize: size * 0.45, fontWeight: 600, lineHeight: 1 }}>
        AI
      </Typography>
    </Box>
  );
}

function QuickActionIcon({ bg, children }) {
  return (
    <Box sx={{
      width: 36, height: 36, borderRadius: RADIUS.md, flexShrink: 0,
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
      bgcolor: color, borderRadius: RADIUS.md, px: 1, minWidth: 16, textAlign: "center",
      lineHeight: "18px",
    }}>
      {count}
    </Box>
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

  // React Query-backed data fetching (shared cache — no redundant requests on tab switch)
  const { data: knowledgeData, isLoading: kLoading } = useKnowledgeItems();
  const { data: reviewQueueData, isLoading: qLoading } = useReviewQueue();
  const { data: activityData, isLoading: aLoading } = useAIActivity(3);
  const { data: personaData, isLoading: pLoading } = usePersona();

  const loading = kLoading || qLoading || aLoading || pLoading;
  const knowledge = knowledgeData ?? null;
  const reviewQueue = reviewQueueData || { pending: [], completed: [] };
  const activity = activityData ?? null;

  // Derived values — all stats computed from actual data
  const aiName = `${doctorName || "医生"} 的 AI`;
  const knowledgeList = Array.isArray(knowledge) ? knowledge : (knowledge?.items || []);
  const knowledgeCount = knowledgeList.length;
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
  const [showAddGuide, setShowAddGuide] = useState(false);
  const isMiniprogram = typeof window !== "undefined" && window.__wxjs_environment === "miniprogram";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      {/* Top bar — no action buttons on main page nav bar */}
      <SubpageHeader title="我的AI" />

      {/* AI-generated content disclaimer (WeChat regulation) */}
      <Box sx={{ bgcolor: COLOR.surfaceAlt, px: 2, py: 0.75, textAlign: "center" }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          本服务为AI生成内容，结果仅供参考
        </Typography>
      </Box>

      {/* Scrollable content */}
      <PullToRefresh sx={{ flex: 1 }} pb="80px">

        {/* ── A. Hero Identity Card ──────────────────────────────── */}
        <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {/* Identity row */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 2, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <AIAvatar />
            <Box sx={{ flex: 1 }}>
              <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.text1 }}>
                {aiName}
              </Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.5 }}>
                {knowledgeCount > 0 ? `已学会 ${knowledgeCount} 条知识` : "尚未添加知识"}
              </Typography>
            </Box>
            <Box
              onClick={() => navigate(dp("settings"))}
              sx={{
                display: "flex", alignItems: "center", gap: 0.5,
                cursor: "pointer", px: 1, py: 0.5, borderRadius: RADIUS.md,
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
            <StatColumn value={pendingReview} label="待确认" onClick={() => navigate(`${dp("review")}?tab=pending`)} />
            <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.5 }} />
            <StatColumn value={completedToday} label="今日处理" onClick={() => navigate(`${dp("review")}?tab=completed`)} />
          </Box>

          {/* Onboarding hint when no knowledge yet */}
          {!loading && knowledgeCount === 0 && (
            <Box sx={{ px: 2, py: 1 }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, lineHeight: 1.5 }}>
                上传你的诊疗规则或常用模板后，它才会按你的方法工作
              </Typography>
            </Box>
          )}

          {/* CTA row */}
          <Box sx={{ display: "flex", gap: 1, px: 2, py: 1.5 }}>
            <AppButton
              variant="primary" size="md" fullWidth
              onClick={() => navigate(dp("settings/persona"))}
            >
              编辑人设
            </AppButton>
            <AppButton
              variant="secondary" size="md" fullWidth
              onClick={() => navigate(dp("settings/knowledge/add"))}
              sx={{ border: `0.5px solid ${COLOR.border}` }}
            >
              添加知识
            </AppButton>
          </Box>
        </Box>

        {/* ── B. Quick Actions ───────────────────────────────────── */}
        <SectionLabel>快捷入口</SectionLabel>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.new_record} />}
            title="新建病历"
            subtitle="语音或文字录入患者信息"
            chevron
            onClick={() => navigate(`${dp("patients")}?action=new`)}
          />
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.qr_code} />}
            title="患者预问诊码"
            subtitle="患者扫码自助填写病史"
            chevron
            onClick={() => navigate(dp("settings/qr"))}
            sx={isWizardDone(doctorId) ? {} : { borderBottom: "none" }}
          />
          {isWizardDone(doctorId) && (
            <ListCard
              avatar={<IconBadge config={ICON_BADGES.kb_doctor} />}
              title="重新体验引导"
              subtitle="再次走一遍产品引导流程"
              chevron
              onClick={() => { clearWizardDone(doctorId); navigate(`${dp("onboarding")}?step=1`); }}
              sx={isMiniprogram ? {} : { borderBottom: "none" }}
            />
          )}
          {isMiniprogram && (
            <ListCard
              avatar={<IconBadge config={ICON_BADGES.add_home} />}
              title="添加到手机桌面"
              subtitle="像App一样一键打开"
              chevron
              onClick={() => setShowAddGuide(true)}
              sx={{ borderBottom: "none" }}
            />
          )}
        </Box>

        {/* ── C1. 我的AI人设 (Persona) ─────────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
          <SectionLabel>
            <Box component="span">我的AI人设</Box>
            <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, ml: 1 }}>
              决定AI怎么说话
            </Typography>
          </SectionLabel>
          <Typography
            onClick={() => navigate(dp("settings/persona"))}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}
          >
            编辑 ›
          </Typography>
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {pLoading && <SectionLoading />}
          {!pLoading && (() => {
            const allRules = personaData ? Object.values(personaData.fields || {}).flat() : [];
            const hasRules = allRules.length > 0;
            const previewText = hasRules
              ? allRules.slice(0, 3).map(r => r.text).join("；") + (allRules.length > 3 ? "…" : "")
              : "尚未设置，点击编辑开始配置";
            return (
              <Box
                onClick={() => navigate(dp("settings/persona"))}
                sx={{ px: 2, py: 1.5, cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}
              >
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: hasRules ? COLOR.text2 : COLOR.text4, lineHeight: 1.7 }}>
                  {previewText}
                </Typography>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 1 }}>
                  已学习 {personaData?.edit_count || 0} 次编辑
                </Typography>
              </Box>
            );
          })()}
        </Box>

        {/* ── C2. 我的知识库 (Knowledge) ───────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
          <SectionLabel>
            <Box component="span">我的知识库</Box>
            <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, ml: 1 }}>
              决定AI知道什么
            </Typography>
          </SectionLabel>
          {knowledgeList.length > 0 && (
            <Typography
              onClick={() => navigate(dp("settings/knowledge"))}
              sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}
            >
              全部 {knowledgeList.length} 条 ›
            </Typography>
          )}
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {knowledgeList.length === 0 && !loading && (
            <>
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.upload} />}
                title="上传指南"
                subtitle="PDF / Word 文档"
                onClick={() => navigate(dp("settings/knowledge/add"))}
                chevron
              />
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.new_record} />}
                title="粘贴常用回复"
                subtitle="你常用的回复模板"
                onClick={() => navigate(dp("settings/knowledge/add"))}
                chevron
                sx={{ borderBottom: "none" }}
              />
            </>
          )}
          {loading && knowledgeList.length === 0 && <SectionLoading />}
          {knowledgeList.slice(0, 3).map((rule, idx) => (
            <KnowledgeCard
              key={rule.id || idx}
              title={rule.title || rule.text?.slice(0, 20) || "规则"}
              summary={rule.summary || rule.text?.slice(0, 40) || ""}
              referenceCount={rule.reference_count || 0}
              source={rule.source}
              date={rule.created_at ? formatRelativeDate(rule.created_at) : ""}
              onClick={() => navigate(`${dp("settings/knowledge")}/${rule.id}`)}
              sx={idx === Math.min(knowledgeList.length, 3) - 1 ? { borderBottom: "none" } : {}}
            />
          ))}
        </Box>

        {/* ── D. 最近由AI处理 ────────────────────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
          <SectionLabel>最近由AI处理</SectionLabel>
          <Typography
            onClick={() => navigate(dp("review"))}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}
          >
            全部 {activityList.length} 条 ›
          </Typography>
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {recentActivity.length === 0 && !loading && (
            <EmptyState title="暂无AI处理记录" />
          )}
          {loading && recentActivity.length === 0 && <SectionLoading />}
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
                      bgcolor: badge.color, borderRadius: RADIUS.sm, px: 0.5, py: 0.5,
                      lineHeight: "16px", ml: 0.5, flexShrink: 0,
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
                  if (item.type === "task" && item.task_id) navigate(`${dp("tasks")}/${item.task_id}`);
                  else if (item.type === "diagnosis" && item.record_id) navigate(`${dp("review")}/${item.record_id}`);
                  else if (item.type === "draft" && item.patient_id) navigate(`${dp("patients")}/${item.patient_id}?view=chat`);
                  else if (item.patient_id) navigate(`${dp("patients")}/${item.patient_id}`);
                  else navigate(dp("review"));
                }}
                sx={idx === recentActivity.length - 1 ? { borderBottom: "none" } : {}}
              />
            );
          })}
        </Box>

      </PullToRefresh>

      {showAddGuide && (
        <Box
          onClick={() => setShowAddGuide(false)}
          sx={{
            position: "fixed", inset: 0, zIndex: 9999,
            bgcolor: "rgba(0,0,0,0.65)",
            display: "flex", flexDirection: "column", alignItems: "flex-end",
            pt: "12px", pr: "24px",
          }}
        >
          {/* Arrow pointing to ··· capsule */}
          <Box sx={{
            width: 0, height: 0,
            borderLeft: "12px solid transparent",
            borderRight: "12px solid transparent",
            borderBottom: "16px solid #fff",
            mr: "42px", mb: "-2px",
          }} />
          {/* Instruction card */}
          <Box sx={{
            bgcolor: "#fff", borderRadius: RADIUS.lg, px: 2.5, py: 2,
            maxWidth: 260, position: "relative",
          }}>
            <IconButton size="small" onClick={() => setShowAddGuide(false)} sx={{ position: "absolute", top: 4, right: 4, color: COLOR.text4 }}>
              <CloseIcon sx={{ fontSize: 18 }} />
            </IconButton>
            <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.text1, mb: 1 }}>
              添加到手机桌面
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.7 }}>
              1. 点击右上角 <b>···</b> 按钮
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.7 }}>
              2. 选择「添加到桌面」
            </Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 1 }}>
              添加后可像App一样一键打开
            </Typography>
          </Box>
        </Box>
      )}
    </Box>
  );
}
