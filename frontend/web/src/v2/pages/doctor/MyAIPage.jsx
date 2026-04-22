/**
 * @route /doctor/my-ai
 *
 * MyAIPage — "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 *
 * antd-mobile implementation — no MUI, no complex components.
 */
import { useState } from "react";
import { Avatar, List, Grid, Space, Tag, Skeleton, Ellipsis } from "antd-mobile";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import QrCodeScannerOutlinedIcon from "@mui/icons-material/QrCodeScannerOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import { useDoctorStore } from "../../../store/doctorStore";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import {
  useReviewQueue,
  usePersona,
  useTodaySummary,
  useKbPending,
  useKnowledgeItems,
  useFeedbackDigest,
} from "../../../lib/doctorQueries";
import { dp } from "../../../utils/doctorBasePath";
import { relativeTime } from "../../../utils/time";
import { APP, FONT, RADIUS, ICON } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";

// ── F3 digest helpers ─────────────────────────────────────────────────────

// Section id (server enum) → Chinese label for the breakdown bars and the
// small "flagged_kind" chip in the recent-feedback list. Kept as a local
// constant because these labels are UX copy, not domain truth.
const SECTION_LABELS = {
  differential: "诊断",
  workup: "检查",
  treatment: "治疗",
};

// Section display order for the breakdown rows. Mockup phone 3 leads with
// 检查 (usually the hottest section for flags), but we lock the order to
// match the server's _DIGEST_SECTIONS tuple so the card is stable regardless
// of who flagged what.
const SECTION_ORDER = ["differential", "workup", "treatment"];

const FLAGGED_RECENT_LIMIT = 10;

// ── Sub-components ────────────────────────────────────────────────────────────

