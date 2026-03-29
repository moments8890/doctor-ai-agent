/**
 * 患者详情面板：可折叠个人信息、带计数的病历标签页、置顶操作栏。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, Stack, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import { useApi } from "../../../api/ApiContext";
import { generateQRToken } from "../../../api";
import QRDialog from "../../../components/QRDialog";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { RECORD_TAB_GROUPS } from "../constants";
import RecordCard, { formatRelativeDate } from "../../../components/RecordCard";
import MessageTimeline from "../../../components/MessageTimeline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExportSelectorDialog from "../../../components/ExportSelectorDialog";
import ConfirmDialog from "../../../components/ConfirmDialog";
import ReplyCard from "../../../components/doctor/ReplyCard";
import { TYPE, ICON, COLOR } from "../../../theme";

/* ── helpers ── */

function maskPhone(phone) {
  if (!phone || phone.length < 7) return phone || "—";
  return phone.slice(0, 3) + "****" + phone.slice(-4);
}

function maskIdNumber(id) {
  if (!id || id.length < 8) return id || "—";
  return id.slice(0, 4) + "****" + id.slice(-4);
}

function computeRecordStats(records) {
  const medical = ["visit", "dictation", "import", "surgery", "referral"];
  let visitCount = 0, labCount = 0, imagingCount = 0, lastDate = null;
  for (const r of records) {
    if (medical.includes(r.record_type)) visitCount++;
    else if (r.record_type === "lab") labCount++;
    else if (r.record_type === "imaging") imagingCount++;
    const d = r.created_at;
    if (d && (!lastDate || d > lastDate)) lastDate = d;
  }
  const lastVisit = lastDate ? new Date(lastDate) : null;
  const lastVisitStr = lastVisit ? `${String(lastVisit.getMonth() + 1).padStart(2, "0")}-${String(lastVisit.getDate()).padStart(2, "0")}` : "—";
  return { visitCount, labCount, imagingCount, lastVisitStr };
}

/* ── sub-components ── */

function EmptyPatientPlaceholder() {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "text.secondary", gap: 1.5 }}>
      <PeopleOutlineIcon sx={{ fontSize: ICON.display, opacity: 0.3 }} />
      <Typography color="text.secondary">← 请在左侧选择患者</Typography>
    </Box>
  );
}

function DeletePatientDialog({ open, patientName, deleting, onConfirm, onClose }) {
  return (
    <ConfirmDialog
      open={open}
      onClose={onClose}
      onCancel={onClose}
      onConfirm={onConfirm}
      title="删除患者"
      message={`确定删除「${patientName}」？\n所有病历和任务将一并删除，无法恢复。`}
      cancelLabel="保留"
      confirmLabel="确认删除"
      confirmTone="danger"
      confirmLoading={deleting}
      confirmLoadingLabel="删除中…"
    />
  );
}

function PatientActionBar({ exportingPdf, exportingReport, onExportPdf, onExportReport, onDeleteOpen, onQRCode }) {
  return (
    <Stack direction="row" spacing={2} sx={{ pt: 0.5, borderTop: "0.5px solid #f0f0f0" }} alignItems="center">
      <Box onClick={onDeleteOpen}
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer", color: "#FA5151", fontSize: TYPE.secondary.fontSize, "&:active": { opacity: 0.6 } }}>
        <DeleteOutlineIcon sx={{ fontSize: ICON.sm }} />
        删除患者
      </Box>
      <Box sx={{ flex: 1 }} />
      <Box onClick={onQRCode}
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer", color: "#e8833a", fontSize: TYPE.secondary.fontSize, "&:active": { opacity: 0.6 } }}>
        <QrCode2OutlinedIcon sx={{ fontSize: ICON.sm }} />
        二维码
      </Box>
      <Box onClick={!exportingPdf && !exportingReport ? onExportPdf : undefined}
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: exportingPdf ? "default" : "pointer", color: exportingPdf ? "#ccc" : "#07C160", fontSize: TYPE.secondary.fontSize }}>
        {exportingPdf ? <CircularProgress size={12} sx={{ color: "#ccc" }} /> : <FileDownloadOutlinedIcon sx={{ fontSize: ICON.sm }} />}
        导出PDF
      </Box>
      <Box onClick={!exportingPdf && !exportingReport ? onExportReport : undefined}
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: exportingReport ? "default" : "pointer", color: exportingReport ? "#ccc" : "#5b9bd5", fontSize: TYPE.secondary.fontSize }}>
        {exportingReport ? <CircularProgress size={12} sx={{ color: "#ccc" }} /> : <FileDownloadOutlinedIcon sx={{ fontSize: ICON.sm }} />}
        门诊报告
      </Box>
    </Stack>
  );
}

