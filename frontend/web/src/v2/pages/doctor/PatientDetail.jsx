/**
 * @route /doctor/patients/:patientId
 *
 * v2 PatientDetail — records-first patient detail page.
 * Displays patient profile, attention card, chat link, and record list.
 * Chat/reply view is a separate subpage at ?view=chat.
 *
 * antd-mobile only. No MUI, no src/components, no src/theme.js.
 */
import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  NavBar,
  List,
  CapsuleTabs,
  Tag,
  SpinLoading,
  ErrorBlock,
  Collapse,
} from "antd-mobile";
import { LeftOutline, MessageOutline } from "antd-mobile-icons";
import { useApi } from "../../../api/ApiContext";
import { useDoctorStore } from "../../../store/doctorStore";
import { APP } from "../../theme";

// ── Record type label map ─────────────────────────────────────────────

const RECORD_TYPE_LABEL = {
  visit: "门诊",
  referral: "转诊",
  surgery: "手术",
  lab: "检验",
  imaging: "影像",
  dictation: "语音录入",
  import: "导入",
  interview_summary: "问诊总结",
};

// ── Record tab config ─────────────────────────────────────────────────

const RECORD_TABS = [
  { key: "", label: "全部", types: null },
  { key: "medical", label: "病历", types: ["visit", "dictation", "import", "surgery", "referral"] },
  { key: "lab_imaging", label: "检验/影像", types: ["lab", "imaging"] },
  { key: "interview", label: "问诊", types: ["interview_summary"] },
];

// ── Record status color ───────────────────────────────────────────────

function recordStatusBadge(status) {
  if (status === "pending_review") {
    return (
      <span
        style={{
          fontSize: 11,
          color: "#fff",
          background: "#FFC300",
          borderRadius: 4,
          padding: "1px 6px",
          fontWeight: 600,
          flexShrink: 0,
        }}
      >
        待审核
      </span>
    );
  }
  if (status === "interview_active") {
    return (
      <span
        style={{
          fontSize: 11,
          color: "#fff",
          background: "#07C160",
          borderRadius: 4,
          padding: "1px 6px",
          fontWeight: 600,
          flexShrink: 0,
        }}
      >
        问诊中
      </span>
    );
  }
  return null;
}

function formatRecordDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const Y = d.getFullYear();
  const M = String(d.getMonth() + 1).padStart(2, "0");
  const D = String(d.getDate()).padStart(2, "0");
  return `${Y}-${M}-${D}`;
}

// ── Patient profile helpers ───────────────────────────────────────────

function maskPhone(phone) {
  if (!phone || phone.length < 7) return phone || "—";
  return phone.slice(0, 3) + "****" + phone.slice(-4);
}

// ── Profile section ───────────────────────────────────────────────────

function PatientProfile({ patient, records }) {
  const age = patient.year_of_birth
    ? new Date().getFullYear() - patient.year_of_birth
    : null;
  const genderStr = patient.gender
    ? { male: "男", female: "女" }[patient.gender] || patient.gender
    : null;

  const medical = ["visit", "dictation", "import", "surgery", "referral"];
  let visitCount = 0;
  for (const r of records) {
    if (medical.includes(r.record_type)) visitCount++;
  }

  const summaryParts = [
    genderStr,
    age ? `${age}岁` : null,
    `门诊${visitCount}次`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      style={{
        padding: "12px 16px",
        background: APP.surface,
        borderBottom: `0.5px solid ${APP.border}`,
      }}
    >
      {/* Compact row always visible */}
      <Collapse>
        <Collapse.Panel
          key="profile"
          title={
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 17, color: APP.text1 }}>
                {patient.name || "患者"}
              </span>
              <span style={{ fontSize: 13, color: APP.text4 }}>{summaryParts}</span>
            </div>
          }
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "8px 16px",
              padding: "4px 0 8px",
            }}
          >
            <ProfileRow label="性别" value={genderStr || "—"} />
            <ProfileRow label="年龄" value={age ? `${age}岁` : "—"} />
            <ProfileRow label="出生年份" value={patient.year_of_birth ? `${patient.year_of_birth}年` : "—"} />
            <ProfileRow label="手机" value={maskPhone(patient.phone)} />
          </div>
        </Collapse.Panel>
      </Collapse>
    </div>
  );
}

function ProfileRow({ label, value }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 11, color: APP.text4 }}>{label}</span>
      <span style={{ fontSize: 14, color: APP.text2 }}>{value}</span>
    </div>
  );
}

// ── Attention card ────────────────────────────────────────────────────

