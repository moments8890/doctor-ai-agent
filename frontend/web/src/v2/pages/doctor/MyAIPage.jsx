/**
 * @route /doctor/my-ai
 *
 * MyAIPage — "我的AI" tab. AI identity dashboard showing the doctor's AI
 * status, knowledge rules, quick actions, and recent AI activity.
 *
 * antd-mobile implementation — no MUI, no complex components.
 */
import { useState } from "react";
import { List, Card, Popup } from "antd-mobile";
import { SetOutline, ContentOutline, CheckCircleFill, StarOutline, FileOutline, ScanningOutline } from "antd-mobile-icons";
import { useDoctorStore } from "../../../store/doctorStore";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import {
  useReviewQueue,
  usePersona,
  useTodaySummary,
  useKbPending,
  useKnowledgeItems,
} from "../../../lib/doctorQueries";
import { dp } from "../../../utils/doctorBasePath";
import { APP, FONT, RADIUS } from "../../theme";

// ── Sub-components ────────────────────────────────────────────────────────────

function AIAvatar({ size = 44 }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "8px",
        flexShrink: 0,
        backgroundColor: APP.accent,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: APP.surface,
        fontSize: size * 0.45,
        fontWeight: 600,
        lineHeight: 1,
      }}
    >
      AI
    </div>
  );
}

