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
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  NavBar,
  List,
  JumboTabs,
  Tag,
  ErrorBlock,
  Collapse,
  ActionSheet,
  Dialog,
  Toast,
  Popup,
  SpinLoading,
  Button,
  Ellipsis,
} from "antd-mobile";
import { LeftOutline, MessageOutline, ContentOutline, MailOutline, MoreOutline, RedoOutline } from "antd-mobile-icons";
import PatientChatPage from "./PatientChatPage";
import { QRCodeSVG } from "qrcode.react";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { useDoctorStore } from "../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { LoadingCenter } from "../../components";
import { STRUCTURED_FIELD_LABELS } from "../../../pages/doctor/constants";

// Fields to show inside an expanded record card, in reading order.
const RECORD_DETAIL_FIELDS = [
  "chief_complaint",
  "present_illness",
  "past_history",
  "allergy_history",
  "physical_exam",
  "auxiliary_exam",
  "diagnosis",
  "treatment_plan",
  "orders_followup",
];

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

// ── Tab config (v2: 3 tabs — 总览 / 病历 / 聊天) ────────────────────
// "overview" shows curated cards (AI summary, clinical context, attention)
// "records"  shows the flat chronological record list
// "chat"     navigates to the dedicated chat subpage (?view=chat)

const TAB_OVERVIEW = "overview";
const TAB_RECORDS = "records";
const TAB_CHAT = "chat";

// Keys in record.structured that we surface in the Overview clinical card.
const CLINICAL_FIELDS = [
  { key: "diagnosis",       label: "诊断" },
  { key: "treatment_plan",  label: "用药" },
  { key: "allergy_history", label: "过敏", danger: true },
  { key: "past_history",    label: "既往" },
];

// ── Record status color ───────────────────────────────────────────────

