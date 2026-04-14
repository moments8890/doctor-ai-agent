/**
 * @route /doctor/my-ai
 *
 * MyAIPage -- "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 */
import { useState } from "react";
import { Box, IconButton, Typography } from "@mui/material";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import AddOutlinedIcon from "@mui/icons-material/AddOutlined";
import { useDoctorStore } from "../../store/doctorStore";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import SectionLabel from "../../components/SectionLabel";
import KnowledgeCard from "../../components/KnowledgeCard";
import IconBadge from "../../components/IconBadge";
import EmptyState from "../../components/EmptyState";
import SectionLoading from "../../components/SectionLoading";
import PullToRefresh from "../../components/PullToRefresh";
import { ICON_BADGES } from "./constants";
import StatColumn from "../../components/StatColumn";
import { TYPE, ICON, COLOR, RADIUS } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
import { useKnowledgeItems, useReviewQueue, usePersona, useTodaySummary } from "../../lib/doctorQueries";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
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




// ── Main page ─────────────────────────────────────────────────────────────────

export default function MyAIPage({ doctorId }) {
  const navigate = useAppNavigate();
  const { doctorName } = useDoctorStore();

  // React Query-backed data fetching (shared cache — no redundant requests on tab switch)
  const { data: knowledgeData, isLoading: kLoading } = useKnowledgeItems();
  const { data: reviewQueueData, isLoading: qLoading } = useReviewQueue();
  const { data: personaData, isLoading: pLoading } = usePersona();
  const { data: summaryData, isLoading: sLoading, isError: sError } = useTodaySummary();

  const loading = kLoading || qLoading || pLoading;
  const knowledge = knowledgeData ?? null;
  const reviewQueue = reviewQueueData || { pending: [], completed: [] };

  // Derived values — all stats computed from actual data
  const displayName = doctorName || "医生";
  const knowledgeListRaw = Array.isArray(knowledge) ? knowledge : (knowledge?.items || []);
  const knowledgeList = knowledgeListRaw.filter((k) => k.category !== "persona");
  const knowledgeCount = knowledgeList.length;

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

  // Persona summary — single line for the bar
  const personaSummary = (() => {
    if (pLoading) return null;
    const summary = personaData?.summary_text || "";
    if (!summary) {
      const rules = personaData ? Object.values(personaData.fields || {}).flat() : [];
      return rules.length > 0 ? rules.slice(0, 3).map(r => r.text).join(" · ") : "";
    }
    // Extract first few keywords from markdown sections
    const items = summary.split(/[·\n###]/).map(s => s.trim()).filter(s => s && s.length < 20);
    return items.slice(0, 4).join(" · ");
  })();

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="AI助手" />

      <PullToRefresh sx={{ flex: 1 }} pb="80px">

        {/* ── 1. Identity header ─────────────────────────────────── */}
        <Box sx={{ bgcolor: COLOR.white, px: 2, py: 2, display: "flex", alignItems: "center", gap: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
          <AIAvatar />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.text1 }}>
              {displayName}的助手
            </Typography>
            <Typography onClick={(e) => { e.stopPropagation(); navigate(dp("settings/persona")); }}
              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.25,
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                cursor: "pointer", "&:active": { opacity: 0.7 } }}>
              AI风格：{personaSummary || "设置你的AI风格"}
            </Typography>
          </Box>
          <Box onClick={() => navigate(dp("settings"))}
            sx={{ p: 1, cursor: "pointer", borderRadius: RADIUS.md, "&:active": { bgcolor: COLOR.surfaceAlt } }}>
            <SettingsOutlinedIcon sx={{ fontSize: ICON.lg, color: COLOR.text4 }} />
          </Box>
        </Box>

        {/* ── 2. Stats row ─────────────────────────────────────────── */}
        <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <Box sx={{ display: "flex", py: 1.5, px: 2 }}>
            <StatColumn value={pendingReview} label="待处理" onClick={() => navigate(`${dp("review")}?tab=pending`)}
              sx={pendingReview > 0 ? { "& .stat-value": { color: COLOR.danger } } : {}} />
            <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.5 }} />
            <StatColumn value={completedToday} label="今日完成" onClick={() => navigate(`${dp("review")}?tab=completed`)} />
            <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.5 }} />
            <StatColumn value={weekCitations} label="7天引用" />
          </Box>
        </Box>

        {/* ── 3. Today Summary (LLM-generated, single narrative) ── */}
        {summaryData && summaryData.mode !== "empty" && summaryData.summary && (
          <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1.5 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.75 }}>
              <AutoAwesomeOutlinedIcon sx={{ fontSize: 14, color: COLOR.primary }} />
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, fontWeight: 600 }}>今日摘要</Typography>
            </Box>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.7 }}>
              {summaryData.summary.replace(/\s*\[KB-\d+\]/g, "")}
            </Typography>
            {/* Render item titles as tappable inline links below the paragraph */}
            {summaryData.items?.length > 0 && (
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, mt: 1 }}>
                {summaryData.items.map((item, idx) => (
                  <Box key={item.id || idx}
                    onClick={() => {
                      if (item.task_id) navigate(`${dp("tasks")}/${item.task_id}`);
                      else if (item.patient_id) navigate(`${dp("patients")}/${item.patient_id}`);
                      else if (item.kind === "knowledge_gap") navigate(dp("settings/knowledge/add"));
                    }}
                    sx={{
                      fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer",
                      px: 1, py: 0.25, borderRadius: RADIUS.sm, bgcolor: COLOR.primaryLight,
                      "&:active": { opacity: 0.7 },
                    }}>
                    {item.patient_name || item.title.replace(/\s*\[KB-\d+\]/g, "").slice(0, 15)}
                  </Box>
                ))}
              </Box>
            )}
          </Box>
        )}
        {sLoading && !sError && (
          <Box sx={{ px: 2, py: 1.5 }}>
            <SectionLoading rows={2} />
          </Box>
        )}
        {summaryData && summaryData.mode === "empty" && summaryData.summary && (
          <Box sx={{ px: 2, py: 1.5 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, textAlign: "center" }}>
              {summaryData.summary}
            </Typography>
          </Box>
        )}

        {/* ── 4. Quick tools ──────────────────────────────────────── */}
        <SectionLabel>快捷工具</SectionLabel>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`,
          display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 0 }}>
          {[
            { config: ICON_BADGES.new_record, label: "新建病历", onClick: () => navigate(`${dp("patients")}?action=new`) },
            { config: ICON_BADGES.qr_code, label: "预问诊码", onClick: () => navigate(dp("settings/qr")) },
            { config: ICON_BADGES.add_home, label: "加到桌面", onClick: () => setShowAddGuide(true) },
          ].map(({ config, label, onClick: onTap }, idx, arr) => (
            <Box key={label} onClick={onTap}
              sx={{
                display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.5, cursor: "pointer",
                borderRight: idx < arr.length - 1 ? `0.5px solid ${COLOR.borderLight}` : "none",
                "&:active": { bgcolor: COLOR.surface },
              }}>
              <IconBadge config={config} size={32} />
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2 }}>{label}</Typography>
            </Box>
          ))}
        </Box>

        {/* ── 5. Knowledge list ───────────────────────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 1.5 }}>
          <SectionLabel>我的知识（{knowledgeCount}）</SectionLabel>
          {knowledgeList.length > 0 && (
            <Typography onClick={() => navigate(dp("settings/knowledge"))}
              sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}>
              管理 ›
            </Typography>
          )}
        </Box>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {loading && knowledgeList.length === 0 && <SectionLoading />}
          {knowledgeList.length === 0 && !loading && (
            <EmptyState text="添加知识后，AI 会按你的方法工作" />
          )}
          {knowledgeList.slice(0, 3).map((rule, idx) => {
            const refs = rule.reference_count || 0;
            const status = refs > 0
              ? { label: `已引用${refs}次`, color: COLOR.primary }
              : { label: "待应用", color: COLOR.text4 };
            return (
              <KnowledgeCard
                key={rule.id || idx}
                title={rule.title || rule.text?.slice(0, 20) || "规则"}
                referenceCount={0}
                source={rule.source}
                date={rule.created_at ? formatRelativeDate(rule.created_at) : ""}
                status={status}
                onClick={() => navigate(`${dp("settings/knowledge")}/${rule.id}`)}
              />
            );
          })}
          {/* Inline add */}
          <Box onClick={() => navigate(dp("settings/knowledge/add"))}
            sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 0.5, py: 1.5,
              cursor: "pointer", color: COLOR.primary, fontSize: TYPE.secondary.fontSize, fontWeight: 500,
              borderTop: knowledgeList.length > 0 ? `0.5px solid ${COLOR.borderLight}` : "none",
              "&:active": { bgcolor: COLOR.surface } }}>
            <AddOutlinedIcon sx={{ fontSize: 16 }} />
            添加知识
          </Box>
        </Box>

        {/* Disclaimer footer */}
        <Box sx={{ py: 2, textAlign: "center" }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
            本服务为AI生成内容，结果仅供参考
          </Typography>
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