/* ── CollapsibleProfile ── */

function formatActivityDate(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return null;
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function CollapsibleProfile({ patient, age, records, expanded, onToggle, exportingPdf, exportingReport, onExportPdf, onExportReport, onDeleteOpen, onQRCode }) {
  const genderStr = patient.gender ? { male: "男", female: "女" }[patient.gender] || patient.gender : null;
  const stats = computeRecordStats(records);
  const activityStr = formatActivityDate(patient.last_activity_at) || stats.lastVisitStr;

  if (!expanded) {
    const summaryParts = [
      genderStr,
      age ? `${age}岁` : null,
      `门诊${stats.visitCount}`,
      `最近${activityStr}`,
    ].filter(Boolean).join(" · ");

    return (
      <Box sx={{ bgcolor: "#fff", px: 2.5, pt: 2, pb: 1.5, mb: 0.8 }}>
        <Box onClick={onToggle} sx={{ display: "flex", alignItems: "center", cursor: "pointer", mb: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
              <Typography sx={{ fontWeight: 700, fontSize: TYPE.action.fontSize }}>{patient.name}</Typography>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>{summaryParts}</Typography>
            </Box>
          </Box>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#07C160", flexShrink: 0, ml: 1 }}>展开 ▾</Typography>
        </Box>
      </Box>
    );
  }

  /* expanded */
  const createdStr = patient.created_at ? new Date(patient.created_at).toLocaleDateString("zh-CN") : "—";
  const birthStr = patient.year_of_birth ? `${patient.year_of_birth}年` : "—";

  return (
    <Box sx={{ bgcolor: "#fff", px: 2.5, pt: 2, pb: 1.5, mb: 0.8 }}>
      {/* Header row — clickable to collapse */}
      <Box onClick={onToggle} sx={{ display: "flex", alignItems: "center", cursor: "pointer", mb: 1.2 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 700, fontSize: TYPE.title.fontSize }}>{patient.name}</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", mt: 0.2 }}>
            {[genderStr, age ? `${age}岁` : null].filter(Boolean).join(" · ")}
          </Typography>
        </Box>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#07C160", flexShrink: 0, ml: 1 }}>收起 ▴</Typography>
      </Box>

      {/* Stats row */}
      <Box sx={{ display: "flex", gap: 2, mb: 1.2 }}>
        {[
          { label: "门诊", value: stats.visitCount },
          { label: "检验", value: stats.labCount },
          { label: "影像", value: stats.imagingCount },
          { label: "最近活动", value: activityStr },
        ].map((s) => (
          <Typography key={s.label} sx={{ fontSize: TYPE.caption.fontSize, color: "#666" }}>
            {s.label} <Box component="span" sx={{ fontWeight: 600, color: "#333" }}>{s.value}</Box>
          </Typography>
        ))}
      </Box>

      {/* Demographics grid */}
      <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", mb: 1.2, fontSize: TYPE.caption.fontSize, color: "#666" }}>
        <Box>电话 <Box component="span" sx={{ color: "#333" }}>{maskPhone(patient.phone)}</Box></Box>
        <Box>出生 <Box component="span" sx={{ color: "#333" }}>{birthStr}</Box></Box>
        <Box>身份证 <Box component="span" sx={{ color: "#333" }}>{maskIdNumber(patient.id_number)}</Box></Box>
        <Box>建档 <Box component="span" sx={{ color: "#333" }}>{createdStr}</Box></Box>
      </Box>

      {/* Action bar */}
      <PatientActionBar
        exportingPdf={exportingPdf} exportingReport={exportingReport}
        onExportPdf={onExportPdf} onExportReport={onExportReport} onDeleteOpen={onDeleteOpen}
        onQRCode={onQRCode}
      />
    </Box>
  );
}

/* ── RecordTabs ── */

import FilterBar from "../../../components/FilterBar";

function RecordTabs({ activeTab, onChange, records }) {
  const counts = {};
  RECORD_TAB_GROUPS.forEach((g) => {
    counts[g.key] = g.types ? records.filter((r) => g.types.includes(r.record_type)).length : records.length;
  });

  return <FilterBar items={RECORD_TAB_GROUPS} active={activeTab} counts={counts} onChange={onChange} />;
}

/* ── StickyTopBar ── */

function StickyTopBar({ patient, isMobile, onStartInterview, onExportOpen }) {
  const navigate = useAppNavigate();
  return (
    <Box sx={{
      position: "sticky", top: 0, zIndex: 2,
      display: "flex", alignItems: "center", height: 48,
      px: 1.5, bgcolor: "#fff", borderBottom: "0.5px solid #e5e5e5",
    }}>
      {isMobile && (
        <Box onClick={() => navigate("/doctor/patients")}
          sx={{ display: "flex", alignItems: "center", cursor: "pointer", color: "#07C160", pr: 1, py: 1 }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, color: "#07C160" }}>←</Typography>
        </Box>
      )}
      <Typography sx={{ fontWeight: 700, fontSize: TYPE.action.fontSize, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {patient.name}
      </Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexShrink: 0 }}>
        <Box onClick={onStartInterview}
          sx={{ fontSize: TYPE.secondary.fontSize, color: "#07C160", cursor: "pointer", "&:active": { opacity: 0.6 } }}>
          新建病历
        </Box>
        <Box onClick={onStartInterview}
          sx={{ fontSize: TYPE.secondary.fontSize, color: "#07C160", cursor: "pointer", "&:active": { opacity: 0.6 } }}>
          问诊
        </Box>
        <Box onClick={onExportOpen}
          sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", cursor: "pointer", "&:active": { opacity: 0.6 } }}>
          导出
        </Box>
      </Box>
    </Box>
  );
}

/* ── RecordListSection ── */

function PendingReviewRow({ record, onClick }) {
  const RECORD_TYPE_LABEL = {
    visit: "门诊记录", dictation: "语音记录", import: "导入记录", interview_summary: "预问诊记录",
    lab: "检验", imaging: "影像", surgery: "手术", referral: "转诊",
  };
  const date = formatRelativeDate(record.created_at);
  const preview = record.structured?.chief_complaint || record.content || "（无记录内容）";
  return (
    <Box onClick={onClick} sx={{ borderBottom: "1px solid #f2f2f2", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1.3 }}>
        <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: COLOR.warning, flexShrink: 0, mt: 0.7, mr: 1.4 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, mb: 0.3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, flexWrap: "wrap" }}>
              {record.record_type && (
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.warning, fontWeight: 600 }}>
                  {RECORD_TYPE_LABEL[record.record_type] || record.record_type}
                </Typography>
              )}
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.warning, bgcolor: COLOR.warningLight, px: 0.8, py: 0.1, borderRadius: 0.5, fontWeight: 500 }}>
                待审核
              </Typography>
              {(Array.isArray(record.tags) ? record.tags : []).map((tag, i) => (
                <Typography key={i} sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, bgcolor: COLOR.surfaceAlt, px: 0.6, borderRadius: 0.5 }}>
                  {tag}
                </Typography>
              ))}
            </Box>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#bbb", flexShrink: 0 }}>{date}</Typography>
          </Box>
          <Typography sx={{
            fontSize: TYPE.secondary.fontSize, color: preview !== "（无记录内容）" ? "text.primary" : "#bbb",
            overflow: "hidden", display: "-webkit-box",
            WebkitLineClamp: 2, WebkitBoxOrient: "vertical", whiteSpace: "pre-wrap",
          }}>
            {preview}
          </Typography>
        </Box>
        <Box sx={{ ml: 1, flexShrink: 0, display: "flex", alignItems: "center", mt: 0.2 }}>
          <ChevronRightIcon sx={{ fontSize: ICON.md, color: COLOR.warning }} />
        </Box>
      </Box>
    </Box>
  );
}

