/**
 * @route /doctor/review
 *
 * v2 ReviewQueuePage — antd-mobile rewrite.
 * Shows pending diagnosis reviews, pending reply drafts, and completed items.
 * No MUI, no src/components, no src/theme.js.
 */
import { useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  JumboTabs,
  List,
  ErrorBlock,
  PullToRefresh,
} from "antd-mobile";
import { useReviewQueue, useDrafts } from "../../../lib/doctorQueries";
import { useDoctorStore } from "../../../store/doctorStore";
import { dp } from "../../../utils/doctorBasePath";
import { APP, FONT } from "../../theme";
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

// ── Pending item row ───────────────────────────────────────────────

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

  return (
    <List.Item
      prefix={<NameAvatar name={item.patient_name} size={36} />}
      extra={
        <span style={{ fontSize: FONT.sm, color: APP.text4 }}>{item.time}</span>
      }
      description={subtitle}
      arrow
      onClick={() => onNavigate(item)}
    >
      <span style={{ fontWeight: 500 }}>{item.patient_name}</span>
    </List.Item>
  );
}

// ── Reply draft row ────────────────────────────────────────────────

function DraftItem({ item, onNavigate }) {
  const statusLabel = item.type === "undrafted" ? "需手动回复" : "AI已起草";
  const snippet = item.patient_message || item.content || "";

  return (
    <List.Item
      prefix={<NameAvatar name={item.patient_name} size={36} />}
      extra={
        <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
          {item.time || ""}
        </span>
      }
      description={`"${snippet.slice(0, 40)}" · ${statusLabel}`}
      arrow
      onClick={() => onNavigate(item)}
    >
      <span style={{ fontWeight: 500 }}>{item.patient_name}</span>
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

  // Tab state from URL: ?tab=pending (default) | ?tab=replies | ?tab=completed
  const [searchParams, setSearchParams] = useSearchParams();
  const validTabs = new Set(["pending", "replies", "completed"]);
  const urlTab = searchParams.get("tab");
  const activeTab = urlTab && validTabs.has(urlTab) ? urlTab : "pending";

  function handleTabChange(key) {
    if (key === "pending") {
      setSearchParams({}, { replace: true });
    } else {
      setSearchParams({ tab: key }, { replace: true });
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

  const pendingCount = pending.length;
  const repliesCount = activeDrafts.length;
  const completedCount = completed.length;

  return (
    <div style={pageContainer}>
      {/* Filter tabs */}
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
            title={<TabTitleWithCount label="待回复" count={repliesCount} />}
            key="replies"
          />
          <JumboTabs.Tab
            title={<TabTitleWithCount label="已完成" count={completedCount} />}
            key="completed"
          />
        </JumboTabs>
      </div>

      {/* Scrollable content */}
      <div style={scrollable}>
        <PullToRefresh onRefresh={handleRefresh}>
          {/* Loading */}
          {loading && <LoadingCenter />}

          {/* Pending tab */}
          {!loading && activeTab === "pending" && (
            <>
              {pending.length > 0 ? (
                <List>
                  {pending.map((item) => (
                    <PendingItem
                      key={item.id}
                      item={item}
                      onNavigate={handleNavigatePending}
                    />
                  ))}
                </List>
              ) : (
                <ErrorBlock
                  status="empty"
                  title="暂无待审核项"
                  description="新的诊断建议会自动出现在这里"
                  style={{ paddingTop: 48 }}
                />
              )}
            </>
          )}

          {/* Replies tab */}
          {!loading && activeTab === "replies" && (
            <>
              {activeDrafts.length > 0 ? (
                <List header="患者消息 · 待回复">
                  {activeDrafts.map((msg) => (
                    <DraftItem
                      key={msg.id}
                      item={msg}
                      onNavigate={handleNavigateDraft}
                    />
                  ))}
                </List>
              ) : (
                <ErrorBlock
                  status="empty"
                  title="暂无待回复消息"
                  description="患者消息会自动出现在这里"
                  style={{ paddingTop: 48 }}
                />
              )}
            </>
          )}

          {/* Completed tab */}
          {!loading && activeTab === "completed" && (
            <>
              {completed.length > 0 ? (
                <List>
                  {completed.map((item) => (
                    <CompletedItem
                      key={item.id}
                      item={item}
                      onNavigate={handleNavigateCompleted}
                    />
                  ))}
                </List>
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
              padding: "16px 0",
              fontSize: FONT.xs,
              color: APP.text4,
            }}
          >
            AI建议仅供参考，请结合临床判断
          </div>
        </PullToRefresh>
      </div>
    </div>
  );
}
