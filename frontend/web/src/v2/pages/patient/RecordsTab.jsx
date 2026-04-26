/**
 * RecordsTab — patient medical records list (v2, antd-mobile).
 *
 * Single chronological timeline grouped by month. Per a 2026-04-24 product
 * call, both the view-toggle (病历/时间线) and the type filter (全部/病历/问诊)
 * were dropped: most patients have <5 records, both controls added decision
 * cost for almost no benefit, and the colored type tag on each Card already
 * conveys type at a glance.
 *
 * Renders:
 *  - Month section header on gray bg above per-month Card stack
 *  - List of records as floating Card rows on a gray pageContainer bg
 *  - PullToRefresh wrap calls usePatientRecords().refetch
 *  - Empty / loading / error states use shared components
 */

import { useNavigate } from "react-router-dom";
import { PullToRefresh, Tag, Ellipsis } from "antd-mobile";
import { usePatientRecords } from "../../../lib/patientQueries";
import { APP, FONT, RADIUS } from "../../theme";
import { pageContainer } from "../../layouts";
import { LoadingCenter, EmptyState, Card } from "../../components";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RECORD_TYPE_LABEL = {
  visit: "门诊记录",
  dictation: "语音记录",
  import: "导入记录",
  intake_summary: "预问诊",
};

// Type tag color mapping — green for medical encounters, blue/accent for
// intake summaries, gray fallback for unknown.
const RECORD_TYPE_COLOR = {
  visit: { bg: APP.primaryLight, fg: APP.primary },
  dictation: { bg: APP.primaryLight, fg: APP.primary },
  import: { bg: APP.primaryLight, fg: APP.primary },
  intake_summary: { bg: APP.accentLight, fg: APP.accent },
};

const DEFAULT_TYPE_COLOR = { bg: APP.borderLight, fg: APP.text3 };

const DIAGNOSIS_STATUS_LABELS = {
  pending: "诊断中",
  completed: "待审核",
  confirmed: "已确认",
  failed: "诊断失败",
};

const DIAGNOSIS_STATUS_COLORS = {
  pending: "warning",
  completed: "primary",
  confirmed: "success",
  failed: "danger",
};

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}

function groupByMonth(records) {
  const groups = [];
  let currentKey = "";
  for (const rec of records) {
    const d = new Date(rec.created_at);
    const key = `${d.getFullYear()}年${d.getMonth() + 1}月`;
    if (key !== currentKey) {
      currentKey = key;
      groups.push({ label: key, items: [] });
    }
    groups[groups.length - 1].items.push(rec);
  }
  return groups;
}

// ---------------------------------------------------------------------------
// Card row
// ---------------------------------------------------------------------------

function RecordCardRow({ rec, onTap, style }) {
  const typeLabel = RECORD_TYPE_LABEL[rec.record_type] || rec.record_type;
  const typeColor = RECORD_TYPE_COLOR[rec.record_type] || DEFAULT_TYPE_COLOR;
  const chief = rec.structured?.chief_complaint;
  const fallback = (rec.content || "").replace(/\n/g, " ");
  const title = chief || fallback || "（内容为空）";
  const ds = rec.status;
  const dsLabel = ds ? DIAGNOSIS_STATUS_LABELS[ds] : null;
  const dsColor = ds ? DIAGNOSIS_STATUS_COLORS[ds] : "default";

  return (
    <Card style={style}>
      <div
        data-testid="patient-record-row"
        onClick={() => onTap(rec.id)}
        style={{
          padding: "12px 14px",
          cursor: "pointer",
          display: "flex",
          flexDirection: "column",
          gap: 6,
        }}
      >
        {/* Top row: type tag + status tag */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <span
            style={{
              display: "inline-block",
              padding: "2px 8px",
              borderRadius: RADIUS.sm,
              fontSize: FONT.xs,
              fontWeight: 600,
              background: typeColor.bg,
              color: typeColor.fg,
              flexShrink: 0,
            }}
          >
            {typeLabel}
          </span>
          {dsLabel && (
            <Tag color={dsColor} fill="outline" style={{ fontSize: FONT.xs }}>
              {dsLabel}
            </Tag>
          )}
        </div>

        {/* Title — Ellipsis rows={1}, never .slice() */}
        <div
          style={{
            fontSize: FONT.md,
            fontWeight: 600,
            color: APP.text1,
            lineHeight: 1.4,
          }}
        >
          <Ellipsis direction="end" content={title} rows={1} />
        </div>

        {/* Meta line: date · diagnosis (if any) */}
        <div
          style={{
            fontSize: FONT.sm,
            color: APP.text4,
            display: "flex",
            alignItems: "center",
            gap: 6,
            minWidth: 0,
          }}
        >
          <span style={{ flexShrink: 0 }}>{formatDate(rec.created_at)}</span>
          {rec.structured?.diagnosis && (
            <>
              <span style={{ flexShrink: 0 }}>·</span>
              <div style={{ flex: 1, minWidth: 0, color: APP.text3 }}>
                <Ellipsis
                  direction="end"
                  content={rec.structured.diagnosis}
                  rows={1}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Timeline view
// ---------------------------------------------------------------------------

function TimelineView({ records, onTap }) {
  const groups = groupByMonth(records);
  return (
    <div style={{ paddingBottom: 12 }}>
      {groups.map((group) => (
        <div key={group.label}>
          {/* Month section header — sits on gray bg, OUTSIDE the cards */}
          <div
            style={{
              fontSize: FONT.sm,
              fontWeight: 600,
              color: APP.text4,
              padding: "16px 16px 8px",
            }}
          >
            {group.label}
          </div>
          {group.items.map((rec, idx) => (
            <RecordCardRow
              key={rec.id}
              rec={rec}
              onTap={onTap}
              style={idx === 0 ? undefined : { marginTop: 8 }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RecordsTab
// ---------------------------------------------------------------------------

export default function RecordsTab({ token: _token }) {
  const navigate = useNavigate();

  const { data: records = [], isLoading, isError, refetch } = usePatientRecords();

  function handleTap(recordId) {
    navigate(`/patient/records/${recordId}`);
  }

  if (isLoading) {
    return <LoadingCenter />;
  }

  if (isError) {
    return (
      <div style={{ ...pageContainer, justifyContent: "center" }}>
        <EmptyState
          title="加载失败"
          description="无法获取病历记录"
          action="重试"
          onAction={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div style={pageContainer}>
      {/* Scrollable content with PullToRefresh */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        <PullToRefresh onRefresh={async () => { await refetch(); }}>
          {records.length === 0 ? (
            <EmptyState
              title="暂无病历记录"
              description="点击上方「新建病历」开始预问诊"
            />
          ) : (
            <TimelineView records={records} onTap={handleTap} />
          )}
        </PullToRefresh>
      </div>
    </div>
  );
}