function RecordListSection({ loading, error, records, filteredRecords, activeTab, setActiveTab, setRecords, doctorId, load, highlightRecordId }) {
  const navigate = useAppNavigate();
  return (
    <Box sx={{ bgcolor: "#fff", mb: 0.8 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5, pb: 0.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.heading.fontSize, color: "#333" }}>病历记录</Typography>
        {loading && <CircularProgress size={14} sx={{ color: "#07C160" }} />}
      </Box>
      <RecordTabs activeTab={activeTab} onChange={setActiveTab} records={records} />
      {error && <Box sx={{ px: 2, pb: 1 }}><Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert></Box>}
      {!loading && !error && records.length === 0 && <Box sx={{ px: 2, pb: 2, pt: 1 }}><Typography variant="body2" color="text.secondary">暂无病历。</Typography></Box>}
      {filteredRecords.length === 0 && records.length > 0 ? (
        <Box sx={{ px: 2, pb: 2, pt: 1 }}><Typography variant="body2" color="text.secondary">该类型暂无病历。</Typography></Box>
      ) : (
        filteredRecords.map((r) => (
          r.status === "pending_review" ? (
            <PendingReviewRow key={r.id} record={r} onClick={() => navigate(`/doctor/review/${r.id}`)} />
          ) : (
            <RecordCard key={r.id} record={r} doctorId={doctorId}
              defaultExpanded={highlightRecordId === r.id ? true : undefined}
              onUpdated={(updated) => setRecords((prev) => prev.map((x) => x.id === updated.id ? { ...x, ...updated } : x))}
              onDeleted={(id) => setRecords((prev) => prev.filter((x) => x.id !== id))} />
          )
        ))
      )}
    </Box>
  );
}

