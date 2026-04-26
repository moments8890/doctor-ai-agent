/**
 * @route /doctor/my-ai
 *
 * MyAIPage — "我的AI" tab. Card-based dashboard: identity, AI summary hero,
 * quick actions, today's triage, and recently viewed items.
 */
import { useEffect, useState } from "react";
import { Avatar, Skeleton, Ellipsis, ActionSheet, CenterPopup } from "antd-mobile";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import PeopleAltOutlinedIcon from "@mui/icons-material/PeopleAltOutlined";
import QrCodeScannerOutlinedIcon from "@mui/icons-material/QrCodeScannerOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import AssignmentTurnedInOutlinedIcon from "@mui/icons-material/AssignmentTurnedInOutlined";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import PersonAddOutlinedIcon from "@mui/icons-material/PersonAddOutlined";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import EventOutlinedIcon from "@mui/icons-material/EventOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import PushPinIcon from "@mui/icons-material/PushPin";
import { useDoctorStore } from "../../../store/doctorStore";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { useLastViewed, reconcileLastViewed } from "../../../hooks/useLastViewed";
import {
  useReviewQueue,
  usePersona,
  useTodaySummary,
  useKbPending,
  useKnowledgeItems,
  usePatients,
  useUnseenPatientCount,
} from "../../../lib/doctorQueries";
import { dp } from "../../../utils/doctorBasePath";
import { formatAge } from "../../../utils/time";
import { APP, FONT, RADIUS, ICON, CATEGORY_COLOR } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";

// ── Sub-components ────────────────────────────────────────────────────────────

function AIAvatar({ size = 52 }) {
  return (
    <Avatar
      src=""
      fallback={
        <div
          style={{
            width: size,
            height: size,
            borderRadius: RADIUS.md,
            backgroundColor: APP.primary,
            color: APP.surface,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: size * 0.38,
            fontWeight: 600,
            letterSpacing: 0.5,
            lineHeight: 1,
          }}
        >
          AI
        </div>
      }
      style={{ "--size": `${size}px`, flexShrink: 0 }}
    />
  );
}

function Card({ children, style, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        backgroundColor: APP.surface,
        borderRadius: RADIUS.lg,
        margin: "0 16px 12px",
        overflow: "hidden",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function SectionHeader({ title, actionLabel, onAction }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        padding: "0 16px",
        marginBottom: 8,
      }}
    >
      <span style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
        {title}
      </span>
      {actionLabel && (
        <span
          onClick={onAction}
          style={{
            fontSize: FONT.sm,
            color: APP.text4,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
          }}
        >
          {actionLabel}
          <ChevronRightIcon sx={{ fontSize: ICON.xs, color: APP.text4 }} />
        </span>
      )}
    </div>
  );
}

// Tinted circular icon badge used in the triage and 最近使用 rows.
// `Icon` is a component reference (e.g. PersonOutlineIcon) and is rendered
// via JSX so React owns the render cycle — never call it as a plain function.
function TintedIcon({ Icon, bg, color, size = 40 }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: RADIUS.circle,
        backgroundColor: bg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <Icon sx={{ fontSize: ICON.md, color }} />
    </div>
  );
}

// Hero banner — green gradient card with the title + short AI summary.
// Tap anywhere on the card to open the full narrative in a bottom-sheet popup.
function HeroBanner({ title, summaryShort, summaryFull, loading, onClick }) {
  const hasDetail = !!(summaryFull && summaryFull.trim());
  return (
    <div
      onClick={hasDetail ? onClick : undefined}
      style={{
        margin: "0 16px 12px",
        borderRadius: RADIUS.lg,
        padding: "18px 18px 20px",
        background: `linear-gradient(135deg, ${APP.primaryLight} 0%, #d4f5e0 100%)`,
        position: "relative",
        overflow: "hidden",
        cursor: hasDetail ? "pointer" : "default",
      }}
    >
      <div style={{ position: "relative", zIndex: 1, paddingRight: 92 }}>
        <div
          style={{
            fontSize: FONT.lg,
            fontWeight: 600,
            color: APP.primary,
            marginBottom: 6,
            lineHeight: 1.3,
          }}
        >
          <Ellipsis direction="end" content={title} rows={1} />
        </div>
        {loading ? (
          <Skeleton.Paragraph lineCount={2} animated />
        ) : (
          <div
            style={{
              fontSize: FONT.sm,
              color: APP.text2,
              lineHeight: 1.55,
            }}
          >
            <Ellipsis direction="end" content={summaryShort} rows={2} />
          </div>
        )}
      </div>

      {/* Illustration cluster — clipboard + sparkles, anchored top-right */}
      <div
        style={{
          position: "absolute",
          top: 18,
          right: 14,
          width: 80,
          height: 80,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          opacity: 0.95,
        }}
      >
        <AutoAwesomeIcon
          sx={{
            position: "absolute",
            top: 4,
            right: 6,
            fontSize: 14, // lint-ui-ignore
            color: APP.primary,
            opacity: 0.7,
          }}
        />
        <AutoAwesomeIcon
          sx={{
            position: "absolute",
            bottom: 6,
            left: 2,
            fontSize: 10, // lint-ui-ignore
            color: APP.primary,
            opacity: 0.5,
          }}
        />
        <AssignmentTurnedInOutlinedIcon
          sx={{ fontSize: 56, color: APP.primary }} // lint-ui-ignore
        />
      </div>
    </div>
  );
}

