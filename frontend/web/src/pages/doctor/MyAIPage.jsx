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
import AppButton from "../../components/AppButton";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import { ICON_BADGES } from "./constants";
import { TYPE, ICON, COLOR, RADIUS } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
import { useReviewQueue, usePersona, useTodaySummary, useKbPending, useKnowledgeItems } from "../../lib/doctorQueries";
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
  const { data: knowledgeData } = useKnowledgeItems();

  const loading = qLoading || pLoading;
  const reviewQueue = reviewQueueData || { pending: [], completed: [] };

  // Derived values — triage counts drive the main action block
  const displayName = doctorName || "医生";
  const pendingReview = loading ? 0 : (reviewQueue?.pending || []).length;
  const kbPendingCount = kbPendingData?.count || 0;
  const knowledgeListRaw = Array.isArray(knowledgeData) ? knowledgeData : (knowledgeData?.items || []);
  const knowledgeCount = knowledgeListRaw.filter((k) => k.category !== "persona").length;

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

        {/* ── 2a. Quick tools — home-screen-style grid (icon on top, label below) ── */}
        <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}`,
          display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 0 }}>
          {[
            { config: ICON_BADGES.new_record, label: "新建病历", onClick: () => navigate(`${dp("patients")}?action=new`) },
            { config: ICON_BADGES.qr_code, label: "预问诊码", onClick: () => navigate(dp("settings/qr")) },
            { config: ICON_BADGES.kb_doctor, label: "知识库", badge: knowledgeCount, onClick: () => navigate(dp("settings/knowledge")) },
          ].map(({ config, label, badge, onClick: onTap }) => (
            <Box key={label} onClick={onTap}
              sx={{
                display: "flex", flexDirection: "column", alignItems: "center",
                gap: 0.5, py: 1.5, cursor: "pointer",
                "&:active": { bgcolor: COLOR.surfaceAlt },
              }}>
              <Box sx={{ position: "relative" }}>
                <IconBadge config={config} size={40} />
                {badge > 0 && (
                  <Typography sx={{
                    position: "absolute", top: -4, right: -6,
                    minWidth: 16, height: 16, borderRadius: 8,
                    px: 0.5,
                    bgcolor: COLOR.danger, color: COLOR.white,
                    fontSize: TYPE.micro.fontSize, fontWeight: 600,
                    lineHeight: "16px", textAlign: "center",
                  }}>
                    {badge}
                  </Typography>
                )}
              </Box>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text2, whiteSpace: "nowrap" }}>{label}</Typography>
            </Box>
          ))}
        </Box>

        {/* ── 2b. New-doctor guided activation OR triage block ─────── */}
        {knowledgeCount === 0 ? (
          <>
            <SectionLabel>开始使用</SectionLabel>
            <Box sx={{
              bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`,
              px: 3, py: 4, textAlign: "center",
            }}>
              <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.text1, mb: 1 }}>
                教 AI 第一条规则
              </Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.7, mb: 2.5, maxWidth: 280, mx: "auto" }}>
                两分钟就够了。AI 还没学到你的诊疗经验 — 从这里开始。
              </Typography>
              <Box sx={{ display: "flex", justifyContent: "center", mb: 2.5 }}>
                <AppButton variant="primary" size="lg" onClick={() => navigate(dp("settings/knowledge/add"))}>
                  <MicNoneOutlinedIcon sx={{ fontSize: 18, mr: 0.75 }} />
                  添加第一条规则
                </AppButton>
              </Box>
              <Box sx={{ textAlign: "left", maxWidth: 300, mx: "auto",
                bgcolor: COLOR.surfaceAlt, borderRadius: RADIUS.md, p: 1.5 }}>
                <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, fontWeight: 600, letterSpacing: 0.4, mb: 0.5 }}>
                  常见开端
                </Typography>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.7 }}>
                  · 术后用药禁忌<br/>
                  · 随访时间点<br/>
                  · 诊断判断要点
                </Typography>
              </Box>
            </Box>
          </>
        ) : (
          <>
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
          </>
        )}

        {/* ── 3. Today Summary (LLM-generated, single narrative) ── */}
        {summaryData && summaryData.mode !== "empty" && summaryData.summary && (
          <>
            <Box sx={{ display: "flex", alignItems: "center", px: 1.5, pt: 2, pb: 0.5 }}>
              <AutoAwesomeOutlinedIcon sx={{ fontSize: 14, color: summaryData.is_new ? COLOR.primary : COLOR.text4, mr: 0.5 }} />
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, fontWeight: 600, letterSpacing: 0.5 }}>
                今日摘要
              </Typography>
              {summaryData.is_new === false && (
                <Typography component="span" sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, ml: 0.5 }}>
                  · 暂无新变化
                </Typography>
              )}
              {summaryData.generated_at && (
                <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, ml: "auto" }}>
                  {relativeTime(summaryData.generated_at)}
                </Typography>
              )}
            </Box>
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1.5 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.7 }}>
              {summaryData.summary.replace(/\s*\[KB-\d+\]/g, "")}
            </Typography>
            {/* Render item titles as tappable inline links below the paragraph.
                Chip routing preference: task > diagnosis review > chat view > knowledge.
                Dedupe by (patient_id, kind) so the same patient doesn't appear twice. */}
            {summaryData.items?.length > 0 && (() => {
              const seen = new Set();
              const deduped = summaryData.items.filter((item) => {
                const key = `${item.patient_id || ""}:${item.kind || ""}`;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
              });
              const routeFor = (item) => {
                if (item.task_id) return `${dp("tasks")}/${item.task_id}`;
                if (item.record_id) return `${dp("review")}/${item.record_id}`;
                if (item.patient_id && item.kind === "message_knowledge_match") {
                  return `${dp("patients")}/${item.patient_id}?view=chat`;
                }
                if (item.patient_id) return `${dp("patients")}/${item.patient_id}`;
                if (item.kind === "knowledge_gap") return dp("settings/knowledge/add");
                return null;
              };
              return (
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, mt: 1 }}>
                  {deduped.map((item, idx) => {
                    const href = routeFor(item);
                    return (
                      <Box key={item.id || idx}
                        onClick={href ? () => navigate(href) : undefined}
                        sx={{
                          fontSize: TYPE.caption.fontSize, color: COLOR.primary,
                          cursor: href ? "pointer" : "default",
                          px: 1, py: 0.25, borderRadius: RADIUS.sm, bgcolor: COLOR.primaryLight,
                          "&:active": href ? { opacity: 0.7 } : {},
                        }}>
                        {item.patient_name || item.title.replace(/\s*\[KB-\d+\]/g, "").slice(0, 15)}
                      </Box>
                    );
                  })}
                </Box>
              );
            })()}
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
