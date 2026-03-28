/**
 * @route /doctor/my-ai
 *
 * MyAIPage -- "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 */
import { useEffect, useState } from "react";
import { Badge, Box, CircularProgress, Skeleton, Typography } from "@mui/material";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import ContentPasteOutlinedIcon from "@mui/icons-material/ContentPasteOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import { useDoctorStore } from "../../store/doctorStore";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import SectionLabel from "../../components/SectionLabel";
import ListCard from "../../components/ListCard";
import AppButton from "../../components/AppButton";
import PatientAvatar from "../../components/PatientAvatar";
import { TYPE, ICON, COLOR } from "../../theme";

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

function RuleDot({ color = COLOR.primary }) {
  return (
    <Box sx={{
      width: 6, height: 6, borderRadius: "50%", bgcolor: color,
      flexShrink: 0, mt: "7px",
    }} />
  );
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
  const recentActivity = activityList.slice(0, 4);

  const weekCitations = loading ? null : knowledgeList.reduce((sum, k) => sum + (k.reference_count || 0), 0);
  const pendingReview = loading ? null : (reviewQueue?.pending || []).length;
  const completedToday = loading ? null : (() => {
    const today = new Date().toISOString().slice(0, 10);
    return (reviewQueue?.completed || []).filter((c) => (c.time || "").includes(today) || (c.time || "").includes("刚刚") || (c.time || "").includes("今天")).length;
  })();

  // Badge counts for quick actions
  const reviewBadge = pendingReview || 0;
  const followupBadge = 0; // TODO: derive from tasks data when fetched

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

        {/* ── B. Quick Actions ───────────────────────────────────── */}
        <SectionLabel>快捷入口</SectionLabel>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <ListCard
            avatar={<QuickActionIcon bg="#07C160"><ContentPasteOutlinedIcon sx={{ fontSize: 18, color: "#fff" }} /></QuickActionIcon>}
            title="新建病历"
            subtitle="语音或文字录入患者信息"
            chevron
            onClick={() => navigate("/doctor/patients/new")}
          />
          <ListCard
            avatar={<QuickActionIcon bg={COLOR.warning}><CheckCircleOutlineIcon sx={{ fontSize: 18, color: "#fff" }} /></QuickActionIcon>}
            title="待审核"
            subtitle="AI建议等你确认"
            right={<InlineBadge count={reviewBadge} />}
            chevron
            onClick={() => navigate("/doctor/review")}
          />
          <ListCard
            avatar={<QuickActionIcon bg={COLOR.accent}><ChatOutlinedIcon sx={{ fontSize: 18, color: "#fff" }} /></QuickActionIcon>}
            title="处理随访"
            subtitle="患者消息可快速处理"
            right={<InlineBadge count={followupBadge} color="#ef4444" />}
            chevron
            onClick={() => navigate("/doctor/tasks")}
          />
          <ListCard
            avatar={<QuickActionIcon bg={COLOR.primary}><QrCode2OutlinedIcon sx={{ fontSize: 18, color: "#fff" }} /></QuickActionIcon>}
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
                avatar={<UploadFileOutlinedIcon sx={{ fontSize: 20, color: COLOR.primary }} />}
                title="上传指南"
                subtitle="PDF / Word 文档"
                onClick={() => navigate("/doctor/settings/knowledge/add")}
                chevron
              />
              <ListCard
                avatar={<ContentPasteOutlinedIcon sx={{ fontSize: 20, color: COLOR.primary }} />}
                title="粘贴常用回复"
                subtitle="你常用的回复模板"
                onClick={() => navigate("/doctor/settings/knowledge/add")}
                chevron
              />
              <ListCard
                avatar={<AssignmentOutlinedIcon sx={{ fontSize: 20, color: COLOR.primary }} />}
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
            <Box
              key={rule.id || idx}
              onClick={() => navigate(`/doctor/settings/knowledge/${rule.id}`)}
              sx={{
                display: "flex", alignItems: "flex-start", gap: 1.2,
                px: 2, py: 1.5, cursor: "pointer",
                borderBottom: idx < topRules.length - 1 ? `0.5px solid ${COLOR.borderLight}` : "none",
                "&:active": { bgcolor: COLOR.surface },
              }}
            >
              <RuleDot color={rule.status === "pending" ? COLOR.warning : COLOR.primary} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>
                  {rule.title || rule.content?.slice(0, 20) || "规则"}
                </Typography>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.2, lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {rule.summary || rule.content?.slice(0, 40) || ""}
                </Typography>
              </Box>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: rule.status === "pending" ? COLOR.warning : COLOR.text4, flexShrink: 0 }}>
                {rule.status === "pending" ? "待确认" : (rule.usage_label || "")}
              </Typography>
            </Box>
          ))}
        </Box>

        {/* ── D. 最近由AI处理 ────────────────────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
          <SectionLabel>最近由AI处理</SectionLabel>
          <Typography
            onClick={() => navigate("/doctor/tasks")}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}
          >
            全部 ›
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
          {recentActivity.map((item, idx) => (
            <ListCard
              key={item.id || idx}
              avatar={<PatientAvatar name={item.patient_name || "?"} size={36} />}
              title={item.patient_name || "患者"}
              subtitle={item.description || item.action_description || "AI处理"}
              right={
                item.status === "pending"
                  ? <InlineBadge count="待确认" />
                  : item.time_label
                    ? <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{item.time_label}</Typography>
                    : null
              }
              onClick={() => {
                if (item.type === "draft" || item.type === "citation") navigate("/doctor/tasks?tab=messages");
                else if (item.type === "diagnosis" && item.record_id) navigate(`/doctor/review/${item.record_id}`);
                else if (item.type === "task") navigate("/doctor/tasks?tab=followups");
                else if (item.patient_id) navigate(`/doctor/patients/${item.patient_id}`);
              }}
              sx={idx === recentActivity.length - 1 ? { borderBottom: "none" } : {}}
            />
          ))}
        </Box>

      </Box>
    </Box>
  );
}
