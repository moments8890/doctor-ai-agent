/**
 * RecordsTab — patient medical records list (v2, antd-mobile).
 *
 * Business logic ported from src/pages/patient/RecordsTab.jsx.
 * Renders:
 *  - "New record" entry button (starts interview)
 *  - Filter pills for list / timeline view + record type
 *  - List of records with type tag, date, chief complaint, status
 *  - Timeline view grouped by month
 *  - Empty state when there are no records
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  ErrorBlock,
  List,
  NavBar,
  SpinLoading,
  Tag,
} from "antd-mobile";
import { AddOutline, FileOutline } from "antd-mobile-icons";
import { usePatientApi } from "../../../api/PatientApiContext";
import { APP } from "../../theme";

// ---------------------------------------------------------------------------
// Helpers (no MUI / theme.js deps)
// ---------------------------------------------------------------------------

const RECORD_TYPE_LABEL = {
  visit: "门诊记录",
  dictation: "语音记录",
  import: "导入记录",
  interview_summary: "预问诊",
};

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

const PATIENT_RECORD_TABS = [
  { key: "", label: "全部" },
  { key: "medical", label: "病历", types: ["visit", "dictation", "import"] },
  { key: "interview", label: "问诊", types: ["interview_summary"] },
];

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
// Filter pill row
// ---------------------------------------------------------------------------

function FilterPills({ items, active, onChange }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        padding: "8px 12px",
        overflowX: "auto",
        background: APP.surface,
        borderBottom: `0.5px solid ${APP.border}`,
        flexShrink: 0,
      }}
    >
      {items.map((item) => (
        <div
          key={item.key}
          onClick={() => onChange(item.key)}
          style={{
            padding: "4px 12px",
            borderRadius: 100,
            fontSize: 13,
            whiteSpace: "nowrap",
            cursor: "pointer",
            background: active === item.key ? "#07C160" : APP.borderLight,
            color: active === item.key ? "#fff" : APP.text3,
            fontWeight: active === item.key ? 600 : 400,
            transition: "all 0.15s",
          }}
        >
          {item.label}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Timeline view
// ---------------------------------------------------------------------------

function TimelineView({ records, onTap }) {
  const groups = groupByMonth(records);
  return (
    <div style={{ padding: "8px 16px" }}>
      {groups.map((group) => (
        <div key={group.label}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: APP.text4,
              marginTop: 12,
              marginBottom: 8,
            }}
          >
            {group.label}
          </div>
          <div style={{ position: "relative", paddingLeft: 24 }}>
            {/* Vertical connecting line */}
            <div
              style={{
                position: "absolute",
                left: 7,
                top: 8,
                bottom: 8,
                width: 2,
                background: APP.borderLight,
                borderRadius: 1,
              }}
            />
            {group.items.map((rec, idx) => {
              const typeLabel = RECORD_TYPE_LABEL[rec.record_type] || rec.record_type;
              const chief = rec.structured?.chief_complaint;
              const preview = chief || (rec.content || "").replace(/\n/g, " ").slice(0, 30) || "";
              const ds = rec.status;
              const dsLabel = ds ? DIAGNOSIS_STATUS_LABELS[ds] : null;
              const dsColor = ds ? DIAGNOSIS_STATUS_COLORS[ds] : "default";
              const d = new Date(rec.created_at);
              const dayStr = `${d.getMonth() + 1}/${d.getDate()}`;
              const diagnosis = rec.structured?.diagnosis;
              const dotColor = "#07C160";

              return (
                <div
                  key={rec.id}
                  onClick={() => onTap(rec.id)}
                  style={{
                    position: "relative",
                    marginBottom: idx < group.items.length - 1 ? 12 : 0,
                    cursor: "pointer",
                  }}
                >
                  {/* Timeline dot */}
                  <div
                    style={{
                      position: "absolute",
                      left: -18,
                      top: 8,
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      background: dotColor,
                      border: "2px solid #fff",
                      zIndex: 1,
                    }}
                  />
                  {/* Card */}
                  <div
                    style={{
                      background: APP.surface,
                      borderRadius: 10,
                      padding: "8px 12px",
                      border: `0.5px solid ${APP.borderLight}`,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: 4,
                      }}
                    >
                      <span style={{ fontSize: 12, color: dotColor, fontWeight: 600 }}>
                        {typeLabel}
                      </span>
                      <span style={{ fontSize: 12, color: APP.text4 }}>{dayStr}</span>
                    </div>
                    {preview && (
                      <div
                        style={{
                          fontSize: 14,
                          fontWeight: 500,
                          color: APP.text1,
                          lineHeight: 1.4,
                          marginBottom: 4,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {preview}
                      </div>
                    )}
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      {diagnosis ? (
                        <span
                          style={{
                            fontSize: 12,
                            color: APP.text3,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            flex: 1,
                            marginRight: 8,
                          }}
                        >
                          {diagnosis}
                        </span>
                      ) : (
                        <span />
                      )}
                      {dsLabel && (
                        <Tag color={dsColor} fill="outline" style={{ fontSize: 11 }}>
                          {dsLabel}
                        </Tag>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RecordsTab
// ---------------------------------------------------------------------------

export default function RecordsTab({ token, onNewRecord, urlSubpage }) {
  const navigate = useNavigate();
  const { getPatientRecords } = usePatientApi();

  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [recordView, setRecordView] = useState("list");
  const [typeFilter, setTypeFilter] = useState("");

  const loadRecords = useCallback(() => {
    setLoading(true);
    setError(false);
    getPatientRecords(token)
      .then((data) => setRecords(Array.isArray(data) ? data : []))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [token, getPatientRecords]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const filteredRecords = typeFilter
    ? records.filter((rec) => {
        const tab = PATIENT_RECORD_TABS.find((t) => t.key === typeFilter);
        return tab?.types?.includes(rec.record_type);
      })
    : records;

  function handleTap(recordId) {
    navigate(`/patient/records/${recordId}`);
  }

  if (loading) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 32,
        }}
      >
        <SpinLoading color="primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 16 }}>
        <ErrorBlock
          status="default"
          title="加载失败"
          description="无法获取病历记录"
        >
          <Button color="primary" size="small" onClick={loadRecords}>
            重试
          </Button>
        </ErrorBlock>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* New record button */}
      <div
        style={{
          padding: "12px 16px",
          background: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
          flexShrink: 0,
        }}
      >
        <Button
          block
          color="primary"
          size="middle"
          style={{ borderRadius: 8 }}
          onClick={onNewRecord}
        >
          <AddOutline style={{ marginRight: 4 }} />
          新建病历 — 开始AI预问诊
        </Button>
      </div>

      {/* Filter pills — only show when records exist */}
      {records.length > 0 && (
        <>
          <div
            style={{
              padding: "6px 12px",
              fontSize: 12,
              color: APP.text4,
              background: APP.surface,
              flexShrink: 0,
            }}
          >
            最近 · {records.length} 份病历
          </div>
          <FilterPills
            items={[
              { key: "list", label: "病历" },
              { key: "timeline", label: "时间线" },
            ]}
            active={recordView}
            onChange={setRecordView}
          />
          <FilterPills
            items={PATIENT_RECORD_TABS}
            active={typeFilter}
            onChange={setTypeFilter}
          />
        </>
      )}

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filteredRecords.length === 0 ? (
          <ErrorBlock
            status="empty"
            title="暂无病历记录"
            description="点击上方「新建病历」开始预问诊"
          />
        ) : recordView === "list" ? (
          <List>
            {filteredRecords.map((rec) => {
              const typeLabel = RECORD_TYPE_LABEL[rec.record_type] || rec.record_type;
              const chief = rec.structured?.chief_complaint;
              const preview =
                chief || (rec.content || "").replace(/\n/g, " ").slice(0, 40) || "（内容为空）";
              const ds = rec.status;
              const dsLabel = ds ? DIAGNOSIS_STATUS_LABELS[ds] : null;
              const dsColor = ds ? DIAGNOSIS_STATUS_COLORS[ds] : "default";

              return (
                <List.Item
                  key={rec.id}
                  prefix={
                    <FileOutline
                      style={{ fontSize: 22, color: "#07C160", marginTop: 2 }}
                    />
                  }
                  title={
                    <span style={{ fontWeight: 600, fontSize: 15, color: APP.text1 }}>
                      {typeLabel}
                    </span>
                  }
                  description={
                    <span style={{ fontSize: 13, color: APP.text3 }}>{preview}</span>
                  }
                  extra={
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-end",
                        gap: 4,
                      }}
                    >
                      <span style={{ fontSize: 11, color: APP.text4 }}>
                        {formatDate(rec.created_at)}
                      </span>
                      {dsLabel && (
                        <Tag color={dsColor} fill="outline" style={{ fontSize: 11 }}>
                          {dsLabel}
                        </Tag>
                      )}
                    </div>
                  }
                  onClick={() => handleTap(rec.id)}
                  arrow
                />
              );
            })}
          </List>
        ) : (
          <TimelineView records={filteredRecords} onTap={handleTap} />
        )}
      </div>
    </div>
  );
}