function CountPill({ value, active }) {
  return (
    <span
      style={{
        fontSize: FONT.main,
        fontWeight: 600,
        color: active ? APP.primary : APP.text4,
        minWidth: 20,
        textAlign: "right",
      }}
    >
      {value}
    </span>
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
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: APP.surfaceAlt,
        overflow: "auto",
      }}
    >
      {/* ── 1. Identity header ─────────────────────────────────── */}
      <div
        style={{
          backgroundColor: APP.surface,
          padding: "16px",
          display: "flex",
          alignItems: "center",
          gap: "12px",
          borderBottom: `0.5px solid ${APP.borderLight}`,
        }}
      >
        <AIAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: FONT.lg,
              fontWeight: 600,
              color: APP.text1,
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
              marginTop: "2px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              cursor: "pointer",
            }}
            onMouseDown={(e) => (e.target.style.opacity = "0.7")}
            onMouseUp={(e) => (e.target.style.opacity = "1")}
          >
            AI风格：{personaSummary || "设置你的AI风格"}
          </div>
        </div>
        <div
          onClick={() => navigate(dp("settings"))}
          style={{
            padding: "8px",
            cursor: "pointer",
            borderRadius: RADIUS.md,
          }}
          onMouseDown={(e) => (e.target.style.backgroundColor = APP.surfaceAlt)}
          onMouseUp={(e) => (e.target.style.backgroundColor = "transparent")}
        >
          <SetOutline style={{ fontSize: 20, color: APP.text3 }} />
        </div>
      </div>

      {/* ── 2a. Quick tools — grid (icon on top, label below) ── */}
      <div
        style={{
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 0,
        }}
      >
        {[
          {
            label: "新建病历",
            icon: <ContentOutline style={{ fontSize: 32, color: APP.text2 }} />,
            badge: 0,
            onClick: () => navigate(`${dp("patients")}?action=new`),
          },
          {
            label: "预问诊码",
            icon: <ScanningOutline style={{ fontSize: 32, color: APP.text2 }} />,
            badge: 0,
            onClick: () => navigate(dp("settings/qr")),
          },
          {
            label: "知识库",
            icon: <FileOutline style={{ fontSize: 32, color: APP.text2 }} />,
            badge: knowledgeCount,
            onClick: () => navigate(dp("settings/knowledge")),
          },
        ].map(({ label, icon, badge, onClick: onTap }) => (
          <div
            key={label}
            onClick={onTap}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "4px",
              padding: "12px 0",
              cursor: "pointer",
              position: "relative",
            }}
            onMouseDown={(e) => (e.currentTarget.style.backgroundColor = APP.surfaceAlt)}
            onMouseUp={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
          >
            <div style={{ position: "relative" }}>
              <div style={{ fontSize: 32 }}>{icon}</div>
              {badge > 0 && (
                <span
                  style={{
                    position: "absolute",
                    top: "-4px",
                    right: "-10px",
                    minWidth: "18px",
                    height: "16px",
                    borderRadius: "8px",
                    paddingLeft: "4px",
                    paddingRight: "4px",
                    backgroundColor: APP.surface,
                    color: APP.text3,
                    border: `0.5px solid ${APP.borderLight}`,
                    fontSize: FONT.xs,
                    fontWeight: 500,
                    lineHeight: "15px",
                    textAlign: "center",
                  }}
                >
                  {badge}
                </span>
              )}
            </div>
            <span
              style={{
                fontSize: FONT.sm,
                color: APP.text2,
                whiteSpace: "nowrap",
              }}
            >
              {label}
            </span>
          </div>
        ))}
      </div>

      {/* ── 2b. New-doctor guided activation OR triage block ─────── */}
      {knowledgeCount === 0 ? (
        <>
          <div
            style={{
              fontSize: FONT.sm,
              fontWeight: 600,
              color: APP.text3,
              padding: "12px 16px 4px",
              marginTop: "12px",
              letterSpacing: "0.4px",
            }}
          >
            开始使用
          </div>
          <div
            style={{
              backgroundColor: APP.surface,
              borderTop: `0.5px solid ${APP.border}`,
              borderBottom: `0.5px solid ${APP.border}`,
              padding: "32px 24px",
              textAlign: "center",
            }}
          >
            <div
              style={{
                fontSize: FONT.lg,
                fontWeight: 600,
                color: APP.text1,
                marginBottom: "8px",
              }}
            >
              教 AI 第一条规则
            </div>
            <div
              style={{
                fontSize: FONT.sm,
                color: APP.text3,
                lineHeight: 1.7,
                marginBottom: "20px",
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
                padding: "10px 16px",
                marginBottom: "20px",
                backgroundColor: APP.primary,
                color: APP.surface,
                border: "none",
                borderRadius: RADIUS.sm,
                fontSize: FONT.md,
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
                padding: "12px",
              }}
            >
              <div
                style={{
                  fontSize: FONT.xs,
                  color: APP.text4,
                  fontWeight: 600,
                  letterSpacing: "0.4px",
                  marginBottom: "4px",
                }}
              >
                常见开端
              </div>
              <div
                style={{
                  fontSize: FONT.sm,
                  color: APP.text3,
                  lineHeight: 1.7,
                }}
              >
                · 术后用药禁忌<br />· 随访时间点<br />· 诊断判断要点
              </div>
            </div>
          </div>
        </>
      ) : (
        <>
          <div
            style={{
              fontSize: FONT.sm,
              fontWeight: 600,
              color: APP.text3,
              padding: "12px 16px 4px",
              marginTop: "12px",
              letterSpacing: "0.4px",
            }}
          >
            今日关注
          </div>
          <List style={{ backgroundColor: APP.surface }}>
            <List.Item
              onClick={() => navigate(`${dp("review")}?tab=pending`)}
              style={{
                borderBottom: `0.5px solid ${APP.border}`,
                padding: "12px 16px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  width: "100%",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: FONT.md, fontWeight: 500, color: APP.text1 }}>
                    待审核诊断建议
                  </div>
                  <div
                    style={{
                      fontSize: FONT.sm,
                      color: APP.text3,
                      marginTop: "2px",
                    }}
                  >
                    {pendingReview > 0
                      ? `${pendingReview} 位患者的 AI 诊断等你确认`
                      : "暂无待审核建议"}
                  </div>
                </div>
                <CountPill value={pendingReview ?? 0} active={pendingReview > 0} />
              </div>
            </List.Item>
            <List.Item
              onClick={() => navigate(dp("settings/knowledge/pending"))}
              style={{
                borderBottom: "none",
                padding: "12px 16px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  width: "100%",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: FONT.md, fontWeight: 500, color: APP.text1 }}>
                    待采纳的规则
                  </div>
                  <div
                    style={{
                      fontSize: FONT.sm,
                      color: APP.text3,
                      marginTop: "2px",
                    }}
                  >
                    {kbPendingCount > 0
                      ? `AI 从你的编辑中提取了 ${kbPendingCount} 条新规则`
                      : "暂无新规则提议"}
                  </div>
                </div>
                <CountPill value={kbPendingCount} active={kbPendingCount > 0} />
              </div>
            </List.Item>
          </List>
        </>
      )}

      {/* ── 3. Today Summary (LLM-generated, single narrative) ── */}
      {summaryData &&
        summaryData.mode !== "empty" &&
        summaryData.summary && (
          <>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                padding: "12px 12px 4px",
                marginTop: "12px",
              }}
            >
              <StarOutline style={{ fontSize: FONT.main, marginRight: "4px", color: APP.text3 }} />
              <span
                style={{
                  fontSize: FONT.sm,
                  color: APP.text3,
                  fontWeight: 600,
                  letterSpacing: "0.5px",
                }}
              >
                今日摘要
              </span>
              {summaryData.is_new === false && (
                <span
                  style={{
                    fontSize: FONT.xs,
                    color: APP.text4,
                    marginLeft: "4px",
                  }}
                >
                  · 暂无新变化
                </span>
              )}
              {summaryData.generated_at && (
                <span
                  style={{
                    fontSize: FONT.xs,
                    color: APP.text4,
                    marginLeft: "auto",
                  }}
                >
                  {new Date(summaryData.generated_at).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              )}
            </div>
            <Card style={{ margin: "8px 0", backgroundColor: APP.surface }}>
              <div style={{ padding: "12px", color: APP.text2, lineHeight: 1.7 }}>
                {summaryData.summary.replace(/\s*\[KB-\d+\]/g, "")}
              </div>
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
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                      marginTop: "8px",
                      padding: "0 12px 12px",
                    }}
                  >
                    {deduped.map((item, idx) => {
                      const href = routeFor(item);
                      return (
                        <div
                          key={item.id || idx}
                          onClick={href ? () => navigate(href) : undefined}
                          style={{
                            fontSize: FONT.sm,
                            color: APP.primary,
                            cursor: href ? "pointer" : "default",
                            paddingLeft: "8px",
                            paddingRight: "8px",
                            paddingTop: "2px",
                            paddingBottom: "2px",
                            borderRadius: RADIUS.sm,
                            backgroundColor: APP.primaryLight,
                          }}
                          onMouseDown={(e) =>
                            href && (e.target.opacity = "0.7")
                          }
                          onMouseUp={(e) =>
                            href && (e.target.opacity = "1")
                          }
                        >
                          {(item.patient_name ||
                            item.title.replace(/\s*\[KB-\d+\]/g, "")).slice(
                            0,
                            15
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </Card>
          </>
        )}
      {sLoading && !sError && (
        <div style={{ padding: "12px 16px", marginTop: "12px" }}>
          <div
            style={{
              height: "20px",
              backgroundColor: APP.borderLight,
              borderRadius: RADIUS.xs,
              animation: "pulse 2s infinite",
            }}
          />
        </div>
      )}
      {summaryData && summaryData.mode === "empty" && summaryData.summary && (
        <div
          style={{
            padding: "12px 16px",
            marginTop: "12px",
            fontSize: FONT.sm,
            color: APP.text4,
            textAlign: "center",
          }}
        >
          {summaryData.summary}
        </div>
      )}

      {/* Disclaimer footer */}
      <div style={{ padding: "16px", textAlign: "center", marginTop: "auto" }}>
        <span style={{ fontSize: FONT.xs, color: APP.text4 }}>
          本服务为AI生成内容，结果仅供参考
        </span>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