/* ── hook ── */

function usePatientDetailState({ patient, doctorId, onDeleted }) {
  const navigate = useAppNavigate();
  const { getRecords, exportPatientPdf, exportOutpatientReport, deletePatient } = useApi();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportingReport, setExportingReport] = useState(false);
  const [exportError, setExportError] = useState("");
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    if (!patient) return; setLoading(true); setError("");
    getRecords({ doctorId, patientId: patient.id, limit: 100 }).then((d) => setRecords(d.items || [])).catch((e) => setError(e.message || "加载失败")).finally(() => setLoading(false));
  }, [patient?.id, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  async function handleDelete() { setDeleting(true); try { await deletePatient(patient.id, doctorId); setDeleteConfirmOpen(false); if (onDeleted) { onDeleted(patient.id); return; } navigate("/doctor/patients"); } catch (e) { setError(e.message || "删除失败"); setDeleteConfirmOpen(false); } finally { setDeleting(false); } }
  async function handleExportPdf(opts) { setExportingPdf(true); setExportError(""); try { await exportPatientPdf(patient.id, doctorId, opts); } catch (e) { setExportError(e.message || "导出失败"); } finally { setExportingPdf(false); } }
  async function handleExportReport() { setExportingReport(true); setExportError(""); try { await exportOutpatientReport(patient.id, doctorId); } catch (e) { setExportError(e.message || "生成失败，请确认已有病历记录"); } finally { setExportingReport(false); } }

  return { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, deleteConfirmOpen, setDeleteConfirmOpen, deleting, load, handleDelete, handleExportPdf, handleExportReport };
}

/* ── DraftReplyCard — now delegates to ReplyCard ── */

/* ── PatientChatPage ── */