function recordStatusBadge(status) {
  if (status === "pending_review") {
    return (
      <span
        style={{
          fontSize: FONT.xs,
          color: APP.white,
          background: APP.warning,
          borderRadius: RADIUS.xs,
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
          fontSize: FONT.xs,
          color: APP.white,
          background: APP.primary,
          borderRadius: RADIUS.xs,
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

// Merge structured fields across all records. Later records override earlier
// ones so the Overview reflects the doctor's most recent understanding.
function buildClinicalContext(records) {
  const merged = {};
  // Oldest → newest so later writes win
  const ordered = [...records].sort(
    (a, b) => (a.created_at || "").localeCompare(b.created_at || "")
  );
  for (const r of ordered) {
    const s = r.structured || {};
    for (const { key } of CLINICAL_FIELDS) {
      if (s[key] && String(s[key]).trim()) {
        merged[key] = String(s[key]).trim();
      }
    }
  }
  return merged;
}

// AI summary text — prefer patient.ai_summary (backend-generated, refreshed
// after each new record). Fall back to the most recent record's summary_text
// or chief_complaint when the LLM summary hasn't been generated yet.
function buildAiSummary(patient, records) {
  if (patient?.ai_summary && patient.ai_summary.trim()) {
    return patient.ai_summary.trim();
  }
  for (const r of records) {
    if (r.summary_text && r.summary_text.trim()) return r.summary_text.trim();
    const s = r.structured || {};
    if (s.chief_complaint && s.chief_complaint.trim()) return s.chief_complaint.trim();
  }
  return "";
}

// "N小时前更新" / "N天前更新" age indicator for the AI-summary card.
function formatSummaryAge(ts) {
  if (!ts) return null;
  const raw = ts.includes("Z") || ts.includes("+") ? ts : ts + "Z";
  const then = new Date(raw);
  if (isNaN(then.getTime())) return null;
  const minutes = Math.floor((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "刚刚更新";
  if (minutes < 60) return `${minutes}分钟前更新`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前更新`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}天前更新`;
  return `${then.getMonth() + 1}-${then.getDate()} 更新`;
}

// ── Patient profile helpers ───────────────────────────────────────────

function maskPhone(phone) {
  if (!phone || phone.length < 7) return phone || "—";
  return phone.slice(0, 3) + "****" + phone.slice(-4);
}

// ── Profile section ───────────────────────────────────────────────────

function PatientProfile({ patient, records, onStartInterview }) {
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

  // Recency: last activity or most recent record date, formatted as MM-DD
  const recencyDate = (() => {
    const raw = patient.last_activity_at || records[0]?.created_at;
    if (!raw) return null;
    const d = new Date(raw);
    if (isNaN(d.getTime())) return null;
    return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  })();

  const summaryParts = [
    genderStr,
    age ? `${age}岁` : null,
    `门诊${visitCount}次`,
    recencyDate ? `最近${recencyDate}` : null,
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
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, width: "100%" }}>
              <span style={{ fontWeight: 700, fontSize: FONT.lg, color: APP.text1, flexShrink: 0 }}>
                {patient.name || "患者"}
              </span>
              <div style={{ fontSize: FONT.sm, color: APP.text4, flex: 1, minWidth: 0 }}>
                <Ellipsis direction="end" content={summaryParts} rows={1} />
              </div>
              <span
                onClick={(e) => { e.stopPropagation(); onStartInterview?.(); }}
                style={{
                  fontSize: FONT.sm,
                  color: APP.primary,
                  fontWeight: 500,
                  flexShrink: 0,
                  cursor: "pointer",
                  marginRight: 8,
                }}
              >
                新建门诊
              </span>
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
      <span style={{ fontSize: FONT.xs, color: APP.text4 }}>{label}</span>
      <span style={{ fontSize: FONT.main, color: APP.text2 }}>{value}</span>
    </div>
  );
}

// ── Attention card ────────────────────────────────────────────────────

function AttentionCard({ pendingReviewCount, draftCount, onPendingClick, onDraftClick }) {
  if (!pendingReviewCount && !draftCount) return null;

  return (
    <List
      header={
        <span style={{ fontSize: FONT.xs, fontWeight: 600, color: APP.warning }}>
          ⚡ 需要你处理
        </span>
      }
      style={{ "--border-top": "none", marginBottom: 8 }}
    >
      {pendingReviewCount > 0 && (
        <List.Item
          prefix={
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: RADIUS.sm,
                background: APP.warningLight,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <ContentOutline style={{ fontSize: FONT.md, color: APP.warning }} />
            </div>
          }
          description="点击查看并确认"
          arrow
          onClick={onPendingClick}
          style={{ "--adm-font-size-main": FONT.main }}
        >
          <span style={{ fontWeight: 500 }}>{pendingReviewCount} 条病历待审核</span>
        </List.Item>
      )}

      {draftCount > 0 && (
        <List.Item
          prefix={
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: RADIUS.sm,
                background: APP.primaryLight,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <MailOutline style={{ fontSize: FONT.md, color: APP.primary }} />
            </div>
          }
          description="AI已起草 · 待你确认"
          arrow
          onClick={onDraftClick}
          style={{ "--adm-font-size-main": FONT.main }}
        >
          <span style={{ fontWeight: 500 }}>{draftCount} 条消息待回复</span>
        </List.Item>
      )}
    </List>
  );
}

// ── Chat nav card ─────────────────────────────────────────────────────

function ChatNavCard({ messageCount, draftCount, onClick }) {
  return (
    <List style={{ marginBottom: 8 }}>
      <List.Item
        prefix={
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: RADIUS.sm,
              background: APP.primaryLight,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <MessageOutline style={{ fontSize: FONT.lg, color: APP.primary }} />
          </div>
        }
        description={draftCount > 0 ? `${draftCount} 条待回复` : "查看聊天记录"}
        extra={
          draftCount > 0 ? (
            <div
              style={{
                fontSize: FONT.sm,
                fontWeight: 600,
                color: APP.white,
                background: APP.danger,
                borderRadius: RADIUS.md,
                padding: "0 6px",
                minWidth: 16,
                textAlign: "center",
                lineHeight: "18px",
              }}
            >
              {draftCount}
            </div>
          ) : null
        }
        arrow
        onClick={onClick}
        style={{ "--adm-font-size-main": FONT.md }}
      >
        <span style={{ fontWeight: 500 }}>
          患者消息
          {messageCount > 0 && (
            <span style={{ fontSize: FONT.sm, color: APP.text4, fontWeight: 400, marginLeft: 4 }}>
              ({messageCount})
            </span>
          )}
        </span>
      </List.Item>
    </List>
  );
}

// ── Record row ────────────────────────────────────────────────────────

function RecordCard({ record, onViewFull }) {
  const dateStr = formatRecordDate(record.created_at || record.visit_date);
  const complaint =
    record.chief_complaint ||
    record.structured?.chief_complaint ||
    record.summary ||
    "";
  const statusBadge = recordStatusBadge(record.status);
  const structured = record.structured || {};
  const filled = RECORD_DETAIL_FIELDS.filter((k) => structured[k]);
  const hasBody = filled.length > 0 || record.content;

  // No body → tap navigates straight to full detail (no empty expand)
  if (!hasBody) {
    return (
      <div
        onClick={() => onViewFull?.()}
        style={{
          background: APP.surface,
          border: `0.5px solid ${APP.border}`,
          borderRadius: RADIUS.md,
          margin: "8px 12px",
          padding: "12px 14px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          cursor: "pointer",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: FONT.md, fontWeight: 500, color: APP.text1, marginBottom: 2 }}>
            <Ellipsis direction="end" content={complaint || "（无主诉）"} rows={1} />
          </div>
          <div style={{ fontSize: FONT.sm, color: APP.text4 }}>{dateStr}</div>
        </div>
        {statusBadge}
        <span style={{ fontSize: FONT.sm, color: APP.text4 }}>›</span>
      </div>
    );
  }

  return (
    <div
      style={{
        background: APP.surface,
        border: `0.5px solid ${APP.border}`,
        borderRadius: RADIUS.md,
        margin: "8px 12px",
        overflow: "hidden",
      }}
    >
      <Collapse
        defaultActiveKey={[String(record.id)]}
        style={{ "--adm-color-background": APP.surface, background: APP.surface }}
      >
        <Collapse.Panel
          key={String(record.id)}
          title={
            <div style={{ display: "flex", alignItems: "center", gap: 10, width: "100%" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: FONT.md, fontWeight: 500, color: APP.text1, marginBottom: 2 }}>
                  <Ellipsis direction="end" content={complaint || "（无主诉）"} rows={1} />
                </div>
                <div style={{ fontSize: FONT.sm, color: APP.text4 }}>{dateStr}</div>
              </div>
              {statusBadge}
            </div>
          }
        >
          <div style={{ padding: "0 0 4px" }}>
            {filled.map((k, i) => (
              <div
                key={k}
                style={{
                  display: "flex",
                  gap: 10,
                  padding: "6px 0",
                  borderTop: i === 0 ? "none" : `0.5px solid ${APP.borderLight}`,
                }}
              >
                <span
                  style={{
                    fontSize: FONT.sm,
                    color: APP.text4,
                    fontWeight: 500,
                    flexShrink: 0,
                    minWidth: 60,
                  }}
                >
                  {STRUCTURED_FIELD_LABELS[k] || k}
                </span>
                <span
                  style={{
                    flex: 1,
                    fontSize: FONT.sm,
                    color: APP.text2,
                    whiteSpace: "pre-wrap",
                    lineHeight: 1.6,
                  }}
                >
                  {structured[k]}
                </span>
              </div>
            ))}
            {filled.length === 0 && record.content && (
              <div
                style={{
                  fontSize: FONT.sm,
                  color: APP.text2,
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.6,
                }}
              >
                {record.content}
              </div>
            )}
            {onViewFull && (
              <div
                onClick={(e) => {
                  e.stopPropagation();
                  onViewFull();
                }}
                style={{
                  marginTop: 8,
                  paddingTop: 8,
                  borderTop: `0.5px solid ${APP.borderLight}`,
                  fontSize: FONT.sm,
                  color: APP.primary,
                  cursor: "pointer",
                  textAlign: "center",
                }}
              >
                查看完整详情 ›
              </div>
            )}
          </div>
        </Collapse.Panel>
      </Collapse>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────

export default function PatientDetail({ patientId: propPatientId }) {
  const params = useParams();
  const patientId = propPatientId || params.patientId;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const { getPatients, getRecords, fetchDrafts } = api;

  // Tab state — local state (survives being buried in the page stack).
  // Initialized from URL on mount; tab changes update both local state and URL.
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(() => {
    const v = new URLSearchParams(window.location.search).get("view");
    return v === "records" ? TAB_RECORDS : v === "chat" ? TAB_CHAT : TAB_OVERVIEW;
  });

  const [patient, setPatient] = useState(null);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [draftCount, setDraftCount] = useState(0);
  const [messageCount] = useState(0);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [refreshingSummary, setRefreshingSummary] = useState(false);
  // Local optimistic patch so the card reflects a fresh summary immediately
  // after manual refresh, without waiting for the patient-list query to refetch.
  const [summaryOverride, setSummaryOverride] = useState(null);
  const [qrUrl, setQrUrl] = useState("");
  const [qrLoading, setQrLoading] = useState(false);
  const [qrError, setQrError] = useState("");

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
  const pendingReviewCount = records.filter((r) => r.status === "pending_review").length;

  // ── Handlers ──────────────────────────────────────────────────────
  function handleBack() {
    navigate(-1);
  }

  function goToChat() {
    setActiveTab(TAB_CHAT);
    setSearchParams({ view: "chat" }, { replace: true });
  }

  function goToPendingReview() {
    const pending = records.find((r) => r.status === "pending_review");
    if (pending) navigate(`/doctor/review/${pending.id}`);
  }

  function goToRecord(record) {
    navigate(`/doctor/review/${record.id}`);
  }

  async function handleRefreshSummary() {
    if (!patient?.id || refreshingSummary) return;
    setRefreshingSummary(true);
    try {
      const data = await api.refreshPatientAiSummary(patient.id, doctorId);
      setSummaryOverride({
        ai_summary: data?.ai_summary || null,
        ai_summary_at: data?.ai_summary_at || null,
      });
      queryClient.invalidateQueries({ queryKey: QK.patients(doctorId) });
      Toast.show({ content: "已更新", position: "bottom" });
    } catch (e) {
      Toast.show({ content: e?.message || "刷新失败", position: "bottom" });
    } finally {
      setRefreshingSummary(false);
    }
  }

  function handleStartInterview() {
    // Route to the interview flow for an existing patient; InterviewPage can
    // read these params to prefill patient context.
    const qs = new URLSearchParams({
      patient_id: String(patient.id),
      patient_name: patient.name || "",
    });
    navigate(`/doctor/patients/new?${qs.toString()}`);
  }

  function handleTabChange(key) {
    setActiveTab(key);
    const viewParam = key === TAB_OVERVIEW ? null : key;
    if (viewParam) {
      setSearchParams({ view: viewParam }, { replace: true });
    } else {
      setSearchParams({}, { replace: true });
    }
  }

  const clinical = buildClinicalContext(records);
  // After a manual refresh, prefer the override so the card updates instantly.
  const effectivePatient = summaryOverride
    ? { ...patient, ...summaryOverride }
    : patient;
  const aiSummary = buildAiSummary(effectivePatient, records);
  const aiSummaryAge = effectivePatient?.ai_summary
    ? formatSummaryAge(effectivePatient.ai_summary_at)
    : null;
  const hasClinical = Object.keys(clinical).length > 0;
  const hasAttention = pendingReviewCount > 0 || draftCount > 0;

  // Compact stat line under the name in the header strip
  const age = patient?.year_of_birth
    ? new Date().getFullYear() - patient.year_of_birth
    : null;
  const genderStr = patient?.gender
    ? { male: "男", female: "女" }[patient.gender] || patient.gender
    : null;
  const medicalTypes = ["visit", "dictation", "import", "surgery", "referral"];
  const visitCount = records.filter((r) => medicalTypes.includes(r.record_type)).length;
  const recencyDate = (() => {
    const raw = patient?.last_activity_at || records[0]?.created_at;
    if (!raw) return null;
    const d = new Date(raw);
    if (isNaN(d.getTime())) return null;
    return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  })();
  const statLine = [
    genderStr,
    age ? `${age}岁` : null,
    `门诊${visitCount}次`,
    recencyDate ? `最近${recencyDate}` : null,
  ].filter(Boolean).join(" · ");

  async function handleDelete() {
    const confirmed = await Dialog.confirm({
      title: "删除患者",
      content: `确定删除「${patient?.name || "该患者"}」？所有病历和任务将一并删除，无法恢复。`,
      confirmText: "确认删除",
      cancelText: "保留",
    });
    if (!confirmed) return;
    try {
      await api.deletePatient(patient.id, doctorId);
      queryClient.invalidateQueries({ queryKey: QK.patients(doctorId) });
      Toast.show({ content: "已删除", position: "bottom" });
      navigate("/doctor/patients", { replace: true });
    } catch (e) {
      Toast.show({ content: e?.message || "删除失败", position: "bottom" });
    }
  }

  async function handleExportPdf() {
    Toast.show({ icon: "loading", content: "导出中…", duration: 0 });
    try {
      await api.exportPatientPdf(patient.id, doctorId);
      Toast.clear();
      Toast.show({ content: "已开始下载", position: "bottom" });
    } catch (e) {
      Toast.clear();
      Toast.show({ content: e?.message || "导出失败", position: "bottom" });
    }
  }

  async function handleExportReport() {
    Toast.show({ icon: "loading", content: "生成中…", duration: 0 });
    try {
      await api.exportOutpatientReport(patient.id, doctorId);
      Toast.clear();
      Toast.show({ content: "已开始下载", position: "bottom" });
    } catch (e) {
      Toast.clear();
      Toast.show({ content: e?.message || "生成失败，请确认已有病历记录", position: "bottom" });
    }
  }

  async function handlePatientQR() {
    setQrOpen(true);
    setQrLoading(true);
    setQrError("");
    try {
      const data = await api.generateQRToken("patient", doctorId, patient.id);
      setQrUrl(data?.url || "");
      if (!data?.url) setQrError("生成失败");
    } catch (e) {
      setQrUrl("");
      setQrError(e?.message || "生成失败");
    } finally {
      setQrLoading(false);
    }
  }

  const OVERFLOW_ACTIONS = [
    { key: "pdf",     text: "导出PDF",   onClick: handleExportPdf },
    { key: "report",  text: "门诊报告",  onClick: handleExportReport },
    { key: "qr",      text: "患者二维码", onClick: handlePatientQR },
    { key: "delete",  text: "删除患者",   onClick: handleDelete,  danger: true },
  ];

  const patientName = patient?.name || "患者";

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div style={pageContainer}>
      {/* NavBar */}
      <NavBar
        backArrow={<LeftOutline />}
        onBack={handleBack}
        right={
          <div
            onClick={() => setOverflowOpen(true)}
            style={{ padding: "4px 8px", cursor: "pointer" }}
            aria-label="更多操作"
          >
            <MoreOutline style={{ fontSize: 22, color: APP.text2 }} />
          </div>
        }
        style={navBarStyle}
      >
        {patientName}
      </NavBar>

      {/* Overflow menu */}
      <ActionSheet
        visible={overflowOpen}
        actions={OVERFLOW_ACTIONS}
        onClose={() => setOverflowOpen(false)}
        onAction={(action) => {
          setOverflowOpen(false);
          action.onClick?.();
        }}
      />

      {/* Patient QR code sheet */}
      <Popup
        visible={qrOpen}
        onMaskClick={() => setQrOpen(false)}
        position="bottom"
        bodyStyle={{
          borderRadius: `${RADIUS.lg}px ${RADIUS.lg}px 0 0`,
          paddingBottom: "env(safe-area-inset-bottom, 0px)",
        }}
      >
        <div style={{ padding: "20px 16px 24px", textAlign: "center" }}>
          <div style={{
            fontSize: FONT.lg, fontWeight: 600, color: APP.text1, marginBottom: 16,
          }}>
            患者二维码
          </div>

          {qrLoading && (
            <div style={{ padding: "48px 0" }}>
              <SpinLoading color="primary" style={{ "--size": "32px" }} />
            </div>
          )}

          {!qrLoading && qrError && (
            <div style={{ padding: "48px 0", fontSize: FONT.main, color: APP.danger }}>
              {qrError}
            </div>
          )}

          {!qrLoading && !qrError && qrUrl && (
            <>
              <div style={{
                display: "inline-block",
                padding: 16,
                background: APP.white,
                borderRadius: RADIUS.md,
                border: `1px solid ${APP.borderLight}`,
              }}>
                <QRCodeSVG value={qrUrl} size={200} level="M" />
              </div>
              {patient?.name && (
                <div style={{
                  marginTop: 12, fontSize: FONT.main, fontWeight: 600, color: APP.text1,
                }}>
                  {patient.name}
                </div>
              )}
              <div style={{ marginTop: 4, fontSize: FONT.sm, color: APP.text4 }}>
                有效期30天
              </div>
            </>
          )}

          <div style={{ marginTop: 20, display: "flex", gap: 8 }}>
            <Button block fill="outline" onClick={() => setQrOpen(false)}>
              关闭
            </Button>
            <Button
              block
              color="primary"
              fill="outline"
              onClick={handlePatientQR}
              loading={qrLoading}
            >
              重新生成
            </Button>
          </div>
        </div>
      </Popup>

      {/* Header strip — one-line name + stat + 新建门诊 CTA */}
      {patient && (
        <div
          style={{
            background: APP.surface,
            padding: "10px 16px",
            display: "flex",
            alignItems: "center",
            gap: 8,
            borderBottom: `0.5px solid ${APP.border}`,
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: FONT.md, fontWeight: 700, color: APP.text1, flexShrink: 0 }}>
            {patient.name || "患者"}
          </span>
          <div
            style={{
              flex: 1,
              fontSize: FONT.sm,
              color: APP.text4,
              minWidth: 0,
            }}
          >
            <Ellipsis direction="end" content={statLine} rows={1} />
          </div>
          <span
            onClick={handleStartInterview}
            style={{
              fontSize: FONT.sm,
              color: APP.primary,
              fontWeight: 500,
              flexShrink: 0,
              cursor: "pointer",
            }}
          >
            + 新建门诊
          </span>
        </div>
      )}

      {/* Tabs */}
      <div
        style={{
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
          flexShrink: 0,
        }}
      >
        <JumboTabs activeKey={activeTab} onChange={handleTabChange}>
          <JumboTabs.Tab title="总览" key={TAB_OVERVIEW} />
          <JumboTabs.Tab title="病历" key={TAB_RECORDS} />
          <JumboTabs.Tab
            title={draftCount > 0 ? `聊天 (${draftCount})` : "聊天"}
            key={TAB_CHAT}
          />
        </JumboTabs>
      </div>

      {/* Scrollable content — tab-dependent */}
      <div style={scrollable}>
        {loading && <LoadingCenter />}

        {!loading && error && (
          <ErrorBlock
            title="加载失败"
            description={error}
            style={{ padding: "24px 0" }}
          />
        )}

        {/* ── 总览 tab ── */}
        {!loading && !error && activeTab === TAB_OVERVIEW && (
          <>
            {/* AI summary */}
            <div
              style={{
                margin: "12px 12px 0",
                background: APP.surface,
                border: `0.5px solid ${APP.border}`,
                borderRadius: RADIUS.md,
                padding: 14,
              }}
            >
              <div style={{
                display: "flex", alignItems: "center",
                marginBottom: 6,
              }}>
                <span style={{
                  fontSize: FONT.xs, fontWeight: 600, color: APP.primary,
                  letterSpacing: 0.5,
                }}>
                  AI 摘要
                </span>
                {aiSummaryAge && (
                  <span style={{
                    marginLeft: "auto", fontSize: FONT.xs, color: APP.text4,
                  }}>
                    {aiSummaryAge}
                  </span>
                )}
                <span
                  onClick={handleRefreshSummary}
                  aria-label="刷新 AI 摘要"
                  style={{
                    marginLeft: aiSummaryAge ? 8 : "auto",
                    padding: 4,
                    cursor: refreshingSummary ? "default" : "pointer",
                    color: APP.text4,
                    display: "inline-flex",
                    alignItems: "center",
                    opacity: refreshingSummary ? 0.5 : 1,
                  }}
                >
                  {refreshingSummary
                    ? <SpinLoading color="primary" style={{ "--size": "14px" }} />
                    : <RedoOutline style={{ fontSize: 14 }} />}
                </span>
              </div>
              <div style={{ fontSize: FONT.base, color: APP.text1, lineHeight: 1.6 }}>
                {aiSummary || "暂无摘要"}
              </div>
            </div>

            {/* Clinical context */}
            {hasClinical && (
              <div
                style={{
                  margin: "12px 12px 0",
                  background: APP.surface,
                  border: `0.5px solid ${APP.border}`,
                  borderRadius: RADIUS.md,
                  overflow: "hidden",
                }}
              >
                <div style={{
                  padding: "10px 14px 6px", fontSize: FONT.sm, color: APP.text4,
                }}>
                  临床资料
                </div>
                {CLINICAL_FIELDS.filter((f) => clinical[f.key]).map((f, i, arr) => (
                  <div
                    key={f.key}
                    style={{
                      display: "flex",
                      padding: "8px 14px",
                      borderTop: i === 0 ? "none" : `0.5px solid ${APP.border}`,
                      fontSize: FONT.sm,
                    }}
                  >
                    <span style={{ color: APP.text4, width: 56, flexShrink: 0 }}>
                      {f.label}
                    </span>
                    <span
                      style={{
                        flex: 1,
                        color: f.danger ? APP.danger : APP.text1,
                        fontWeight: f.danger ? 500 : 400,
                        lineHeight: 1.5,
                      }}
                    >
                      {f.danger ? `⚠ ${clinical[f.key]}` : clinical[f.key]}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Attention */}
            {hasAttention && (
              <div style={{ marginTop: 12 }}>
                <AttentionCard
                  pendingReviewCount={pendingReviewCount}
                  draftCount={draftCount}
                  onPendingClick={goToPendingReview}
                  onDraftClick={goToChat}
                />
              </div>
            )}

            <div style={{ height: 24 }} />
          </>
        )}

        {/* ── 病历 tab ── */}
        {!loading && !error && activeTab === TAB_RECORDS && (
          <>
            {records.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "48px 16px",
                  fontSize: FONT.main,
                  color: APP.text4,
                }}
              >
                暂无病历
              </div>
            ) : (
              <div>
                {records.map((record) => (
                  <RecordCard
                    key={record.id}
                    record={record}
                    onViewFull={() => goToRecord(record)}
                  />
                ))}
              </div>
            )}
            <div style={{ height: 24 }} />
          </>
        )}

        {/* ── 聊天 tab — rendered inline ── */}
        {!loading && !error && activeTab === TAB_CHAT && (
          <PatientChatPage patientId={patientId} embedded />
        )}
      </div>
    </div>
  );
}
