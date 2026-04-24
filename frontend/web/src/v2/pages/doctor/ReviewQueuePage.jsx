/**
 * @route /doctor/review
 *
 * v2 ReviewQueuePage — antd-mobile rewrite.
 * Shows pending diagnosis reviews, pending reply drafts, and completed items.
 */
import { useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  JumboTabs,
  List,
  ErrorBlock,
  PullToRefresh,
  Ellipsis,
} from "antd-mobile";
import { useReviewQueue, useDrafts } from "../../../lib/doctorQueries";
import { useDoctorStore } from "../../../store/doctorStore";
import { dp } from "../../../utils/doctorBasePath";
import { APP, FONT, RADIUS } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";
import { NameAvatar, LoadingCenter } from "../../components";

// Tab title with an inline (N) count shown when count > 0.
function TabTitleWithCount({ label, count }) {
  if (count > 0) {
    return <span>{label} ({count})</span>;
  }
  return <span>{label}</span>;
}

const SECTION_LABEL = {
  differential: "鉴别诊断",
  workup: "检查建议",
  treatment: "治疗方向",
};

// Small chip to distinguish diagnose vs reply rows in the unified queue.
// When a group has multiple pending items collapsed into one row,
// the count is shown inline inside the chip (e.g. "诊断 ×3").
function KindTag({ kind, count = 1 }) {
  const isReview = kind === "review";
  const label = isReview ? "诊断" : "回复";
  return (
    <span
      style={{
        display: "inline-block",
        marginRight: 6,
        padding: "1px 6px",
        borderRadius: RADIUS.xs,
        fontSize: FONT.xs,
        fontWeight: 500,
        lineHeight: 1.5,
        background: isReview ? APP.primaryLight : APP.accentLight,
        color: isReview ? APP.primary : APP.accent,
      }}
    >
      {count > 1 ? `${label} ×${count}` : label}
    </span>
  );
}

// Format ISO timestamp → "N 天前" / "刚刚" / "N 小时前" for the extra slot.
function formatRelative(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return d.toLocaleDateString("zh-CN");
}

// ── Pending item row (AI diagnosis review) ────────────────────────

function PendingItem({ item, onNavigate }) {
  const sectionLabel = SECTION_LABEL[item.section] || item.section || "";
  const sourceLabel =
    item.record_type === "interview_summary"
      ? "预问诊"
      : item.record_type === "import"
      ? "导入"
      : "门诊记录";
  const subtitle = item.chief_complaint
    ? `主诉：${item.chief_complaint}`
    : [sourceLabel, sectionLabel && item.content ? `${sectionLabel}：${item.content}` : ""]
        .filter(Boolean)
        .join(" · ");
  const time = item.time || formatRelative(item.created_at);

  return (
    <List.Item
      prefix={<NameAvatar name={item.patient_name} size={36} />}
      extra={<span style={{ fontSize: FONT.sm, color: APP.text4 }}>{time}</span>}
      description={<Ellipsis direction="end" content={subtitle} rows={1} />}
      arrow
      onClick={() => onNavigate(item)}
      style={{ "--align-items": "center" }}
    >
      <div style={{ display: "flex", alignItems: "center" }}>
        <KindTag kind="review" count={item._group_count || 1} />
        <span style={{ fontWeight: 500, fontSize: FONT.md }}>
          {item.patient_name}
        </span>
      </div>
    </List.Item>
  );
}

// ── Reply draft row ────────────────────────────────────────────────

function DraftItem({ item, onNavigate }) {
  const statusLabel = item.type === "undrafted" ? "需手动回复" : "AI已起草";
  const snippet = item.patient_message || item.content || "";
  const subtitle = snippet ? `"${snippet}" · ${statusLabel}` : statusLabel;
  const time = item.time || formatRelative(item.created_at);

  return (
    <List.Item
      prefix={<NameAvatar name={item.patient_name} size={36} />}
      extra={<span style={{ fontSize: FONT.sm, color: APP.text4 }}>{time}</span>}
      description={<Ellipsis direction="end" content={subtitle} rows={1} />}
      arrow
      onClick={() => onNavigate(item)}
      style={{ "--align-items": "center" }}
    >
      <div style={{ display: "flex", alignItems: "center" }}>
        <KindTag kind="reply" count={item._group_count || 1} />
        <span style={{ fontWeight: 500, fontSize: FONT.md }}>
          {item.patient_name}
        </span>
      </div>
    </List.Item>
  );
}