function AIAvatar({ size = 44 }) {
  // antd-mobile `Avatar` only renders an `<img>` from `src`. Text avatars
  // have to ride in via the `fallback` prop, which renders when src is empty.
  return (
    <Avatar
      src=""
      fallback={
        <div
          style={{
            width: size,
            height: size,
            borderRadius: 8,
            backgroundColor: APP.primary,
            color: APP.surface,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: size * 0.45,
            fontWeight: 600,
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


// ── Main page ─────────────────────────────────────────────────────────────────

export default function MyAIPage({ doctorId }) {
  const navigate = useAppNavigate();
  const { doctorName } = useDoctorStore();

  // React Query-backed data fetching (shared cache — no redundant requests on tab switch)
  const { data: reviewQueueData, isLoading: qLoading } = useReviewQueue();
  const { data: personaData, isLoading: pLoading } = usePersona();
  const { data: summaryData, isLoading: sLoading, isError: sError } =
    useTodaySummary();
  const { data: kbPendingData } = useKbPending();
  const { data: knowledgeData } = useKnowledgeItems();
  const { data: digestData } = useFeedbackDigest(7);

  const loading = qLoading || pLoading;
  const reviewQueue = reviewQueueData || { pending: [], completed: [] };

  // Derived values — triage counts drive the main action block
  const displayName = doctorName || "医生";
  const pendingReview = loading ? 0 : (reviewQueue?.pending || []).length;
  const kbPendingCount = kbPendingData?.count || 0;
  const knowledgeListRaw = Array.isArray(knowledgeData)
    ? knowledgeData
    : knowledgeData?.items || [];
  const knowledgeCount = knowledgeListRaw.filter(
    (k) => k.category !== "persona"
  ).length;

  // Persona summary — single line for the bar
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
    // Extract first few keywords from markdown sections
    const items = summary
      .split(/[·\n###]/)
      .map((s) => s.trim())
      .filter((s) => s && s.length < 20);
    return items.slice(0, 4).join(" · ");
  })();

  return (
    <div style={pageContainer}>
      <div style={scrollable}>
      {/* ── 1. Identity + Quick tools — single Grid, two rows ── */}
      <Grid
        columns={3}
        gap={0}
        style={{
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
        }}
      >
        {/* Row 1 — identity header (spans 3 columns) */}
        <Grid.Item span={3}>
          <div
            style={{
              padding: "10px 16px",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              borderBottom: `0.5px solid ${APP.borderLight}`,
            }}
          >
            <AIAvatar size={52} />
            <div style={{ flex: 1, minWidth: 0, paddingRight: 8 }}>
              <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
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
                  marginTop: 2,
                  lineHeight: 1.4,
                  cursor: "pointer",
                }}
              >
                <Ellipsis
                  direction="end"
                  content={`AI风格：${personaSummary || "设置你的AI风格"}`}
                  rows={2}
                />
              </div>
            </div>
            <div
              onClick={() => navigate(dp("settings"))}
              style={{ padding: "8px", cursor: "pointer", borderRadius: RADIUS.md }}
            >
              <SettingsOutlinedIcon sx={{ fontSize: ICON.sm, color: APP.text3 }} />
            </div>
          </div>
        </Grid.Item>

        {/* Row 2 — 3 quick-tool tiles */}
        {[
          {
            label: "新建病历",
            icon: <EditNoteOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />,
            onClick: () => navigate(`${dp("patients")}?action=new`),
          },
          {
            label: "预问诊码",
            icon: <QrCodeScannerOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />,
            onClick: () => navigate(dp("settings/qr")),
          },
          {
            label: "知识库",
            icon: <MenuBookOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />,
            onClick: () => navigate(dp("settings/knowledge")),
          },
        ].map(({ label, icon, onClick: onTap }) => (
          <Grid.Item key={label} onClick={onTap}>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "2px",
                padding: "8px 0",
                cursor: "pointer",
              }}
            >
              {icon}
              <span style={{ fontSize: FONT.sm, color: APP.text2, whiteSpace: "nowrap" }}>
                {label}
              </span>
            </div>
          </Grid.Item>
        ))}
      </Grid>

      {/* ── 2a. Weekly AI performance digest (F3 feedback loop) ─────
          Shown between the identity Grid and today's triage block so the
          doctor sees their flag impact alongside their identity, not
          buried below the queue. Hidden when there's literally nothing
          to report (no suggestions ever shown) — new doctors see the
          activation card instead. */}
      {digestData && digestData.total_shown > 0 && (
        <>
          <div style={{ height: 8, backgroundColor: APP.surfaceAlt }} />
          <List header="本周 AI 表现">
            <List.Item>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  marginBottom: 10,
                }}
              >
                <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
                  你的 AI 表现
                </div>
                <div style={{ fontSize: FONT.xs, color: APP.text4 }}>近 7 天</div>
              </div>

              <div
                style={{
                  display: "flex",
                  gap: 20,
                  padding: "6px 0 10px",
                  borderBottom: `0.5px solid ${APP.borderLight}`,
                }}
              >
                {[
                  { num: digestData.total_shown, label: "AI 建议展示", warning: false },
                  { num: digestData.total_accepted, label: "你已采纳", warning: false },
                  { num: digestData.total_flagged, label: "你反馈不合理", warning: true },
                ].map(({ num, label, warning }) => (
                  <div key={label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span
                      style={{
                        fontSize: 24,
                        fontWeight: 600,
                        lineHeight: 1.1,
                        color: warning ? APP.warning : APP.text1,
                      }}
                    >
                      {num}
                    </span>
                    <span style={{ fontSize: FONT.xs, color: APP.text4 }}>{label}</span>
                  </div>
                ))}
              </div>

              {/* Breakdown — all 3 sections render even at zero when any
                  flag exists; pure-zero state short-circuits to placeholder */}
              {digestData.total_flagged === 0 ? (
                <div
                  style={{
                    padding: "12px 0 4px",
                    fontSize: FONT.sm,
                    color: APP.text4,
                    textAlign: "center",
                  }}
                >
                  本周暂无反馈
                </div>
              ) : (
                <div style={{ paddingTop: 10, display: "grid", gap: 8 }}>
                  {(() => {
                    const counts = SECTION_ORDER.map(
                      (s) => (digestData.by_section || {})[s] || 0
                    );
                    const maxCount = Math.max(1, ...counts);
                    return SECTION_ORDER.map((section, idx) => {
                      const count = counts[idx];
                      const pct = (count / maxCount) * 100;
                      return (
                        <div
                          key={section}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            fontSize: FONT.sm,
                            color: APP.text2,
                          }}
                        >
                          <span style={{ minWidth: 48 }}>{SECTION_LABELS[section]}</span>
                          <span
                            style={{
                              flex: 1,
                              height: 4,
                              backgroundColor: APP.borderLight,
                              borderRadius: 2,
                              margin: "0 10px",
                              overflow: "hidden",
                              position: "relative",
                            }}
                          >
                            <span
                              style={{
                                position: "absolute",
                                left: 0,
                                top: 0,
                                bottom: 0,
                                width: `${pct}%`,
                                backgroundColor: APP.warning,
                                borderRadius: 2,
                              }}
                            />
                          </span>
                          <span
                            style={{
                              color: APP.text4,
                              fontSize: FONT.xs,
                              minWidth: 44,
                              textAlign: "right",
                            }}
                          >
                            {count} / {digestData.total_flagged}
                          </span>
                        </div>
                      );
                    });
                  })()}
                </div>
              )}
            </List.Item>
          </List>

          {/* Recent-feedback list — only render when there's at least one
              flag. Shows up to FLAGGED_RECENT_LIMIT rows (server also caps). */}
          {digestData.recent && digestData.recent.length > 0 && (
            <List header="最近反馈">
              {digestData.recent.slice(0, FLAGGED_RECENT_LIMIT).map((r) => (
                <List.Item key={r.id}>
                  <div style={{ display: "grid", gap: 4 }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        fontSize: FONT.xs,
                        color: APP.text4,
                      }}
                    >
                      <span
                        style={{
                          padding: "1px 6px",
                          borderRadius: RADIUS.xs,
                          backgroundColor: APP.warningLight,
                          color: APP.warning,
                          fontWeight: 500,
                        }}
                      >
                        {SECTION_LABELS[r.section] || r.section}
                      </span>
                      <span>
                        {[r.patient_name, relativeTime(r.feedback_created_at)]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </div>
                    <div style={{ fontSize: FONT.sm, color: APP.text1, lineHeight: 1.5 }}>
                      <Ellipsis direction="end" content={r.content || ""} rows={1} />
                    </div>
                    {r.feedback_note && (
                      <div style={{ fontSize: FONT.xs, color: APP.text3 }}>
                        <Ellipsis direction="end" content={r.feedback_note} rows={1} />
                      </div>
                    )}
                  </div>
                </List.Item>
              ))}
            </List>
          )}
        </>
      )}

      {/* ── 2b. New-doctor guided activation OR triage block ─────── */}
      {knowledgeCount === 0 ? (
        <List header="开始使用">
          <List.Item>
            <div
              style={{
                padding: "12px 16px",
                textAlign: "center",
              }}
            >
            <div
              style={{
                fontSize: FONT.md,
                fontWeight: 600,
                color: APP.text1,
                marginBottom: "4px",
              }}
            >
              教 AI 第一条规则
            </div>
            <div
              style={{
                fontSize: FONT.sm,
                color: APP.text3,
                lineHeight: 1.6,
                marginBottom: "12px",
                maxWidth: "280px",
                marginLeft: "auto",
                marginRight: "auto",
              }}
            >
              两分钟就够了。AI 还没学到你的诊疗经验 — 从这里开始。
            </div>
            <button
              onClick={() => navigate(dp("settings/knowledge/add"))}
              style={{
                padding: "8px 14px",
                marginBottom: "12px",
                backgroundColor: APP.primary,
                color: APP.surface,
                border: "none",
                borderRadius: RADIUS.sm,
                fontSize: FONT.sm,
                fontWeight: 600,
                cursor: "pointer",
              }}
              onMouseDown={(e) => (e.target.opacity = "0.7")}
              onMouseUp={(e) => (e.target.opacity = "1")}
            >
              添加第一条规则
            </button>
            <div
              style={{
                textAlign: "left",
                maxWidth: "300px",
                marginLeft: "auto",
                marginRight: "auto",
                backgroundColor: APP.surfaceAlt,
                borderRadius: RADIUS.md,
                padding: "8px 10px",
              }}
            >
              <div
                style={{
                  fontSize: FONT.xs,
                  color: APP.text4,
                  fontWeight: 600,
                  letterSpacing: "0.4px",
                  marginBottom: "2px",
                }}
              >
                常见开端
              </div>
              <div
                style={{
                  fontSize: FONT.sm,
                  color: APP.text3,
                  lineHeight: 1.5,
                }}
              >
                · 术后用药禁忌<br />· 随访时间点<br />· 诊断判断要点
              </div>
            </div>
            </div>
          </List.Item>
        </List>
      ) : (
        <>
          <div style={{ height: 8, backgroundColor: APP.surfaceAlt }} />
          <List header="今日关注">
            <List.Item
              onClick={() => navigate(`${dp("review")}?tab=pending`)}
              arrow
              extra={pendingReview > 0 ? (
                <span style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.primary }}>{pendingReview}</span>
              ) : undefined}
              description={pendingReview > 0 ? `${pendingReview} 位患者待确认` : "暂无待审核建议"}
            >
              待审核诊断建议
            </List.Item>
            <List.Item
              onClick={() => navigate(`${dp("settings/knowledge")}?tab=pending`)}
              arrow
              extra={kbPendingCount > 0 ? (
                <span style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.primary }}>{kbPendingCount}</span>
              ) : undefined}
              description={kbPendingCount > 0 ? `从你的编辑中提取 ${kbPendingCount} 条` : "暂无新规则提议"}
            >
              待采纳的规则
            </List.Item>
          </List>
        </>
      )}

      {/* ── 3. Today Summary (LLM-generated, single narrative) ── */}
      {summaryData &&
        summaryData.mode !== "empty" &&
        summaryData.summary && (
          <>
            <div style={{ height: 8, backgroundColor: APP.surfaceAlt }} />
            <List
              header={
                <div style={{ display: "flex", alignItems: "center", width: "100%" }}>
                  <AutoAwesomeOutlinedIcon sx={{ fontSize: FONT.main, marginRight: "4px", color: APP.text3 }} />
                  <span>今日摘要</span>
                  {summaryData.is_new === false && (
                    <span style={{ fontSize: FONT.xs, color: APP.text4, marginLeft: "4px" }}>
                      · 较上次无新增
                    </span>
                  )}
                  {summaryData.generated_at && (
                    <span style={{ fontSize: FONT.xs, color: APP.text4, marginLeft: "auto" }}>
                      {new Date(summaryData.generated_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  )}
                </div>
              }
            >
              <List.Item>
                {/* Chips first — "who to act on" at a glance.
                    Chip routing: diagnosis review > chat view > knowledge.
                    Dedupe by (patient_id, kind). */}
                {summaryData.items?.length > 0 && (() => {
                  const seen = new Set();
                  const deduped = summaryData.items.filter((item) => {
                    const key = `${item.patient_id || ""}:${item.kind || ""}`;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                  });
                  const routeFor = (item) => {
                    if (item.record_id) return `${dp("review")}/${item.record_id}`;
                    if (
                      item.patient_id &&
                      item.kind === "message_knowledge_match"
                    ) {
                      return `${dp("patients")}/${item.patient_id}?view=chat`;
                    }
                    if (item.patient_id) return `${dp("patients")}/${item.patient_id}`;
                    if (item.kind === "knowledge_gap")
                      return dp("settings/knowledge/add");
                    return null;
                  };
                  return (
                    <div style={{ marginBottom: 8 }}>
                      <Space wrap>
                        {deduped.map((item, idx) => {
                          const href = routeFor(item);
                          const label = (
                            item.patient_name ||
                            item.title.replace(/\s*\[KB-\d+\]/g, "")
                          ).slice(0, 15);
                          return (
                            <Tag
                              key={item.id || idx}
                              color="primary"
                              fill="outline"
                              onClick={href ? () => navigate(href) : undefined}
                              style={{
                                "--background-color": APP.primaryLight,
                                "--border-color": APP.primaryLight,
                                "--text-color": APP.primary,
                                fontSize: FONT.sm,
                                cursor: href ? "pointer" : "default",
                              }}
                            >
                              {label}
                            </Tag>
                          );
                        })}
                      </Space>
                    </div>
                  );
                })()}
                {/* Narrative as supporting context */}
                {summaryData.summary.replace(/\s*\[KB-\d+\]/g, "")}
              </List.Item>
            </List>
          </>
        )}
      {sLoading && !sError && (
        <div style={{ padding: "8px 16px", marginTop: "8px" }}>
          <Skeleton.Paragraph lineCount={2} animated />
        </div>
      )}
      {summaryData && summaryData.mode === "empty" && summaryData.summary && (
        <div
          style={{
            padding: "8px 16px",
            marginTop: "8px",
            fontSize: FONT.sm,
            color: APP.text4,
            textAlign: "center",
          }}
        >
          {summaryData.summary}
        </div>
      )}

      </div>
    </div>
  );
}