function AttentionCard({ pendingReviewCount, draftCount, onPendingClick, onDraftClick }) {
  if (!pendingReviewCount && !draftCount) return null;

  return (
    <div
      style={{
        background: APP.surface,
        borderBottom: `0.5px solid ${APP.border}`,
        padding: "8px 16px",
        marginBottom: 8,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: "#FFC300",
          marginBottom: 8,
        }}
      >
        ⚡ 需要你处理
      </div>

      {pendingReviewCount > 0 && (
        <div
          onClick={onPendingClick}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "8px 0",
            cursor: "pointer",
            borderBottom: draftCount ? `0.5px solid ${APP.borderLight}` : "none",
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 6,
              background: "#FFF8E0",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 16,
              flexShrink: 0,
            }}
          >
            📋
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: APP.text1 }}>
              {pendingReviewCount} 条病历待审核
            </div>
            <div style={{ fontSize: 12, color: APP.text4, marginTop: 2 }}>
              点击查看并确认
            </div>
          </div>
          <span style={{ fontSize: 16, color: APP.text4 }}>›</span>
        </div>
      )}

      {draftCount > 0 && (
        <div
          onClick={onDraftClick}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "8px 0",
            cursor: "pointer",
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 6,
              background: APP.primaryLight,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 16,
              flexShrink: 0,
            }}
          >
            ✉️
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: APP.text1 }}>
              {draftCount} 条消息待回复
            </div>
            <div style={{ fontSize: 12, color: APP.text4, marginTop: 2 }}>
              AI已起草 · 待你确认
            </div>
          </div>
          <span style={{ fontSize: 16, color: APP.text4 }}>›</span>
        </div>
      )}
    </div>
  );
}

// ── Chat nav card ─────────────────────────────────────────────────────

function ChatNavCard({ messageCount, draftCount, onClick }) {
  return (
    <div
      style={{
        background: APP.surface,
        borderTop: `0.5px solid ${APP.border}`,
        borderBottom: `0.5px solid ${APP.border}`,
        marginBottom: 8,
      }}
    >
      <div
        onClick={onClick}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 16px",
          cursor: "pointer",
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 6,
            background: APP.primaryLight,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <MessageOutline style={{ fontSize: 18, color: "#07C160" }} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 500, color: APP.text1 }}>
            患者消息
            {messageCount > 0 && (
              <span style={{ fontSize: 12, color: APP.text4, fontWeight: 400, marginLeft: 4 }}>
                ({messageCount})
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: APP.text4, marginTop: 2 }}>
            {draftCount > 0 ? `${draftCount} 条待回复` : "查看聊天记录"}
          </div>
        </div>
        {draftCount > 0 && (
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "#fff",
              background: "#FA5151",
              borderRadius: 8,
              padding: "0 6px",
              minWidth: 16,
              textAlign: "center",
              lineHeight: "18px",
            }}
          >
            {draftCount}
          </div>
        )}
        <span style={{ fontSize: 16, color: APP.text4 }}>›</span>
      </div>
    </div>
  );
}

// ── Record row ────────────────────────────────────────────────────────