// Centered modal — shows the full narrative summary when the banner is tapped.
function SummaryDetailSheet({ visible, onClose, summary, generatedAt }) {
  const timeStr = generatedAt
    ? new Date(generatedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
    : "";
  return (
    <CenterPopup
      visible={visible}
      onClose={onClose}
      showCloseButton
      closeOnMaskClick
      bodyStyle={{
        padding: "22px 22px 26px",
        maxHeight: "85vh",
        overflowY: "auto",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 14,
          paddingRight: 36,
        }}
      >
        <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
          今日摘要
        </div>
        {timeStr && (
          <div style={{ fontSize: FONT.xs, color: APP.text4, flexShrink: 0 }}>
            生成于 {timeStr}
          </div>
        )}
      </div>
      <div style={{ fontSize: FONT.base, color: APP.text2, lineHeight: 1.65 }}>
        {summary}
      </div>
    </CenterPopup>
  );
}

// Icon + label for a knowledge category in 最近使用.
function knowledgeIcon(category) {
  if (category === "medication") return MedicationOutlinedIcon;
  if (category === "followup") return EventOutlinedIcon;
  if (category === "diagnosis") return ArticleOutlinedIcon;
  return FolderOutlinedIcon;
}

// Absolute YYYY-MM-DD — matches the mockup's "就诊时间：2023-12-01" format.
function ymd(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// Single row of the 最近使用 card. Patients render as "name | 男 | 45岁"
// with 就诊时间 subtitle; knowledge renders as title + 更新于 subtitle.
function LastViewedRow({ item, isFirst, onClick, onPin, onRemove }) {
  const isKnowledge = item.type === "knowledge";
  const Icon = isKnowledge ? knowledgeIcon(item.category) : PersonOutlineIcon;
  const isPinned = !!item.pinnedAt;

  function handleMoreClick(e) {
    e.stopPropagation();
    const handler = ActionSheet.show({
      actions: [
        {
          key: "pin",
          text: isPinned ? "取消置顶" : "置顶",
          onClick: () => {
            onPin?.();
            handler.close();
          },
        },
        {
          key: "remove",
          text: "从最近使用中移除",
          danger: true,
          onClick: () => {
            onRemove?.();
            handler.close();
          },
        },
      ],
      cancelText: "取消",
      onClose: () => {},
    });
  }
  const iconBg = isKnowledge ? CATEGORY_COLOR.followup.bg : APP.accentLight;
  const iconColor = isKnowledge ? CATEGORY_COLOR.followup.fg : APP.accent;
  const tag = isKnowledge ? "知识库" : "病历";
  const tagBg = isKnowledge ? APP.primaryLight : APP.accentLight;
  const tagColor = isKnowledge ? APP.primary : APP.accent;

  let titleText;
  let subtitleText;
  if (isKnowledge) {
    titleText = item.title || "知识条目";
    subtitleText = `更新于 ${ymd(item.updatedAt) || ymd(item.viewedAt)}`;
  } else {
    const genderStr = item.gender
      ? { male: "男", female: "女" }[item.gender] || item.gender
      : null;
    titleText = [item.name || "患者", genderStr, formatAge(item.yearOfBirth)]
      .filter(Boolean)
      .join(" | ");
    subtitleText = `就诊时间：${ymd(item.lastVisitAt) || ymd(item.viewedAt)}`;
  }

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "14px 16px",
        cursor: "pointer",
        borderTop: isFirst ? "none" : `0.5px solid ${APP.borderLight}`,
      }}
    >
      <TintedIcon Icon={Icon} bg={iconBg} color={iconColor} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: FONT.md,
            fontWeight: 500,
            color: APP.text1,
          }}
        >
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              minWidth: 0,
            }}
          >
            {titleText}
          </span>
          <span
            style={{
              fontSize: FONT.xs,
              padding: "1px 6px",
              borderRadius: RADIUS.xs,
              backgroundColor: tagBg,
              color: tagColor,
              fontWeight: 500,
              flexShrink: 0,
            }}
          >
            {tag}
          </span>
          {isPinned && (
            <PushPinIcon
              aria-label="已置顶"
              sx={{
                fontSize: ICON.xs,
                color: APP.primary,
                transform: "rotate(30deg)",
                flexShrink: 0,
              }}
            />
          )}
        </div>
        <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
          {subtitleText}
        </div>
      </div>
      <div
        onClick={handleMoreClick}
        aria-label="更多"
        style={{
          padding: 6,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
        }}
      >
        <MoreHorizIcon sx={{ fontSize: ICON.sm, color: APP.text4 }} />
      </div>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function MyAIPage({ doctorId }) {
  const navigate = useAppNavigate();
  const { doctorName } = useDoctorStore();

  const { data: reviewQueueData, isLoading: qLoading } = useReviewQueue();
  const { data: unseenPatientData } = useUnseenPatientCount();
  const { data: personaData, isLoading: pLoading } = usePersona();
  const { data: summaryData, isLoading: sLoading } = useTodaySummary();
  const { data: kbPendingData } = useKbPending();
  const { data: knowledgeData } = useKnowledgeItems();
  const { data: patientsData } = usePatients();
  const { items: lastViewed, pin: pinLastViewed, remove: removeLastViewed } = useLastViewed(3);

  // Self-heal 最近使用: drop entries whose server row has been deleted since
  // the view was recorded. Pass ids only for types whose live data has loaded.
  useEffect(() => {
    const patientIds = Array.isArray(patientsData)
      ? patientsData.map((p) => p.id)
      : patientsData?.items?.map((p) => p.id);
    const knowledgeIds = Array.isArray(knowledgeData)
      ? knowledgeData.map((k) => k.id)
      : knowledgeData?.items?.map((k) => k.id);
    reconcileLastViewed({ patientIds, knowledgeIds });
  }, [patientsData, knowledgeData]);

  const reviewQueue = reviewQueueData || { pending: [], completed: [] };

  const displayName = doctorName || "医生";
  const pendingReview = qLoading ? 0 : (reviewQueue?.pending || []).length;
  const firstPendingReviewId = (reviewQueue?.pending || [])[0]?.record_id;
  const kbPendingCount = kbPendingData?.count || 0;
  const unseenPatientCount = unseenPatientData?.count || 0;
  const knowledgeList = Array.isArray(knowledgeData)
    ? knowledgeData
    : knowledgeData?.items || [];
  const knowledgeCount = knowledgeList.filter(
    (k) => k.category !== "persona"
  ).length;

  const personaSummary = (() => {
    if (pLoading) return null;
    const summary = personaData?.summary_text || "";
    if (!summary) {
      const rules = personaData
        ? Object.values(personaData.fields || {}).flat()
        : [];
      return rules.length > 0
        ? rules.slice(0, 3).map((r) => r.text).join(" · ")
        : "";
    }
    const items = summary
      .split(/[·\n###]/)
      .map((s) => s.trim())
      .filter((s) => s && s.length < 20);
    return items.slice(0, 4).join(" · ");
  })();

  const [summaryDetailOpen, setSummaryDetailOpen] = useState(false);

  // Hero summary — short preview on the banner; tap the banner to open the detail popup.
  // `<Ellipsis rows={2}>` below handles per-device overflow, so we never need to
  // char-slice here. Prefer LLM summary_short; fall back to full summary (Ellipsis
  // truncates with "…"); final fallback is the static tagline when no data at all.
  const heroSummaryFull = (summaryData?.summary || "").replace(/\s*\[KB-\d+\]/g, "").trim();
  const heroSummaryShort =
    (summaryData?.summary_short || "").replace(/\s*\[KB-\d+\]/g, "").trim() ||
    heroSummaryFull ||
    "基于您的知识库，提供专业的医疗决策支持";

  // 今日关注 rows — only rows with count>0 are rendered. Empty list = the
  // section disappears entirely (WeChat-unread style — absence communicates
  // "nothing to do").
  const triageRows = [
    {
      key: "review",
      label: "待审核诊断建议",
      description: `${pendingReview} 位患者待确认`,
      count: pendingReview,
      icon: PersonOutlineIcon,
      bg: APP.primaryLight,
      color: APP.primary,
      onClick: () => {
        if (firstPendingReviewId) {
          navigate(`${dp("review")}/${firstPendingReviewId}`);
        }
      },
    },
    {
      key: "rules",
      label: "待采纳的规则",
      description: `从你的编辑中提取 ${kbPendingCount} 条`,
      count: kbPendingCount,
      icon: ArticleOutlinedIcon,
      bg: CATEGORY_COLOR.custom.bg,
      color: CATEGORY_COLOR.custom.fg,
      onClick: () => navigate(`${dp("settings/knowledge")}?tab=pending`),
    },
    {
      key: "new_patients",
      label: "新患者",
      description: `${unseenPatientCount} 位刚刚加入`,
      count: unseenPatientCount,
      icon: PersonAddOutlinedIcon,
      bg: APP.accentLight || APP.primaryLight,
      color: APP.accent || APP.primary,
      onClick: () => navigate(dp("patients")),
    },
  ].filter((r) => r.count > 0);

  const quickActions = [
    {
      label: "全部患者",
      icon: <PeopleAltOutlinedIcon sx={{ fontSize: ICON.xl, color: APP.primary }} />,
      onClick: () => navigate(dp("patients")),
    },
    {
      label: "预问诊码",
      icon: <QrCodeScannerOutlinedIcon sx={{ fontSize: ICON.xl, color: APP.primary }} />,
      onClick: () => navigate(dp("settings/qr")),
    },
    {
      label: "知识库",
      icon: <MenuBookOutlinedIcon sx={{ fontSize: ICON.xl, color: APP.primary }} />,
      onClick: () => navigate(dp("settings/knowledge")),
    },
  ];

  return (
    <div style={pageContainer}>
      <div style={{ ...scrollable, paddingTop: 12, paddingBottom: 16 }}>
        {/* ── Identity card ────────────────────────────────────────── */}
        <Card>
          <div
            style={{
              padding: "14px 16px",
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <AIAvatar size={52} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: FONT.md,
                  fontWeight: 600,
                  color: APP.text1,
                  lineHeight: 1.3,
                }}
              >
                {displayName}的助手
              </div>
              <div
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(dp("settings/persona"));
                }}
                style={{
                  fontSize: FONT.sm,
                  color: APP.text4,
                  marginTop: 4,
                  display: "flex",
                  alignItems: "center",
                  cursor: "pointer",
                }}
              >
                <span style={{ minWidth: 0, flex: "0 1 auto" }}>
                  <Ellipsis
                    direction="end"
                    content={`AI风格：${personaSummary || "设置你的AI风格"}`}
                    rows={1}
                  />
                </span>
                <ChevronRightIcon sx={{ fontSize: ICON.xs, color: APP.text4, flexShrink: 0 }} />
              </div>
            </div>
            <div
              onClick={() => navigate(dp("settings"))}
              aria-label="设置"
              style={{
                padding: 8,
                cursor: "pointer",
                borderRadius: RADIUS.md,
                flexShrink: 0,
              }}
            >
              <SettingsOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text3 }} />
            </div>
          </div>
        </Card>

        {/* ── Hero banner (AI summary) ─────────────────────────────── */}
        <HeroBanner
          title="您的专属医疗AI助手"
          summaryShort={heroSummaryShort}
          summaryFull={heroSummaryFull}
          loading={sLoading && !summaryData}
          onClick={() => setSummaryDetailOpen(true)}
        />
        <SummaryDetailSheet
          visible={summaryDetailOpen}
          onClose={() => setSummaryDetailOpen(false)}
          summary={heroSummaryFull}
          generatedAt={summaryData?.generated_at}
        />

        {/* ── Quick actions card — 3 tiles with vertical dividers ─── */}
        <Card>
          <div style={{ display: "flex", padding: "14px 0" }}>
            {quickActions.map((action, idx) => (
              <div
                key={action.label}
                onClick={action.onClick}
                style={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 0",
                  cursor: "pointer",
                  borderRight:
                    idx < quickActions.length - 1
                      ? `0.5px solid ${APP.borderLight}`
                      : "none",
                }}
              >
                {action.icon}
                <span
                  style={{
                    fontSize: FONT.md,
                    fontWeight: 500,
                    color: APP.text1,
                    marginTop: 2,
                  }}
                >
                  {action.label}
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* ── 今日关注 OR new-doctor activation ─────────────────────── */}
        {/* When triageRows is empty (nothing pending across all 3 categories),
            the section is hidden entirely — absence communicates "nothing to do". */}
        {knowledgeCount === 0 ? (
          <ActivationCard onAdd={() => navigate(dp("settings/knowledge/add"))} />
        ) : triageRows.length === 0 ? null : (
          <>
            <SectionHeader title="今日关注" />
            <Card>
              {triageRows.map((row, idx) => (
                <div
                  key={row.key}
                  onClick={row.onClick}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "14px 16px",
                    cursor: "pointer",
                    borderTop:
                      idx > 0 ? `0.5px solid ${APP.borderLight}` : "none",
                  }}
                >
                  <TintedIcon
                    Icon={row.icon}
                    bg={row.bg}
                    color={row.color}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: FONT.md,
                        fontWeight: 500,
                        color: APP.text1,
                      }}
                    >
                      {row.label}
                    </div>
                    <div
                      style={{
                        fontSize: FONT.sm,
                        color: APP.text4,
                        marginTop: 2,
                      }}
                    >
                      {row.description}
                    </div>
                  </div>
                  {row.count > 0 && (
                    <span
                      style={{
                        fontSize: FONT.md,
                        fontWeight: 600,
                        color: APP.primary,
                      }}
                    >
                      {row.count}
                    </span>
                  )}
                  <ChevronRightIcon sx={{ fontSize: ICON.sm, color: APP.text4 }} />
                </div>
              ))}
            </Card>
          </>
        )}

        {/* ── 最近使用 — last-viewed knowledge + patients ──────────── */}
        {lastViewed.length > 0 && (
          <>
            <SectionHeader
              title="最近使用"
              actionLabel="查看更多"
              onAction={() => navigate(dp("patients"))}
            />
            <Card>
              {lastViewed.map((item, idx) => (
                <LastViewedRow
                  key={`${item.type}:${item.id}`}
                  item={item}
                  isFirst={idx === 0}
                  onClick={() =>
                    navigate(
                      item.type === "knowledge"
                        ? dp(`settings/knowledge/${item.id}`)
                        : dp(`patients/${item.id}`)
                    )
                  }
                  onPin={() => pinLastViewed(item.type, item.id)}
                  onRemove={() => removeLastViewed(item.type, item.id)}
                />
              ))}
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

// ── New-doctor activation — unchanged copy, card-styled ─────────────

function ActivationCard({ onAdd }) {
  return (
    <>
      <SectionHeader title="开始使用" />
      <Card>
        <div
          style={{
            padding: "20px 16px",
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: FONT.md,
              fontWeight: 600,
              color: APP.text1,
              marginBottom: 4,
            }}
          >
            教 AI 第一条规则
          </div>
          <div
            style={{
              fontSize: FONT.sm,
              color: APP.text3,
              lineHeight: 1.6,
              marginBottom: 16,
              maxWidth: 280,
              marginLeft: "auto",
              marginRight: "auto",
            }}
          >
            两分钟就够了。AI 还没学到你的诊疗经验 — 从这里开始。
          </div>
          <button
            onClick={onAdd}
            style={{
              padding: "8px 18px",
              marginBottom: 16,
              backgroundColor: APP.primary,
              color: APP.surface,
              border: "none",
              borderRadius: RADIUS.sm,
              fontSize: FONT.sm,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            添加第一条规则
          </button>
          <div
            style={{
              textAlign: "left",
              maxWidth: 300,
              marginLeft: "auto",
              marginRight: "auto",
              backgroundColor: APP.surfaceAlt,
              borderRadius: RADIUS.md,
              padding: "10px 12px",
            }}
          >
            <div
              style={{
                fontSize: FONT.xs,
                color: APP.text4,
                fontWeight: 600,
                letterSpacing: 0.4,
                marginBottom: 2,
              }}
            >
              常见开端
            </div>
            <div
              style={{
                fontSize: FONT.sm,
                color: APP.text3,
                lineHeight: 1.6,
              }}
            >
              · 术后用药禁忌<br />· 随访时间点<br />· 诊断判断要点
            </div>
          </div>
        </div>
      </Card>
    </>
  );
}