// ── Completed row ──────────────────────────────────────────────────

function CompletedItem({ item, onNavigate }) {
  const isEdited = item.decision === "edited";
  const detail = isEdited && item.detail
    ? `已修改 · ${item.detail}`
    : item.rule_count > 0
    ? `已确认 · 引用了你的 ${item.rule_count} 条规则`
    : "已确认";

  return (
    <List.Item
      prefix={<NameAvatar name={item.patient_name} size={36} />}
      extra={
        <span style={{ fontSize: FONT.sm, color: APP.text4 }}>{item.time}</span>
      }
      description={detail}
      arrow
      onClick={() => onNavigate(item)}
      style={{ opacity: 0.65 }}
    >
      <span style={{ fontWeight: 500 }}>
        {item.patient_name} · {item.content}
      </span>
    </List.Item>
  );
}

// ── Main ───────────────────────────────────────────────────────────

export default function ReviewQueuePage() {
  const navigate = useNavigate();
  const { doctorId } = useDoctorStore();

  const { data: queueData, isLoading: qLoading, refetch: refetchQueue } = useReviewQueue();
  const { data: draftsData, isLoading: dLoading, refetch: refetchDrafts } = useDrafts({ includeSent: true });

  const loading = qLoading || dLoading;
  const queue = queueData || { pending: [], completed: [] };
  const drafts = Array.isArray(draftsData)
    ? draftsData
    : draftsData?.pending_messages || [];

  const pending = queue.pending || [];
  const reviewCompleted = queue.completed || [];
  const activeDrafts = drafts.filter((d) => d.status !== "sent");
  const sentDrafts = drafts.filter((d) => d.status === "sent").map((d) => ({
    id: `draft_${d.id}`,
    type: "reply",
    patient_name: d.patient_name,
    patient_id: d.patient_id,
    content: d.patient_message ? d.patient_message.slice(0, 40) : "已回复",
    created_at: d.created_at,
    time: d.time,
  }));
  const completed = [...reviewCompleted, ...sentDrafts].sort((a, b) =>
    (b.created_at || "").localeCompare(a.created_at || "")
  );

  // Tab state from URL: ?tab=pending (default) | ?tab=completed
  // `replies` legacy value is remapped to `pending` since they share the tab.
  const [searchParams, setSearchParams] = useSearchParams();
  const validTabs = new Set(["pending", "completed"]);
  const urlTab = searchParams.get("tab");
  const activeTab =
    urlTab === "replies"
      ? "pending"
      : urlTab && validTabs.has(urlTab)
      ? urlTab
      : "pending";

  function handleTabChange(key) {
    if (key === "pending") {
      setSearchParams({}, { replace: true });
    } else {
      setSearchParams({ tab: key }, { replace: true });
    }
  }

  // Unified pending list — AI diagnosis reviews + patient reply drafts.
  // Sorted newest-first so the dedup step below naturally keeps the latest.
  const pendingUnified = [
    ...pending.map((p) => ({ ...p, _kind: "review" })),
    ...activeDrafts.map((d) => ({ ...d, _kind: "reply" })),
  ].sort((a, b) =>
    (b.created_at || "").localeCompare(a.created_at || "")
  );

  // Dedup: one row per (patient_id, _kind) pair, keeping the latest item
  // and attaching the group size so the chip can show "诊断 ×N".
  const pendingDedup = (() => {
    const groups = new Map();
    for (const item of pendingUnified) {
      const key = `${item.patient_id}:${item._kind}`;
      const existing = groups.get(key);
      if (existing) {
        existing.count += 1;
      } else {
        groups.set(key, { latest: item, count: 1 });
      }
    }
    return Array.from(groups.values()).map((g) => ({
      ...g.latest,
      _group_count: g.count,
    }));
  })();

  function handleNavigateUnified(item) {
    if (item._kind === "reply") {
      handleNavigateDraft(item);
    } else {
      handleNavigatePending(item);
    }
  }

  function handleNavigatePending(item) {
    navigate(`${dp("review")}/${item.record_id}`);
  }

  function handleNavigateDraft(item) {
    navigate(`${dp("patients")}/${item.patient_id}?view=chat`);
  }

  function handleNavigateCompleted(item) {
    if (item.type === "reply" && item.patient_id) {
      navigate(`${dp("patients")}/${item.patient_id}?view=chat`);
    } else if (item.patient_id) {
      const qs = item.record_id ? `?view=record&record=${item.record_id}` : "";
      navigate(`${dp("patients")}/${item.patient_id}${qs}`);
    } else if (item.record_id) {
      navigate(`${dp("review")}/${item.record_id}`);
    }
  }

  const handleRefresh = useCallback(async () => {
    await Promise.all([refetchQueue(), refetchDrafts()]);
  }, [refetchQueue, refetchDrafts]);

  const pendingCount = pendingDedup.length;
  const completedCount = completed.length;

  return (
    <div style={pageContainer}>
      {/* Filter tabs — flat strip on white */}
      <div
        style={{
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
          flexShrink: 0,
        }}
      >
        <JumboTabs activeKey={activeTab} onChange={handleTabChange}>
          <JumboTabs.Tab
            title={<TabTitleWithCount label="待审核" count={pendingCount} />}
            key="pending"
          />
          <JumboTabs.Tab
            title={<TabTitleWithCount label="已完成" count={completedCount} />}
            key="completed"
          />
        </JumboTabs>
      </div>

      {/* Scrollable content — page bg is gray (pageContainer), list sits in a white card */}
      <div style={scrollable}>
        <PullToRefresh onRefresh={handleRefresh}>
          {loading && <LoadingCenter />}

          {/* Unified pending tab — diagnosis reviews + reply drafts */}
          {!loading && activeTab === "pending" && (
            <>
              {pendingDedup.length > 0 ? (
                <>
                  <List
                    style={{
                      "--border-top": "none",
                      "--border-bottom": "none",
                      "--border-inner": `0.5px solid ${APP.border}`,
                    }}
                  >
                    {pendingDedup.map((item) =>
                      item._kind === "reply" ? (
                        <DraftItem
                          key={`reply-${item.id}`}
                          item={item}
                          onNavigate={handleNavigateUnified}
                        />
                      ) : (
                        <PendingItem
                          key={`review-${item.id}`}
                          item={item}
                          onNavigate={handleNavigateUnified}
                        />
                      )
                    )}
                  </List>
                  <div
                    style={{
                      textAlign: "center",
                      padding: "24px 16px 8px",
                      fontSize: FONT.sm,
                      color: APP.text4,
                    }}
                  >
                    共 {pendingCount} 条
                  </div>
                </>
              ) : (
                <ErrorBlock
                  status="empty"
                  title="暂无待审核项"
                  description="新的诊断建议和患者消息会自动出现在这里"
                  style={{ paddingTop: 48 }}
                />
              )}
            </>
          )}

          {/* Completed tab */}
          {!loading && activeTab === "completed" && (
            <>
              {completed.length > 0 ? (
                <>
                  <List
                    style={{
                      "--border-top": "none",
                      "--border-bottom": "none",
                      "--border-inner": `0.5px solid ${APP.border}`,
                    }}
                  >
                    {completed.map((item) => (
                      <CompletedItem
                        key={item.id}
                        item={item}
                        onNavigate={handleNavigateCompleted}
                      />
                    ))}
                  </List>
                  <div
                    style={{
                      textAlign: "center",
                      padding: "24px 16px 8px",
                      fontSize: FONT.sm,
                      color: APP.text4,
                    }}
                  >
                    共 {completedCount} 条
                  </div>
                </>
              ) : (
                <ErrorBlock
                  status="empty"
                  title="暂无已完成项"
                  style={{ paddingTop: 48 }}
                />
              )}
            </>
          )}

          {/* Disclaimer */}
          <div
            style={{
              textAlign: "center",
              padding: "8px 0 24px",
              fontSize: FONT.xs,
              color: APP.text4,
            }}
          >
            AI 建议仅供参考，请结合临床判断
          </div>
        </PullToRefresh>
      </div>
    </div>
  );
}