function RecordRow({ record, onClick }) {
  const typeLabel = RECORD_TYPE_LABEL[record.record_type] || record.record_type || "病历";
  const dateStr = formatRecordDate(record.created_at || record.visit_date);
  const complaint = record.chief_complaint || record.summary || "";
  const preview = complaint.length > 40 ? complaint.slice(0, 40) + "…" : complaint;
  const statusBadge = recordStatusBadge(record.status);

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "12px 16px",
        background: APP.surface,
        borderBottom: `0.5px solid ${APP.borderLight}`,
        cursor: "pointer",
      }}
    >
      {/* Type tag */}
      <div style={{ flexShrink: 0, paddingTop: 2 }}>
        <Tag
          color={
            record.record_type === "lab"
              ? "#576B95"
              : record.record_type === "imaging"
              ? "#576B95"
              : "#07C160"
          }
          fill="outline"
          style={{ "--border-radius": "4px", fontSize: 11 }}
        >
          {typeLabel}
        </Tag>
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, color: APP.text1, lineHeight: "1.5", wordBreak: "break-word" }}>
          {preview || "（无主诉）"}
        </div>
        <div style={{ fontSize: 12, color: APP.text4, marginTop: 4 }}>{dateStr}</div>
      </div>

      {/* Status + chevron */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        {statusBadge}
        <span style={{ fontSize: 16, color: APP.text4 }}>›</span>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────

export default function PatientDetail({ patientId: propPatientId }) {
  const params = useParams();
  const patientId = propPatientId || params.patientId;
  const navigate = useNavigate();
  const { doctorId } = useDoctorStore();
  const { getPatients, getRecords, fetchDrafts } = useApi();

  const [patient, setPatient] = useState(null);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("");
  const [draftCount, setDraftCount] = useState(0);
  const [messageCount] = useState(0);

  // ── Load patient info ──────────────────────────────────────────────
  useEffect(() => {
    if (!patientId || !doctorId) return;
    getPatients(doctorId, {}, 200)
      .then((data) => {
        const items = Array.isArray(data) ? data : data?.items || [];
        const found = items.find((p) => String(p.id) === String(patientId));
        setPatient(found || { id: patientId, name: "患者" });
      })
      .catch(() => setPatient({ id: patientId, name: "患者" }));
  }, [patientId, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load records ───────────────────────────────────────────────────
  const loadRecords = useCallback(async () => {
    if (!patientId || !doctorId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getRecords({ doctorId, patientId, limit: 100 });
      const items = Array.isArray(data) ? data : data?.items || [];
      // Sort: actionable first, then by date desc
      items.sort((a, b) => {
        const actionable = (r) =>
          r.status === "pending_review" || r.status === "interview_active" ? 1 : 0;
        const diff = actionable(b) - actionable(a);
        if (diff !== 0) return diff;
        return (b.created_at || "").localeCompare(a.created_at || "");
      });
      setRecords(items);
    } catch (e) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [patientId, doctorId, getRecords]);

  // ── Load drafts (for counts) ───────────────────────────────────────
  const loadDraftCount = useCallback(async () => {
    if (!patientId || !doctorId) return;
    try {
      const data = await fetchDrafts(doctorId, { patientId });
      const all = Array.isArray(data) ? data : data?.pending_messages || [];
      const pending = all.filter(
        (d) => d.type === "draft" && d.status !== "sent" && (d.draft_text || d.content)
      );
      setDraftCount(pending.length);
    } catch {
      // non-critical
    }
  }, [patientId, doctorId, fetchDrafts]);

  useEffect(() => {
    loadRecords();
    loadDraftCount();
  }, [loadRecords, loadDraftCount]);

  // ── Tab filtering ──────────────────────────────────────────────────
  const activeGroup = RECORD_TABS.find((g) => g.key === activeTab);
  const filteredRecords = activeGroup?.types
    ? records.filter((r) => activeGroup.types.includes(r.record_type))
    : records;

  const pendingReviewCount = records.filter((r) => r.status === "pending_review").length;

  // ── Handlers ──────────────────────────────────────────────────────
  function handleBack() {
    navigate("/doctor/patients", { replace: true });
  }

  function goToChat() {
    navigate(`/doctor/patients/${patientId}?view=chat`);
  }

  function goToPendingReview() {
    const pending = records.find((r) => r.status === "pending_review");
    if (pending) navigate(`/doctor/review/${pending.id}`);
  }

  function goToRecord(record) {
    navigate(`/doctor/review/${record.id}`);
  }

  const patientName = patient?.name || "患者";

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      {/* NavBar */}
      <NavBar
        backArrow={<LeftOutline />}
        onBack={handleBack}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        {patientName}
      </NavBar>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {/* Patient profile (collapsible) */}
        {patient && <PatientProfile patient={patient} records={records} />}

        {/* Attention card */}
        <AttentionCard
          pendingReviewCount={pendingReviewCount}
          draftCount={draftCount}
          onPendingClick={goToPendingReview}
          onDraftClick={goToChat}
        />

        {/* Chat nav card */}
        <ChatNavCard
          messageCount={messageCount}
          draftCount={draftCount}
          onClick={goToChat}
        />

        {/* Record list */}
        <div>
          {/* Filter tabs */}
          <CapsuleTabs
            activeKey={activeTab}
            onChange={setActiveTab}
            style={{
              "--adm-color-primary": "#07C160",
              background: APP.surface,
              padding: "8px 12px",
              borderBottom: `0.5px solid ${APP.border}`,
            }}
          >
            {RECORD_TABS.map((tab) => (
              <CapsuleTabs.Tab key={tab.key} title={tab.label} />
            ))}
          </CapsuleTabs>

          {/* Loading */}
          {loading && (
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                padding: "40px 0",
              }}
            >
              <SpinLoading color="#07C160" style={{ "--size": "24px" }} />
            </div>
          )}

          {/* Error */}
          {!loading && error && (
            <ErrorBlock
              title="加载失败"
              description={error}
              style={{ padding: "24px 0" }}
            />
          )}

          {/* Empty */}
          {!loading && !error && filteredRecords.length === 0 && (
            <div
              style={{
                textAlign: "center",
                padding: "48px 16px",
                fontSize: 14,
                color: APP.text4,
              }}
            >
              暂无病历
            </div>
          )}

          {/* Record rows */}
          {!loading &&
            !error &&
            filteredRecords.map((record) => (
              <RecordRow
                key={record.id}
                record={record}
                onClick={() => goToRecord(record)}
              />
            ))}
        </div>

        {/* Bottom spacing */}
        <div style={{ height: 32 }} />
      </div>
    </div>
  );
}
