/**
 * @route /doctor/my-ai
 *
 * MyAIPage -- "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 */
import { useState } from "react";
import { Badge, Box, CircularProgress, Skeleton, Typography } from "@mui/material";
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
import { useKnowledgeItems, useReviewQueue, useAIActivity } from "../../lib/doctorQueries";
import ConfirmDialog from "../../components/ConfirmDialog";

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

  const loading = kLoading || qLoading || aLoading;
  const knowledge = knowledgeData ?? null;
  const reviewQueue = reviewQueueData || { pending: [], completed: [] };
  const activity = activityData ?? null;

  // Derived values — all stats computed from actual data
  const aiName = `${doctorName || "医生"} 的 AI`;
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
  const [showAddHome, setShowAddHome] = useState(false);
  const isMiniprogram = typeof window !== "undefined" && window.__wxjs_environment === "miniprogram";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      {/* Top bar — no action buttons on main page nav bar */}
      <SubpageHeader title="我的AI" />

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
              onClick={() => navigate(dp("settings/knowledge"))}
            >
              我的知识库
            </AppButton>
            <AppButton
              variant="secondary" size="md" fullWidth
              onClick={() => navigate(dp("settings/knowledge/add"))}
              sx={{ border: `0.5px solid ${COLOR.border}` }}
            >
              继续教AI
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
            avatar={<IconBadge config={ICON_BADGES.review} />}
            title="待审核"
            subtitle="AI建议等你确认"
            right={<InlineBadge count={reviewBadge} />}
            chevron
            onClick={() => navigate(dp("review"))}
          />
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.followup} />}
            title="处理随访"
            subtitle="患者消息可快速处理"
            right={<InlineBadge count={followupBadge} color={COLOR.danger} />}
            chevron
            onClick={() => navigate(`${dp("review")}?tab=replies`)}
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
              onClick={() => setShowAddHome(true)}
              sx={{ borderBottom: "none" }}
            />
          )}
        </Box>

        {/* ── C. 我的方法 (Knowledge Preview) ─────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
          <SectionLabel>
            {knowledgeCount === 0 ? "我的知识库 · 快速入门" : "我的知识库 · 继续教AI"}
          </SectionLabel>
          {knowledgeCount > 0 && (
            <Typography
              onClick={() => navigate(dp("settings/knowledge"))}
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
                onClick={() => navigate(dp("settings/knowledge/add"))}
                chevron
              />
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.new_record} />}
                title="粘贴常用回复"
                subtitle="你常用的回复模板"
                onClick={() => navigate(dp("settings/knowledge/add"))}
                chevron
              />
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.kb_doctor} />}
                title="导入已确认病例"
                subtitle="从病历中提取规则"
                onClick={() => navigate(dp("settings/knowledge/add"))}
                chevron
                sx={{ borderBottom: "none" }}
              />
            </>
          )}
          {loading && topRules.length === 0 && <SectionLoading />}
          {topRules.map((rule, idx) => (
            <KnowledgeCard
              key={rule.id || idx}
              title={rule.title || rule.content?.slice(0, 20) || "规则"}
              summary={rule.summary || rule.content?.slice(0, 40) || ""}
              referenceCount={rule.reference_count || 0}
              source={rule.source}
              date={rule.created_at ? formatRelativeDate(rule.created_at) : ""}
              onClick={() => navigate(`${dp("settings/knowledge")}/${rule.id}`)}
              sx={idx === topRules.length - 1 ? { borderBottom: "none" } : {}}
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

      <ConfirmDialog
        open={showAddHome}
        title="添加到手机桌面"
        confirmLabel="复制链接"
        cancelLabel="知道了"
        onConfirm={() => { navigator.clipboard?.writeText("https://wxaurl.cn/c5C1mGUyd9i").catch(() => {}); setShowAddHome(false); }}
        onCancel={() => setShowAddHome(false)}
        onClose={() => setShowAddHome(false)}
      >
        <Box sx={{ textAlign: "left", fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.8 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, mb: 1 }}>
            点击右上角 <b>···</b> 菜单，选择「添加到桌面」即可像App一样使用。
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
            或复制链接发送给微信好友，对方打开即可添加。
          </Typography>
        </Box>
      </ConfirmDialog>
    </Box>
  );
}
