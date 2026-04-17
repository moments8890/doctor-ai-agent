/**
 * @route /doctor/my-ai
 *
 * MyAIPage -- "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 */
import { Box, Typography } from "@mui/material";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import AddOutlinedIcon from "@mui/icons-material/AddOutlined";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import TipsAndUpdatesOutlinedIcon from "@mui/icons-material/TipsAndUpdatesOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import { useDoctorStore } from "../../store/doctorStore";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import PullToRefresh from "../../components/PullToRefresh";
import SectionLoading from "../../components/SectionLoading";
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

function QuickChip({ icon, label, primary, onClick }) {
  return (
    <Box
      onClick={onClick}
      sx={{
        flexShrink: 0,
        display: "flex", alignItems: "center", gap: 0.5,
        px: 1.5, py: 0.75, borderRadius: 16,
        bgcolor: primary ? COLOR.primary : "#f1f8f3",
        color: primary ? COLOR.white : "#0d5c2e",
        border: primary ? `1px solid ${COLOR.primary}` : "1px solid #d7ecdb",
        fontSize: TYPE.caption.fontSize, fontWeight: 500,
        cursor: "pointer",
        "&:active": { opacity: 0.7 },
      }}
    >
      {icon}
      <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, fontWeight: 500, color: "inherit" }}>
        {label}
      </Typography>
    </Box>
  );
}

function TriageRow({ icon, iconBg, iconColor, title, sub, count, onClick }) {
  const active = count > 0;
  return (
    <Box
      onClick={onClick}
      sx={{
        display: "flex", alignItems: "center", gap: 1.25,
        px: 2, py: 1.25,
        borderTop: `0.5px solid ${COLOR.borderLight}`,
        cursor: "pointer",
        "&:active": { bgcolor: COLOR.surfaceAlt },
      }}
    >
      <Box sx={{
        width: 32, height: 32, borderRadius: RADIUS.md, flexShrink: 0,
        bgcolor: iconBg, color: iconColor,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500, color: COLOR.text1 }}>{title}</Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.25 }}>{sub}</Typography>
      </Box>
      <Box sx={{
        fontSize: TYPE.heading.fontSize, fontWeight: 600,
        color: active ? iconColor : COLOR.text4,
        bgcolor: active ? iconBg : "transparent",
        borderRadius: 12, px: 1.25, py: 0.25, minWidth: 28, textAlign: "center",
      }}>
        {count}
      </Box>
      <ChevronRightOutlinedIcon sx={{ color: COLOR.text4, fontSize: 18 }} />
    </Box>
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

        {/* ── 2a. Quick-action chips ──────────────────────────────── */}
        <Box sx={{
          display: "flex", gap: 1, px: 2, py: 1,
          bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.borderLight}`,
          overflowX: "auto",
        }}>
          <QuickChip
            icon={<AddOutlinedIcon sx={{ fontSize: 14 }} />}
            label="新建病历" primary
            onClick={() => navigate(`${dp("patients")}?action=new`)}
          />
          <QuickChip
            icon={<QrCode2OutlinedIcon sx={{ fontSize: 14 }} />}
            label="预问诊码"
            onClick={() => navigate(dp("settings/qr"))}
          />
          {isMiniprogram && (
            <QuickChip
              icon={<MicNoneOutlinedIcon sx={{ fontSize: 14 }} />}
              label="语音记规则"
              onClick={() => navigate(dp("settings/knowledge/add"))}
            />
          )}
        </Box>

        {/* ── 2b. Triage block — primary action list ──────────────── */}
        <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <Typography sx={{
            px: 2, pt: 1.25, pb: 0.5,
            fontSize: TYPE.micro.fontSize, fontWeight: 700, color: COLOR.primary,
            letterSpacing: 0.5, textTransform: "uppercase",
          }}>
            现在请你确认
          </Typography>
          <TriageRow
            icon={<AssignmentOutlinedIcon sx={{ fontSize: 18 }} />}
            iconBg="#fff3e0" iconColor="#e65100"
            title="待审核诊断建议"
            sub={pendingReview > 0 ? `${pendingReview} 位患者的 AI 诊断等你确认` : "暂无待审核建议"}
            count={pendingReview ?? 0}
            onClick={() => navigate(`${dp("review")}?tab=pending`)}
          />
          <TriageRow
            icon={<TipsAndUpdatesOutlinedIcon sx={{ fontSize: 18 }} />}
            iconBg="#e8f5e9" iconColor="#0d5c2e"
            title="待采纳的规则"
            sub={kbPendingCount > 0 ? `AI 从你的编辑中提取了 ${kbPendingCount} 条新规则` : "暂无新规则提议"}
            count={kbPendingCount}
            onClick={() => navigate(dp("settings/knowledge/pending"))}
          />
        </Box>

        {/* ── 3. Today Summary (LLM-generated, single narrative) ── */}
        {summaryData && summaryData.mode !== "empty" && summaryData.summary && (
          <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1.5 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.75 }}>
              <AutoAwesomeOutlinedIcon sx={{ fontSize: 14, color: summaryData.is_new ? COLOR.primary : COLOR.text4 }} />
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: summaryData.is_new ? COLOR.primary : COLOR.text4, fontWeight: 600 }}>
                今日摘要
              </Typography>
              {summaryData.is_new === false && (
                <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, ml: 0.5 }}>
                  暂无新变化
                </Typography>
              )}
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, ml: "auto" }}>
                {summaryData.generated_at ? relativeTime(summaryData.generated_at) : ""}
              </Typography>
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
