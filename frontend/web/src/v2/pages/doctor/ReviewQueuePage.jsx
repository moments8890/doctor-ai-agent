/**
 * @route /doctor/review
 *
 * v2 ReviewQueuePage — antd-mobile rewrite.
 * Shows pending diagnosis reviews, pending reply drafts, and completed items.
 * No MUI, no src/components, no src/theme.js.
 */
import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  JumboTabs,
  List,
  SpinLoading,
  ErrorBlock,
  PullToRefresh,
  Tag,
} from "antd-mobile";
import { useReviewQueue, useDrafts } from "../../../lib/doctorQueries";
import { useDoctorStore } from "../../../store/doctorStore";
import { dp } from "../../../utils/doctorBasePath";
import { APP, FONT, RADIUS } from "../../theme";

// ── Helpers ────────────────────────────────────────────────────────

function NameCircle({ name }) {
  const ch = (name || "?")[0];
  return (
    <div
      style={{
        width: 36,
        height: 36,
        borderRadius: "50%",
        background: APP.primary,
        color: APP.white,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: FONT.md,
        fontWeight: 600,
        flexShrink: 0,
      }}
    >
      {ch}
    </div>
  );
}

const SECTION_LABEL = {
  differential: "鉴别诊断",
  workup: "检查建议",
  treatment: "治疗方向",
};

// ── Pending item row ───────────────────────────────────────────────

function PendingItem({ item, onNavigate }) {
  const urgency = item.urgency === "urgent";
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
      prefix={<NameCircle name={item.patient_name} />}
      extra={
        <span style={{ fontSize: FONT.sm, color: APP.text4 }}>{item.time}</span>
      }
      description={subtitle}
      arrow
      onClick={() => onNavigate(item)}
    >
      <span style={{ fontWeight: 500 }}>{item.patient_name}</span>
      {urgency ? (
        <Tag color="danger" style={{ marginLeft: 6, fontSize: FONT.xs }}>
          紧急
        </Tag>
      ) : (
        <Tag color="warning" style={{ marginLeft: 6, fontSize: FONT.xs }}>
          待处理
        </Tag>
      )}
    </List.Item>
  );
}

// ── Reply draft row ────────────────────────────────────────────────

function DraftItem({ item, onNavigate }) {
  const statusLabel = item.type === "undrafted" ? "需手动回复" : "AI已起草";
  const snippet = item.patient_message || item.content || "";

  return (
    <List.Item
      prefix={<NameCircle name={item.patient_name} />}
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
      {item.badge === "urgent" && (
        <Tag color="danger" style={{ marginLeft: 6, fontSize: FONT.xs }}>
          紧急
        </Tag>
      )}
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
      prefix={<NameCircle name={item.patient_name} />}
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

  // Tab from URL
  const params = new URLSearchParams(window.location.search);
  const tabFromUrl = params.get("tab");
  const validTabs = new Set(["pending", "replies", "completed"]);
  const [activeTab, setActiveTab] = useState(
    tabFromUrl && validTabs.has(tabFromUrl) ? tabFromUrl : "pending"
  );

  function handleTabChange(key) {
    setActiveTab(key);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", key);
    window.history.replaceState(null, "", url);
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
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
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
            title={`待审核${pendingCount > 0 ? ` ${pendingCount}` : ""}`}
            key="pending"
          />
          <JumboTabs.Tab
            title={`待回复${repliesCount > 0 ? ` ${repliesCount}` : ""}`}
            key="replies"
          />
          <JumboTabs.Tab
            title={`已完成${completedCount > 0 ? ` ${completedCount}` : ""}`}
            key="completed"
          />
        </JumboTabs>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        <PullToRefresh onRefresh={handleRefresh}>
          {/* Loading */}
          {loading && (
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                paddingTop: 48,
              }}
            >
              <SpinLoading color="primary" />
            </div>
          )}

          {/* Pending tab */}
          {!loading && activeTab === "pending" && (
            <>
              {pending.length > 0 ? (
                <List header="待审核">
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
                <List header="已完成">
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
