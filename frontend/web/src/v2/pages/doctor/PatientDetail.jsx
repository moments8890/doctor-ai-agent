/**
 * @route /doctor/patients/:patientId
 *
 * v2 PatientDetail — records-first patient detail page.
 * Displays patient profile, attention card, chat link, and record list.
 * Chat/reply view is a separate subpage at ?view=chat.
 *
 * antd-mobile only. No MUI, no src/components, no src/theme.js.
 */
import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { SafeArea, NavBar,
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
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import EventNoteOutlinedIcon from "@mui/icons-material/EventNoteOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import BoltOutlinedIcon from "@mui/icons-material/BoltOutlined";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import PatientChatPage from "./PatientChatPage";
import { QRCodeSVG } from "qrcode.react";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { useDoctorStore } from "../../../store/doctorStore";
import { useMarkPatientViewed } from "../../../lib/doctorQueries";
import { recordView } from "../../../hooks/useLastViewed";
import { formatAge, relativeTime } from "../../../utils/time";
import { APP, FONT, RADIUS, ICON, CATEGORY_COLOR } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { LoadingCenter, NameAvatar } from "../../components";
import { STRUCTURED_FIELD_LABELS } from "../../constants";
import SubpageBackHome from "../../components/SubpageBackHome";

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
  intake_summary: "问诊总结",
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
  { key: "diagnosis",       label: "诊断", Icon: MedicalServicesOutlinedIcon },
  { key: "treatment_plan",  label: "用药", Icon: MedicationOutlinedIcon },
  { key: "allergy_history", label: "过敏", danger: true, Icon: WarningAmberOutlinedIcon },
  { key: "past_history",    label: "既往", Icon: EventNoteOutlinedIcon },
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
  if (status === "intake_active") {
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

// AI-summary age indicator. Defers to the unified relativeTime helper for
// the bucket label, then appends the "更新" qualifier so it reads as
// "刚刚更新" / "今天更新" / "3天前更新" / etc.
function formatSummaryAge(ts) {
  if (!ts) return null;
  const label = relativeTime(ts);
  return label ? `${label}更新` : null;
}

// ── Patient profile helpers ───────────────────────────────────────────

// ── Attention callouts ────────────────────────────────────────────────
// Two independent cards — one amber for pending AI suggestions, one green for
// drafts waiting confirmation. Each renders only when its count is > 0.

function CalloutCard({ Icon, iconColor, iconBg, tint, title, description, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        margin: "8px 12px 0",
        background: tint,
        borderRadius: RADIUS.lg,
        padding: "12px 14px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        cursor: "pointer",
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: RADIUS.md,
          background: iconBg,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon sx={{ fontSize: ICON.sm, color: iconColor }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
          {title}
        </div>
        <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
          {description}
        </div>
      </div>
      <ChevronRightIcon sx={{ fontSize: ICON.sm, color: APP.text4, flexShrink: 0 }} />
    </div>
  );
}

function AttentionCard({ pendingReviewCount, draftCount, onPendingClick, onDraftClick }) {
  if (!pendingReviewCount && !draftCount) return null;
  return (
    <>
      {pendingReviewCount > 0 && (
        <CalloutCard
          Icon={BoltOutlinedIcon}
          iconColor={APP.warning}
          iconBg={APP.surface}
          tint={APP.warningLight}
          title="需要你处理"
          description="请尽快查看并确认AI建议"
          onClick={onPendingClick}
        />
      )}
      {draftCount > 0 && (
        <CalloutCard
          Icon={MailOutlineIcon}
          iconColor={APP.primary}
          iconBg={APP.surface}
          tint={APP.primaryLight}
          title={`${draftCount} 条消息待回复`}
          description="AI已起草 · 待你确认"
          onClick={onDraftClick}
        />
      )}
    </>
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
            <ChatBubbleOutlineIcon sx={{ fontSize: FONT.lg, color: APP.primary }} />
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

// ── Append-only field entries view ────────────────────────────────────

// The 7 history fields tracked by FieldEntryDB, in reading order.
const HISTORY_FIELDS = [
  { key: "chief_complaint",   label: "主诉" },
  { key: "present_illness",   label: "现病史" },
  { key: "past_history",      label: "既往史" },
  { key: "allergy_history",   label: "过敏史" },
  { key: "personal_history",  label: "个人史" },
  { key: "marital_reproductive", label: "婚育史" },
  { key: "family_history",    label: "家族史" },
];

// Per-field provenance badges removed 2026-04-26 — every field in a confirmed
// medical record was either approved by the patient (new flow) or recorded by
// the doctor (legacy). The doctor reads the values; provenance taxonomy
// (本次采集 / 已沿用并确认 / 本次更新 / 历史档案) added noise without
// actionable signal. carry_forward_meta + fields_updated_this_visit columns
// on medical_records are still populated for future audit/analytics use.

// Detect the post-redesign per-field shape returned by GET
// /api/manage/records/{id}/entries: each value is an object with `text`,
// `carry_forward`, `updated_this_visit` keys. Legacy shape was an array of
// {text, created_at} entries — the legacy branch below handles that for
// older records.
function isProvenanceEntry(v) {
  return (
    v != null
    && typeof v === "object"
    && !Array.isArray(v)
    && typeof v.text === "string"
  );
}

/**
 * Renders the per-field history view for a single record.
 *
 * Two backend shapes supported:
 *   - NEW (intake redesign):
 *       entries[field] = { text, carry_forward: {...}|null, updated_this_visit }
 *     Renders single text with a provenance badge next to the label.
 *   - LEGACY (FieldEntryDB):
 *       entries[field] = [{ text, created_at }, ...]
 *     Renders chronological multi-entry view (initial + supplements).
 *   - EMPTY: falls back to flat structured-column rendering.
 */
function FieldEntriesSection({ entries, structured }) {
  // Filter out the underscore-prefixed record-level meta key so it doesn't
  // leak into the field iteration. We don't render the meta anywhere now.
  const hasFieldData = entries && Object.keys(entries).some((k) => k !== "_record_meta");

  if (!hasFieldData) {
    // Legacy fallback: render from structured columns
    const legacyFields = HISTORY_FIELDS.filter(({ key }) => structured?.[key]);
    if (legacyFields.length === 0) return null;
    return (
      <>
        {legacyFields.map(({ key, label }, i) => (
          <div
            key={key}
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
              {label}
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
              {structured[key]}
            </span>
          </div>
        ))}
      </>
    );
  }

  // Filter to fields that have content under either shape.
  const renderedFields = HISTORY_FIELDS.filter(({ key }) => {
    const v = entries[key];
    if (isProvenanceEntry(v)) return Boolean(v.text && v.text.trim());
    return Array.isArray(v) && v.length > 0;
  });
  if (renderedFields.length === 0) return null;

  return (
    <>
      {renderedFields.map(({ key, label }, fi) => {
        const v = entries[key];

        // ── New per-field provenance shape ─────────────────────────
        if (isProvenanceEntry(v)) {
          return (
            <div
              key={key}
              style={{
                display: "flex",
                gap: 10,
                padding: "6px 0",
                borderTop: fi === 0 ? "none" : `0.5px solid ${APP.borderLight}`,
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
                {label}
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
                {v.text}
              </span>
            </div>
          );
        }

        // ── Legacy chronological multi-entry view ──────────────────
        const fieldEntries = v;
        const isMulti = fieldEntries.length > 1;

        // Single entry: use left-label / right-value layout (matches the
        // structured-field rows + provenance branch above).
        if (!isMulti) {
          return (
            <div
              key={key}
              style={{
                display: "flex",
                gap: 10,
                padding: "6px 0",
                borderTop: fi === 0 ? "none" : `0.5px solid ${APP.borderLight}`,
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
                {label}
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
                {fieldEntries[0].text}
              </span>
            </div>
          );
        }

        // Multi-entry: keep stacked layout because each entry has its own
        // meta line (初次描述 / 之后补充 + relative time).
        return (
          <div
            key={key}
            style={{
              padding: "8px 0 4px",
              borderTop: fi === 0 ? "none" : `0.5px solid ${APP.borderLight}`,
            }}
          >
            <div
              style={{
                fontSize: FONT.sm,
                color: APP.text4,
                fontWeight: 500,
                marginBottom: 6,
              }}
            >
              {label}
            </div>

            {fieldEntries.map((entry, idx) => (
              <div key={idx} style={{ marginBottom: idx < fieldEntries.length - 1 ? 8 : 0 }}>
                <div
                  style={{
                    fontSize: FONT.xs,
                    color: APP.text4,
                    marginBottom: 2,
                  }}
                >
                  {idx === 0 ? "初次描述" : "之后补充"} · {relativeTime(entry.created_at)}
                </div>
                <div
                  style={{
                    fontSize: FONT.sm,
                    color: APP.text2,
                    whiteSpace: "pre-wrap",
                    lineHeight: 1.6,
                    paddingLeft: 8,
                    borderLeft: `2px solid ${idx === 0 ? APP.border : APP.primary}`,
                  }}
                >
                  {entry.text}
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </>
  );
}

/**
 * Hook to lazily fetch FieldEntryDB entries for a record.
 * Fetches once on mount; returns {} while loading or on error (graceful degradation).
 */
function useRecordEntries(api, doctorId, recordId, skip) {
  const [entries, setEntries] = useState(null); // null = loading, {} = no entries
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (skip || fetchedRef.current) return;
    fetchedRef.current = true;
    api.getRecordEntries(doctorId, recordId)
      .then((data) => setEntries(data || {}))
      .catch(() => setEntries({}));
  }, [api, doctorId, recordId, skip]); // eslint-disable-line react-hooks/exhaustive-deps

  return entries;
}

// ── Record row ────────────────────────────────────────────────────────

function RecordCard({ record, onViewFull, api, doctorId }) {
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

  // Fetch field entries for the chronological history view.
  // Skip when the record has no body (navigates directly, no expansion needed).
  const entries = useRecordEntries(api, doctorId, record.id, !hasBody);

  // No body → tap navigates straight to full detail (no empty expand)
  if (!hasBody) {
    return (
      <div
        onClick={() => onViewFull?.()}
        style={{
          background: APP.surface,
          borderRadius: RADIUS.lg,
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
        borderRadius: RADIUS.lg,
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
            {/* Chronological field entries view (FieldEntryDB) with legacy fallback */}
            {entries !== null && (
              <FieldEntriesSection entries={entries} structured={structured} />
            )}
            {/* Non-history structured fields (diagnosis, treatment_plan, etc.) */}
            {filled.filter((k) => !HISTORY_FIELDS.some((h) => h.key === k)).map((k) => (
              <div
                key={k}
                style={{
                  display: "flex",
                  gap: 10,
                  padding: "6px 0",
                  borderTop: `0.5px solid ${APP.borderLight}`,
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
        const resolved = found || { id: patientId, name: "患者" };
        setPatient(resolved);
        if (found) {
          recordView({
            type: "patient",
            id: found.id,
            name: found.name || "未命名",
            gender: found.gender || null,
            yearOfBirth: found.year_of_birth || null,
            lastVisitAt: found.last_activity_at || found.created_at || null,
          });
        }
      })
      .catch(() => setPatient({ id: patientId, name: "患者" }));
  }, [patientId, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── First-view tracking (drives the 新 badge) ──────────────────────
  // Fire mark-viewed only after ~2s of foregrounded dwell — Codex review
  // pushed back on "route mount = viewed" because an accidental tap or
  // 0.5s open shouldn't permanently clear the badge. Cancel on unmount or
  // when the page is hidden so a quick back-nav also doesn't fire.
  const markViewed = useMarkPatientViewed();
  useEffect(() => {
    if (!patientId || !patient || patient.first_doctor_view_at) return;
    const DWELL_MS = 2000;
    let timer = setTimeout(() => {
      markViewed.mutate(patientId);
    }, DWELL_MS);
    const onVisibility = () => {
      if (document.hidden && timer) {
        clearTimeout(timer);
        timer = null;
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [patientId, patient]); // eslint-disable-line react-hooks/exhaustive-deps

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
          r.status === "pending_review" || r.status === "intake_active" ? 1 : 0;
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

  function handleStartIntake() {
    // Route to the intake flow for an existing patient; IntakePage can
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
  const ageStr = formatAge(patient?.year_of_birth);
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
    ageStr,
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
      <SafeArea position="top" />
      <NavBar
        backArrow={<SubpageBackHome />}
        onBack={handleBack}
        right={
          <div
            onClick={() => setOverflowOpen(true)}
            style={{ padding: "4px 8px", cursor: "pointer" }}
            aria-label="更多操作"
          >
            <MoreHorizIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />
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
          paddingBottom: "var(--safe-bottom, env(safe-area-inset-bottom, 0px))",
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

      {/* Header strip — flat strip, avatar + (name over vitals) + CTA */}
      {patient && (
        <div
          style={{
            background: APP.surface,
            padding: "10px 16px",
            display: "flex",
            alignItems: "center",
            gap: 12,
            borderBottom: `0.5px solid ${APP.border}`,
            flexShrink: 0,
          }}
        >
          <NameAvatar name={patient.name} size={44} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: FONT.md,
                fontWeight: 700,
                color: APP.text1,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {patient.name || "患者"}
            </div>
            {statLine && (
              <div
                style={{
                  marginTop: 2,
                  fontSize: FONT.sm,
                  color: APP.text4,
                  lineHeight: 1.5,
                }}
              >
                {statLine}
              </div>
            )}
          </div>
          <span
            onClick={handleStartIntake}
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
            {/* AI 摘要 — white outer card wrapping a bordered inner box */}
            <div
              style={{
                margin: "8px 12px 0",
                background: APP.surface,
                borderRadius: RADIUS.lg,
                padding: "12px 14px",
              }}
            >
              <div style={{
                display: "flex", alignItems: "center", gap: 6,
                marginBottom: 8,
              }}>
                <AutoAwesomeOutlinedIcon sx={{ fontSize: ICON.sm, color: APP.primary }} />
                <span style={{
                  fontSize: FONT.md, fontWeight: 600, color: APP.primary,
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
                    : <RefreshOutlinedIcon sx={{ fontSize: ICON.xs }} />}
                </span>
              </div>
              <div
                style={{
                  background: `linear-gradient(135deg, ${APP.primaryLight} 0%, #d4f5e0 100%)`,
                  borderRadius: RADIUS.md,
                  padding: "10px 14px",
                  fontSize: FONT.base,
                  color: APP.text1,
                  lineHeight: 1.65,
                }}
              >
                {aiSummary || "暂无摘要"}
              </div>
            </div>

            {/* Clinical context — outer card with nested bordered inner card */}
            {hasClinical && (
              <div
                style={{
                  margin: "8px 12px 0",
                  background: APP.surface,
                  borderRadius: RADIUS.lg,
                  padding: "12px 12px 12px",
                }}
              >
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "0 2px 8px",
                }}>
                  <ArticleOutlinedIcon sx={{ fontSize: ICON.sm, color: APP.primary }} />
                  <span style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
                    临床资料
                  </span>
                </div>
                <div
                  style={{
                    border: `0.5px solid ${APP.border}`,
                    borderRadius: RADIUS.md,
                    overflow: "hidden",
                  }}
                >
                  {CLINICAL_FIELDS.filter((f) => clinical[f.key]).map((f, i) => {
                    const iconColor = f.danger ? APP.danger : APP.primary;
                    const iconBg = f.danger ? APP.dangerLight : APP.primaryLight;
                    return (
                      <div
                        key={f.key}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 10,
                          padding: "10px 12px",
                          borderTop: i === 0 ? "none" : `0.5px solid ${APP.borderLight}`,
                        }}
                      >
                        <div
                          style={{
                            width: 32,
                            height: 32,
                            borderRadius: RADIUS.md,
                            background: iconBg,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            flexShrink: 0,
                          }}
                        >
                          <f.Icon sx={{ fontSize: ICON.sm, color: iconColor }} />
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>
                            {f.label}
                          </div>
                          <div
                            style={{
                              marginTop: 2,
                              fontSize: FONT.sm,
                              color: f.danger ? APP.danger : APP.text2,
                              lineHeight: 1.55,
                            }}
                          >
                            {clinical[f.key]}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Attention callouts — each renders its own spacing */}
            {hasAttention && (
              <AttentionCard
                pendingReviewCount={pendingReviewCount}
                draftCount={draftCount}
                onPendingClick={goToPendingReview}
                onDraftClick={goToChat}
              />
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
              <div style={{ paddingTop: 4 }}>
                {records.map((record) => (
                  <RecordCard
                    key={record.id}
                    record={record}
                    api={api}
                    doctorId={doctorId}
                    onViewFull={() => goToRecord(record)}
                  />
                ))}
                <div
                  style={{
                    textAlign: "center",
                    padding: "16px 16px 8px",
                    fontSize: FONT.sm,
                    color: APP.text4,
                  }}
                >
                  共 {records.length} 条病历
                </div>
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
