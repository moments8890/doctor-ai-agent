/**
 * @route /doctor/my-ai
 *
 * MyAIPage -- "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 */
import { Box, Typography } from "@mui/material";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import TipsAndUpdatesOutlinedIcon from "@mui/icons-material/TipsAndUpdatesOutlined";
import { useDoctorStore } from "../../store/doctorStore";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import PullToRefresh from "../../components/PullToRefresh";
import SectionLoading from "../../components/SectionLoading";
import ListCard from "../../components/ListCard";
import IconBadge from "../../components/IconBadge";
import SectionLabel from "../../components/SectionLabel";
import { ICON_BADGES } from "./constants";
import { TYPE, ICON, COLOR, RADIUS } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
import { useReviewQueue, usePersona, useTodaySummary, useKbPending } from "../../lib/doctorQueries";
import { relativeTime } from "../../utils/time";

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

function CountPill({ value, active }) {
  return (
    <Typography sx={{
      fontSize: TYPE.body.fontSize, fontWeight: 600,
      color: active ? COLOR.primary : COLOR.text4,
      minWidth: 20, textAlign: "right",
    }}>
      {value}
    </Typography>
  );
}


// ── Main page ─────────────────────────────────────────────────────────────────

export default function MyAIPage({ doctorId }) {
  const navigate = useAppNavigate();
  const { doctorName } = useDoctorStore();

  // React Query-backed data fetching (shared cache — no redundant requests on tab switch)
  const { data: reviewQueueData, isLoading: qLoading } = useReviewQueue();
  const { data: personaData, isLoading: pLoading } = usePersona();
  const { data: summaryData, isLoading: sLoading, isError: sError } = useTodaySummary();
  const { data: kbPendingData } = useKbPending();

  const loading = qLoading || pLoading;
  const reviewQueue = reviewQueueData || { pending: [], completed: [] };

  // Derived values — triage counts drive the main action block
  const displayName = doctorName || "医生";
  const pendingReview = loading ? 0 : (reviewQueue?.pending || []).length;
  const kbPendingCount = kbPendingData?.count || 0;

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

        {/* ── 2a. Quick tools (3-column grid with IconBadge) ──────── */}
        <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}`,
          display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 0 }}>
          {[
            { config: ICON_BADGES.new_record, label: "新建病历", onClick: () => navigate(`${dp("patients")}?action=new`) },
            { config: ICON_BADGES.qr_code, label: "预问诊码", onClick: () => navigate(dp("settings/qr")) },
            { config: ICON_BADGES.kb_add, label: "添加知识", onClick: () => navigate(dp("settings/knowledge/add")) },
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

        {/* ── 2b. Triage block — today's attention list ──────────── */}
        <SectionLabel>今日关注</SectionLabel>
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.review} size={36} />}
            title="待审核诊断建议"
            subtitle={pendingReview > 0 ? `${pendingReview} 位患者的 AI 诊断等你确认` : "暂无待审核建议"}
            right={<CountPill value={pendingReview ?? 0} active={pendingReview > 0} />}
            chevron
            onClick={() => navigate(`${dp("review")}?tab=pending`)}
          />
          <ListCard
            avatar={<IconBadge config={ICON_BADGES.kb_add} size={36} />}
            title="待采纳的规则"
            subtitle={kbPendingCount > 0 ? `AI 从你的编辑中提取了 ${kbPendingCount} 条新规则` : "暂无新规则提议"}
            right={<CountPill value={kbPendingCount} active={kbPendingCount > 0} />}
            chevron
            onClick={() => navigate(dp("settings/knowledge/pending"))}
            sx={{ borderBottom: "none" }}
          />
        </Box>

        {/* ── 3. Today Summary (LLM-generated, single narrative) ── */}
        {summaryData && summaryData.mode !== "empty" && summaryData.summary && (
          <>
            <SectionLabel sx={{
              display: "flex", alignItems: "center", gap: 0.5,
            }}>
              <AutoAwesomeOutlinedIcon sx={{ fontSize: 14, color: summaryData.is_new ? COLOR.primary : COLOR.text4, verticalAlign: "middle", mr: 0.5 }} />
              今日摘要
              {summaryData.is_new === false && (
                <Typography component="span" sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, ml: 0.5, fontWeight: 400 }}>
                  · 暂无新变化
                </Typography>
              )}
              {summaryData.generated_at && (
                <Typography component="span" sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, ml: "auto", fontWeight: 400 }}>
                  {relativeTime(summaryData.generated_at)}
                </Typography>
              )}
            </SectionLabel>
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1.5 }}>
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
          </>
        )}
        {sLoading && !sError && (
          <Box sx={{ px: 2, py: 1.5 }}>
            <SectionLoading rows={1} />
          </Box>
        )}
        {summaryData && summaryData.mode === "empty" && summaryData.summary && (
          <Box sx={{ px: 2, py: 1.5 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, textAlign: "center" }}>
              {summaryData.summary}
            </Typography>
          </Box>
        )}

        {/* Disclaimer footer */}
        <Box sx={{ py: 2, textAlign: "center" }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
            本服务为AI生成内容，结果仅供参考
          </Typography>
        </Box>

      </PullToRefresh>
    </Box>
  );
}