function PatientChatPage({ patientId, doctorId }) {
  const { getPatientChat, replyToPatient, fetchDrafts } = useApi();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(() => new URLSearchParams(window.location.search).get("expand") === "messages");
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [drafts, setDrafts] = useState([]);
  const [draftsLoading, setDraftsLoading] = useState(false);

  useEffect(() => {
    if (!patientId) return;
    setLoading(true);
    getPatientChat(patientId)
      .then(data => setMessages(data.messages || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [patientId]);

  // Fetch drafts for this patient
  useEffect(() => {
    if (!patientId || !doctorId) return;
    setDraftsLoading(true);
    fetchDrafts(doctorId)
      .then(data => {
        // API returns { pending_messages: [...] } or a flat array
        const allDrafts = Array.isArray(data) ? data : (data?.pending_messages || []);
        const patientDrafts = allDrafts.filter(d => String(d.patient_id) === String(patientId));
        setDrafts(patientDrafts);
      })
      .catch(() => setDrafts([]))
      .finally(() => setDraftsLoading(false));
  }, [patientId, doctorId]);

  async function handleReply() {
    const text = replyText.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await replyToPatient(patientId, text);
      setReplyText("");
      // Refresh messages
      const data = await getPatientChat(patientId);
      setMessages(data.messages || []);
    } catch {}
    finally { setSending(false); }
  }

  function handleDraftSent(draftId) {
    setDrafts(prev => prev.filter(d => d.id !== draftId));
    // Refresh messages to show the sent reply
    getPatientChat(patientId)
      .then(data => setMessages(data.messages || []))
      .catch(() => {});
  }

  // Show only escalated/unhandled messages in triage summary
  const escalated = messages.filter(m => m.source === "patient" || (m.ai_handled === false));
  const hasMessages = messages.length > 0;
  const hasDrafts = drafts.length > 0;

  const msgSectionRef = useRef(null);
  useEffect(() => {
    if (expanded && new URLSearchParams(window.location.search).get("expand") === "messages") {
      setTimeout(() => msgSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 300);
    }
  }, [expanded]);

  return (
    <Box ref={msgSectionRef} sx={{ bgcolor: "#fff", mb: 0.8 }}>
      {/* Header: 患者消息 (N) + expand toggle */}
      <Box
        onClick={() => (hasMessages || hasDrafts) ? setExpanded(v => !v) : undefined}
        sx={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          px: 2, pt: 1.5, pb: 0.5,
          cursor: (hasMessages || hasDrafts) ? "pointer" : "default",
          "&:active": (hasMessages || hasDrafts) ? { opacity: 0.6 } : {},
        }}
      >
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.heading.fontSize, color: COLOR.text2 }}>
          患者消息 {hasMessages && <Box component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, fontWeight: 400 }}>({messages.length})</Box>}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          {(loading || draftsLoading) && <CircularProgress size={14} sx={{ color: COLOR.success }} />}
          {(hasMessages || hasDrafts) && (
            <Typography sx={{ fontSize: 12, color: COLOR.text4 }}>{expanded ? "▴" : "▾"}</Typography>
          )}
        </Box>
      </Box>

      {!loading && !hasMessages && !hasDrafts && (
        <Box sx={{ px: 2, pb: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>暂无患者消息</Typography>
        </Box>
      )}

      {!loading && (hasMessages || hasDrafts) && (
        <>
          {/* Message timeline */}
          {hasMessages && expanded && (
            <Box sx={{ px: 2, mb: 0.5 }}>
              <MessageTimeline messages={messages} maxHeight={300} />
            </Box>
          )}

          {/* Draft reply cards — outside green box */}
          {hasDrafts && (
            <Box sx={{ mx: 1.5, mb: 0.5 }}>
              {drafts.map(d => (
                <ReplyCard key={d.id} item={d} mode="inline" doctorId={doctorId} onSent={handleDraftSent} />
              ))}
            </Box>
          )}

          {/* Reply input — outside green box */}
          {expanded && (
            <Box sx={{ display: "flex", gap: 1, px: 2, py: 1 }}>
              <Box component="input" value={replyText} onChange={e => setReplyText(e.target.value)}
                placeholder="回复患者…"
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleReply(); } }}
                style={{
                  flex: 1, border: "1px solid #e0e0e0", borderRadius: 6,
                  padding: "6px 10px", fontSize: 13, fontFamily: "inherit",
                  outline: "none",
                }}
              />
              <Button size="small" disabled={!replyText.trim() || sending}
                onClick={handleReply}
                sx={{ color: COLOR.success, minWidth: "auto", fontSize: TYPE.secondary.fontSize }}>
                {sending ? <CircularProgress size={14} /> : "发送"}
              </Button>
            </Box>
          )}
        </>
      )}
    </Box>
  );
}

/* ── main component ── */

export default function PatientDetail({ patient, doctorId, onDeleted, onStartInterview, triggerExport, onTriggerExportConsumed }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [expanded, setExpanded] = useState(!isMobile);
  const [activeTab, setActiveTab] = useState("");
  const [exportOpen, setExportOpen] = useState(false);

  // Allow parent to trigger export dialog
  useEffect(() => {
    if (triggerExport) { setExportOpen(true); onTriggerExportConsumed?.(); }
  }, [triggerExport]); // eslint-disable-line react-hooks/exhaustive-deps

  const { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, deleteConfirmOpen, setDeleteConfirmOpen, deleting, load, handleDelete, handleExportPdf, handleExportReport } = usePatientDetailState({ patient, doctorId, onDeleted });

  /* QR code state */
  const [qrOpen, setQrOpen] = useState(false);
  const [qrUrl, setQrUrl] = useState("");
  const [qrError, setQrError] = useState("");
  const [qrLoading, setQrLoading] = useState(false);

  async function handlePatientQR() {
    setQrLoading(true); setQrError(""); setQrOpen(true);
    try { const data = await generateQRToken("patient", doctorId, patient.id); setQrUrl(data.url); }
    catch (e) { setQrUrl(""); setQrError(e.message || "生成失败"); }
    finally { setQrLoading(false); }
  }

  if (!patient) return <EmptyPatientPlaceholder />;

  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;

  /* Filter records by active tab */
  const activeGroup = RECORD_TAB_GROUPS.find((g) => g.key === activeTab);
  // Sort: actionable items first (pending_review, interview_active), then newest first
  const sortedRecords = [...records].sort((a, b) => {
    const actionable = (r) => r.status === "pending_review" || r.status === "interview_active" ? 1 : 0;
    const diff = actionable(b) - actionable(a);
    if (diff !== 0) return diff;
    return (b.created_at || "").localeCompare(a.created_at || "");
  });
  const filteredRecords = activeGroup?.types ? sortedRecords.filter((r) => activeGroup.types.includes(r.record_type)) : sortedRecords;

  return (
    <Box sx={{ overflowY: "auto", height: "100%", bgcolor: "#ededed" }}>
      <CollapsibleProfile
        patient={patient} age={age} records={records} expanded={expanded} onToggle={() => setExpanded((v) => !v)}
        exportingPdf={exportingPdf} exportingReport={exportingReport}
        onExportPdf={() => setExportOpen(true)}
        onExportReport={handleExportReport} onDeleteOpen={() => setDeleteConfirmOpen(true)}
        onQRCode={handlePatientQR}
      />
      {exportError && <Typography variant="caption" color="error.main" sx={{ display: "block", px: 2.5, mt: 0.5 }}>{exportError}</Typography>}
      <DeletePatientDialog open={deleteConfirmOpen} patientName={patient.name} deleting={deleting} onConfirm={handleDelete} onClose={() => setDeleteConfirmOpen(false)} />
      <ExportSelectorDialog open={exportOpen} onClose={() => setExportOpen(false)} patientId={patient.id} patientName={patient.name}
        onExport={(opts) => { setExportOpen(false); handleExportPdf(opts); }} />
      <RecordListSection loading={loading} error={error} records={records} filteredRecords={filteredRecords} activeTab={activeTab} setActiveTab={setActiveTab} setRecords={setRecords} doctorId={doctorId} load={load}
        highlightRecordId={(() => { const p = new URLSearchParams(window.location.search).get("record"); return p ? parseInt(p) : null; })()} />
      <PatientChatPage patientId={patient.id} doctorId={doctorId} />
      <QRDialog open={qrOpen} onClose={() => setQrOpen(false)} title="患者二维码"
        name={patient.name} url={qrUrl} loading={qrLoading} error={qrError}
        onRegenerate={handlePatientQR} />
      <Box sx={{ height: 24 }} />
    </Box>
  );
}
