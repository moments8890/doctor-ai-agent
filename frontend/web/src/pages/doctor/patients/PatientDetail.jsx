/**
 * 患者详情面板：可折叠个人信息、带计数的病历标签页、置顶操作栏。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, ClickAwayListener, Collapse, Stack, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { generateQRToken } from "../../../api";
import QRDialog from "../../../components/QRDialog";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { RECORD_TAB_GROUPS } from "../constants";
import { formatRelativeDate } from "../../../components/RecordCard";
import MessageTimeline from "../../../components/MessageTimeline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExportSelectorDialog from "../../../components/ExportSelectorDialog";
import ConfirmDialog from "../../../components/ConfirmDialog";
import SheetDialog from "../../../components/SheetDialog";
import DialogFooter from "../../../components/DialogFooter";
import EmptyState from "../../../components/EmptyState";
import MsgAvatar from "../../../components/MsgAvatar";
import NameAvatar from "../../../components/NameAvatar";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import { TYPE, ICON, COLOR, RADIUS } from "../../../theme";
import { dp } from "../../../utils/doctorBasePath";
import HelpTip from "../../../components/HelpTip";
import { PAGE_HELP } from "../constants";

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

function OverflowDropdown({ open, onClose, onExportPdf, onExportReport, onQRCode, onDeleteOpen }) {
  if (!open) return null;
  const menuItems = [
    { label: "导出PDF", onClick: () => { onClose(); onExportPdf(); } },
    { label: "门诊报告", onClick: () => { onClose(); onExportReport(); } },
    { label: "患者二维码", onClick: () => { onClose(); onQRCode(); } },
    { label: "删除患者", onClick: () => { onClose(); onDeleteOpen(); }, danger: true },
  ];
  return (
    <ClickAwayListener onClickAway={onClose}>
      <Box sx={{
        position: "absolute", right: 0, top: "100%", mt: 0.5, zIndex: 100,
        bgcolor: COLOR.white, borderRadius: RADIUS.md, overflow: "hidden",
        minWidth: 140, border: `0.5px solid ${COLOR.border}`,
        boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
      }}>
        {menuItems.map((item, i) => (
          <Box key={item.label} onClick={item.onClick}
            sx={{
              py: 1.5, px: 2, cursor: "pointer",
              fontSize: TYPE.secondary.fontSize, color: item.danger ? COLOR.danger : COLOR.text1,
              borderBottom: i < menuItems.length - 1 ? `0.5px solid ${COLOR.borderLight}` : "none",
              "&:active": { bgcolor: COLOR.surface },
            }}>
            {item.label}
          </Box>
        ))}
      </Box>
    </ClickAwayListener>
  );
}


function AttentionCard({ pendingReviewCount, draftCount, onPendingClick, onDraftClick }) {
  if (!pendingReviewCount && !draftCount) return null;
  return (
    <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, mb: 1, px: 2, py: 1 }}>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 600, color: COLOR.warning, letterSpacing: 0.3, mb: 1, display: "flex", alignItems: "center", gap: 0.5 }}>
        ⚡ 需要你处理
      </Typography>
      {pendingReviewCount > 0 && (
        <Box onClick={onPendingClick} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, cursor: "pointer", borderBottom: draftCount ? `0.5px solid ${COLOR.borderLight}` : "none", "&:active": { opacity: 0.6 } }}>
          <Box sx={{ width: 32, height: 32, borderRadius: "6px", bgcolor: COLOR.warningLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <AssignmentOutlinedIcon sx={{ fontSize: 16, color: COLOR.warning }} />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 500 }}>{pendingReviewCount} 条病历待审核</Typography>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 0.5 }}>点击查看并确认</Typography>
          </Box>
          <Typography sx={{ fontSize: 14, color: COLOR.text4 }}>›</Typography>
        </Box>
      )}
      {draftCount > 0 && (
        <Box onClick={onDraftClick} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
          <Box sx={{ width: 32, height: 32, borderRadius: "6px", bgcolor: COLOR.primaryLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <MailOutlineIcon sx={{ fontSize: 16, color: COLOR.primary }} />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 500 }}>{draftCount} 条消息待回复</Typography>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 0.5 }}>AI已起草 · 待你确认</Typography>
          </Box>
          <Typography sx={{ fontSize: 14, color: COLOR.text4 }}>›</Typography>
        </Box>
      )}
    </Box>
  );
}

/* ── CollapsibleProfile ── */

function formatActivityDate(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return null;
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function CollapsibleProfile({ patient, age, records, expanded, onToggle, overflowOpen, onOverflowOpen, onOverflowClose, overflowActions, onStartInterview }) {
  const genderStr = patient.gender ? { male: "男", female: "女" }[patient.gender] || patient.gender : null;
  const stats = computeRecordStats(records);
  const activityStr = formatActivityDate(patient.last_activity_at) || stats.lastVisitStr;
  const summaryParts = [
    genderStr, age ? `${age}岁` : null, `门诊${stats.visitCount}`, `最近${activityStr}`,
  ].filter(Boolean).join(" · ");

  const createdStr = patient.created_at ? new Date(patient.created_at).toLocaleDateString("zh-CN") : "—";
  const birthStr = patient.year_of_birth ? `${patient.year_of_birth}年` : "—";

  return (
    <Box sx={{ bgcolor: COLOR.white, px: 2.5, pt: 1.5, pb: 1, mb: 0, position: "relative" }}>
      {/* Header row — always same height regardless of expanded state */}
      <Box sx={{ display: "flex", alignItems: "center" }}>
        <Box onClick={onToggle} sx={{ flex: 1, minWidth: 0, display: "flex", alignItems: "baseline", gap: 1, cursor: "pointer" }}>
          <Typography sx={{ fontWeight: 700, fontSize: TYPE.action.fontSize }}>{patient.name}</Typography>
          {!expanded && (
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {summaryParts}
            </Typography>
          )}
        </Box>
        {expanded ? (
          <Typography onClick={(e) => { e.stopPropagation(); onStartInterview?.(); }}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, fontWeight: 500, flexShrink: 0, ml: 1, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
            新建门诊
          </Typography>
        ) : (
          <Typography onClick={onToggle}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, flexShrink: 0, ml: 1, cursor: "pointer" }}>
            展开 ▾
          </Typography>
        )}
        <Box onClick={(e) => { e.stopPropagation(); onOverflowOpen(); }} sx={{ ml: 1.5, cursor: "pointer", display: "flex", alignItems: "center", position: "relative", "&:active": { opacity: 0.5 } }}>
          <MoreHorizIcon sx={{ fontSize: ICON.lg, color: COLOR.text4 }} />
          <OverflowDropdown open={overflowOpen} onClose={onOverflowClose} {...overflowActions} />
        </Box>
      </Box>

      {/* Expanded details — all below the fixed header row */}
      <Collapse in={expanded}>
        <Box sx={{ mt: 1 }}>
          <Box sx={{ display: "flex", gap: 2, mb: 1 }}>
            {[
              { label: "门诊", value: stats.visitCount },
              { label: "检验", value: stats.labCount },
              { label: "影像", value: stats.imagingCount },
              { label: "最近", value: activityStr },
            ].map((s) => (
              <Typography key={s.label} sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3 }}>
                {s.label} <Box component="span" sx={{ fontWeight: 600, color: COLOR.text2 }}>{s.value}</Box>
              </Typography>
            ))}
          </Box>
          <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: TYPE.caption.fontSize, color: COLOR.text3 }}>
            <Box>电话 <Box component="span" sx={{ color: COLOR.text2 }}>{maskPhone(patient.phone)}</Box></Box>
            <Box>出生 <Box component="span" sx={{ color: COLOR.text2 }}>{birthStr}</Box></Box>
            <Box>身份证 <Box component="span" sx={{ color: COLOR.text2 }}>{maskIdNumber(patient.id_number)}</Box></Box>
            <Box>建档 <Box component="span" sx={{ color: COLOR.text2 }}>{createdStr}</Box></Box>
          </Box>
        </Box>
      </Collapse>
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
      px: 1.5, bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}`,
    }}>
      {isMobile && (
        <Box onClick={() => navigate(dp("patients"))}
          sx={{ display: "flex", alignItems: "center", cursor: "pointer", color: COLOR.primary, pr: 1, py: 1 }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.primary }}>←</Typography>
        </Box>
      )}
      <Typography sx={{ fontWeight: 700, fontSize: TYPE.action.fontSize, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {patient.name}
      </Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexShrink: 0 }}>
        <Box onClick={onStartInterview}
          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
          新建病历
        </Box>
        <Box onClick={onStartInterview}
          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
          问诊
        </Box>
        <Box onClick={onExportOpen}
          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
          导出
        </Box>
      </Box>
    </Box>
  );
}

/* ── RecordListSection ── */

const RECORD_DOT_COLORS = {
  visit: COLOR.primary, dictation: COLOR.recordDoc, import: COLOR.recordDoc,
  lab: COLOR.accent, imaging: COLOR.accent, surgery: COLOR.danger,
  referral: COLOR.primary, interview_summary: COLOR.primary,
};

const RECORD_TYPE_LABEL_MAP = {
  visit: "门诊", dictation: "口述", import: "导入", interview_summary: "预问诊",
  lab: "检验", imaging: "影像", surgery: "手术", referral: "转诊",
};

function RecordRow({ record, onClick }) {
  const isPending = record.status === "pending_review";
  const dotColor = isPending ? COLOR.warning : (RECORD_DOT_COLORS[record.record_type] || COLOR.text4);
  const date = formatRelativeDate(record.created_at);
  const preview = record.structured?.chief_complaint || record.content || "（无记录内容）";
  const typeLabel = RECORD_TYPE_LABEL_MAP[record.record_type] || record.record_type;
  return (
    <Box onClick={onClick} sx={{
      borderBottom: `0.5px solid ${COLOR.borderLight}`, cursor: "pointer",
      ...(isPending ? { bgcolor: COLOR.warningLight } : {}),
      "&:active": { opacity: 0.8 },
    }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1 }}>
        <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: dotColor, flexShrink: 0, mt: 0.5, mr: 1.5 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: dotColor, fontWeight: 600 }}>{typeLabel}</Typography>
            {isPending && <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.warning, fontWeight: 500 }}>待审核</Typography>}
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, ml: "auto", flexShrink: 0 }}>{date} ›</Typography>
          </Box>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {preview}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}

function RecordListSection({ loading, error, records, filteredRecords, activeTab, setActiveTab, setRecords, doctorId, load, highlightRecordId }) {
  const navigate = useAppNavigate();
  return (
    <Box sx={{ bgcolor: COLOR.white, mb: 1 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5, pb: 0.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.heading.fontSize, color: COLOR.text2 }}>病历记录</Typography>
        {loading && <CircularProgress size={14} sx={{ color: COLOR.primary }} />}
      </Box>
      <RecordTabs activeTab={activeTab} onChange={setActiveTab} records={records} />
      {error && <Box sx={{ px: 2, pb: 1 }}><Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert></Box>}
      {!loading && !error && records.length === 0 && <EmptyState title="暂无病历" subtitle="点击右上角「门诊」新建病历" />}
      {filteredRecords.length === 0 && records.length > 0 ? (
        <EmptyState title="该类型暂无病历" />
      ) : (
        filteredRecords.map((r) => (
          <RecordRow key={r.id} record={r} onClick={() => {
            if (r.status === "pending_review") navigate(`${dp("review")}/${r.id}`);
            else navigate(`${dp("patients")}/${r.patient_id || ""}?view=record&record=${r.id}`, { replace: true });
          }} />
        ))
      )}
    </Box>
  );
}

/* ── hook ── */

function usePatientDetailState({ patient, doctorId, onDeleted }) {
  const navigate = useAppNavigate();
  const queryClient = useQueryClient();
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
  async function handleDelete() { setDeleting(true); try { await deletePatient(patient.id, doctorId); queryClient.invalidateQueries({ queryKey: QK.patients(doctorId) }); setDeleteConfirmOpen(false); if (onDeleted) { onDeleted(patient.id); return; } navigate(dp("patients")); } catch (e) { setError(e.message || "删除失败"); setDeleteConfirmOpen(false); } finally { setDeleting(false); } }
  async function handleExportPdf(opts) { setExportingPdf(true); setExportError(""); try { await exportPatientPdf(patient.id, doctorId, opts); } catch (e) { setExportError(e.message || "导出失败"); } finally { setExportingPdf(false); } }
  async function handleExportReport() { setExportingReport(true); setExportError(""); try { await exportOutpatientReport(patient.id, doctorId); } catch (e) { setExportError(e.message || "生成失败，请确认已有病历记录"); } finally { setExportingReport(false); } }

  return { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, deleteConfirmOpen, setDeleteConfirmOpen, deleting, load, handleDelete, handleExportPdf, handleExportReport };
}

/* ── BubbleChatView ──
 *
 * Full-screen chat subpage (WeChat-style bubbles + reply input + AI-draft
 * confirm sheet + teach-as-rule prompt). Extracted from PatientChatPage so
 * its local state (`replyText`, `editingDraft`, `confirmDraft`, `teachState`,
 * scroll refs, etc.) lives inside a component that is always rendered when
 * present — avoiding a Rules-of-Hooks violation when conditional hook calls
 * were inlined under `if (bubbleView)`.
 *
 * Data flows in via props (`messages`, `drafts`, `draftByMsgId`, ...) from
 * the parent PatientChatPage which owns fetching. Mutations call API
 * functions from useApi() and notify the parent through `refreshMessages`
 * / `refreshDrafts` for cache invalidation.
 */
function BubbleChatView({
  patientId, doctorId, patientName,
  messages, drafts, loading,
  draftByMsgId, matchedCount, activeDraft,
  refreshMessages, refreshDrafts,
}) {
  const { replyToPatient, editDraft, sendDraft, getDraftConfirmation, createRuleFromEdit } = useApi();
  const navigate = useAppNavigate();
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [editingDraft, setEditingDraft] = useState(null);
  const [confirmDraft, setConfirmDraft] = useState(null);
  const [confirmData, setConfirmData] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [teachState, setTeachState] = useState(null);
  const [savingRule, setSavingRule] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const hasScrolledRef = useRef(false);
  const highlightRefs = useRef({});

  // Parse ?highlight_draft_id=N on mount. Used to deep-link from knowledge
  // citation rows (KnowledgeDetailSubpage) → the specific reply.
  const highlightDraftId = (() => {
    try { return new URLSearchParams(window.location.search).get("highlight_draft_id"); }
    catch { return null; }
  })();
  const [flashMsgId, setFlashMsgId] = useState(null);
  const highlightAppliedRef = useRef(false);

  // Initial mount: if highlight_draft_id is set, scroll to that message
  // and flash it briefly. Otherwise scroll to bottom (normal behavior).
  useEffect(() => {
    if (!messages.length) return;
    if (highlightDraftId && !highlightAppliedRef.current) {
      const draft = drafts.find((d) => String(d.id) === String(highlightDraftId));
      const targetMsgId = draft?.source_message_id;
      const el = targetMsgId != null ? highlightRefs.current[targetMsgId] : null;
      if (el) {
        el.scrollIntoView({ behavior: "auto", block: "center" });
        setFlashMsgId(targetMsgId);
        highlightAppliedRef.current = true;
        setTimeout(() => setFlashMsgId(null), 2400);
        return;
      }
    }
    if (!bottomRef.current) return;
    bottomRef.current.scrollIntoView({ behavior: hasScrolledRef.current ? "smooth" : "auto" });
    hasScrolledRef.current = true;
  }, [messages, drafts, highlightDraftId]);

  async function handleDraftEdit(nextText, draft) {
    if (!draft?.id) return;
    const result = await editDraft(draft.id, doctorId, nextText);
    await refreshDrafts?.();
    if (result?.teach_prompt && result?.edit_id) {
      setTeachState({ editId: result.edit_id });
    }
  }

  async function handleDraftSend(draft) {
    if (!draft?.id) return;
    try {
      const data = await getDraftConfirmation(draft.id, doctorId);
      setConfirmDraft(draft);
      setConfirmData(data);
    } catch {
      await sendDraft(draft.id, doctorId);
      await Promise.allSettled([refreshMessages?.(), refreshDrafts?.()]);
    }
  }

  async function handleSendReply() {
    const text = replyText.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      if (editingDraft) {
        await handleDraftEdit(text, editingDraft);
        await handleDraftSend({ ...editingDraft, draft_text: text });
        setEditingDraft(null);
      } else {
        await replyToPatient(patientId, text);
      }
      setReplyText("");
      await Promise.allSettled([refreshMessages?.(), refreshDrafts?.()]);
    } finally { setSending(false); }
  }

  function handleEditDraft(draft) {
    setEditingDraft(draft);
    setReplyText(draft.draft_text || draft.content || "");
    setTimeout(() => inputRef.current?.focus(), 100);
  }

  function handleReplyKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSendReply();
    }
  }

  async function handleConfirmedSend() {
    if (!confirmDraft?.id) return;
    setConfirming(true);
    try {
      await sendDraft(confirmDraft.id, doctorId);
      setConfirmDraft(null);
      setConfirmData(null);
      await Promise.allSettled([refreshMessages?.(), refreshDrafts?.()]);
    } finally { setConfirming(false); }
  }

  async function handleSaveAsRule() {
    if (!teachState?.editId) return;
    setSavingRule(true);
    try {
      await createRuleFromEdit(teachState.editId, doctorId);
    } finally {
      setSavingRule(false);
      setTeachState(null);
    }
  }

  return (
    <>
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {/* Messages area */}
        <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: 1.5, bgcolor: COLOR.surfaceAlt }}>
          {loading && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress size={20} sx={{ color: COLOR.text4 }} />
            </Box>
          )}
          {!loading && messages.length === 0 && !activeDraft && (
            <Box sx={{ textAlign: "center", py: 6 }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>暂无消息</Typography>
            </Box>
          )}
          {messages.map((msg, idx) => {
            const isPatient = msg.role === "patient" || msg.sender_type === "patient" || msg.source === "patient";
            const isDoctor = msg.role === "doctor" || msg.sender_type === "doctor" || msg.source === "doctor";
            const isAI = !isPatient && !isDoctor;
            const time = msg.created_at ? new Date(msg.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "";
            const inlineDraft = draftByMsgId[msg.id];
            const isFlash = flashMsgId != null && String(flashMsgId) === String(msg.id);
            return (
              <Box
                key={idx}
                ref={(el) => { if (el) highlightRefs.current[msg.id] = el; }}
                sx={{
                  borderRadius: RADIUS.md,
                  transition: "background-color 2s ease-out",
                  bgcolor: isFlash ? `${COLOR.warning}22` : "transparent",
                  py: isFlash ? 0.5 : 0,
                }}
              >
                {/* Message bubble */}
                <Box sx={{ display: "flex", flexDirection: isPatient ? "row" : "row-reverse", alignItems: "flex-end", gap: 1, px: 1.5 }}>
                  {isPatient ? (
                    <NameAvatar name={patientName || "患者"} size={36} />
                  ) : (
                    <MsgAvatar isUser={isDoctor} size={36} />
                  )}
                  <Box sx={{ maxWidth: "72%", display: "flex", flexDirection: "column", alignItems: isPatient ? "flex-start" : "flex-end" }}>
                    <Box sx={{
                      px: 1.5, py: 1,
                      borderRadius: isPatient ? `${RADIUS.sm} ${RADIUS.sm} ${RADIUS.sm} 0` : `${RADIUS.sm} ${RADIUS.sm} 0 ${RADIUS.sm}`,
                      bgcolor: isPatient ? COLOR.white : (isDoctor ? COLOR.wechatGreen : COLOR.white),
                      fontSize: TYPE.body.fontSize, whiteSpace: "pre-wrap", lineHeight: 1.7, color: COLOR.text1,
                    }}>
                      {isAI && <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 500, mb: 0.5 }}>AI</Typography>}
                      {msg.content || msg.text || ""}
                    </Box>
                    <Typography sx={{ mt: 0.5, px: 0.5, fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>{time}</Typography>
                  </Box>
                </Box>
                {/* Inline AI draft for this message */}
                {inlineDraft && (inlineDraft.draft_text || inlineDraft.content) && (
                  <Box sx={{ display: "flex", flexDirection: "row-reverse", alignItems: "flex-end", gap: 1, px: 1.5, mt: 1.5 }}>
                    <MsgAvatar isUser={false} size={36} />
                    <Box sx={{ maxWidth: "78%" }}>
                      <Box sx={{ bgcolor: COLOR.primaryLight, border: `1px solid ${COLOR.primary}30`, borderRadius: RADIUS.md, px: 2, py: 1.5 }}>
                        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 600, mb: 0.5 }}>
                          AI起草回复 · 待你确认
                        </Typography>
                        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                          {inlineDraft.draft_text || inlineDraft.content || ""}
                        </Typography>
                        {inlineDraft.cited_rules?.length > 0 && (
                          <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                            {inlineDraft.cited_rules.map((rule) => (
                              <Box key={rule.id} component="span"
                                onClick={() => rule.id && navigate(`${dp("settings/knowledge")}/${rule.id}`)}
                                sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger, bgcolor: COLOR.dangerLight, px: 1, py: 0.5, borderRadius: RADIUS.sm, cursor: "pointer" }}>
                                引用: {rule.title}
                              </Box>
                            ))}
                          </Box>
                        )}
                        <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2, mt: 1.5, pt: 1, borderTop: `0.5px solid ${COLOR.primary}20` }}>
                          <Typography onClick={() => handleEditDraft(inlineDraft)}
                            sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.5 } }}>
                            修改
                          </Typography>
                          <Typography onClick={() => handleDraftSend(inlineDraft)}
                            sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 600, cursor: "pointer", "&:active": { opacity: 0.5 } }}>
                            确认发送 ›
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  </Box>
                )}
              </Box>
            );
          })}

          {/* No draft hint — when last inbound message has no AI draft */}
          {matchedCount === 0 && messages.length > 0 && messages[messages.length - 1]?.direction === "inbound" && (
            <Box sx={{ display: "flex", justifyContent: "center", px: 1.5, py: 1 }}>
              <Box sx={{
                bgcolor: COLOR.surfaceAlt, border: `1px dashed ${COLOR.border}`,
                borderRadius: RADIUS.md, px: 2, py: 1.2, maxWidth: "85%", textAlign: "center",
              }}>
                <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
                  AI未能起草回复（知识库中无匹配规则），请直接回复患者
                </Typography>
              </Box>
            </Box>
          )}

          <div ref={bottomRef} />
        </Box>

        {/* Reply input bar */}
        <Box sx={{ borderTop: `1px solid ${COLOR.border}`, bgcolor: COLOR.surface }}>
          {editingDraft && (
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 1.5, py: 0.5, bgcolor: COLOR.primaryLight, borderBottom: `0.5px solid ${COLOR.primary}30` }}>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 500 }}>正在编辑AI草稿</Typography>
              <Typography onClick={() => { setEditingDraft(null); setReplyText(""); }}
                sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, cursor: "pointer" }}>取消</Typography>
            </Box>
          )}
          <Box sx={{ px: 1, py: 1, display: "flex", alignItems: "flex-end", gap: 0.5 }}>
            <Box sx={{ flex: 1, bgcolor: COLOR.white, borderRadius: RADIUS.sm, px: 1.5, py: 1, minHeight: 36, maxHeight: 120, overflowY: "auto" }}>
              <Box component="textarea" ref={inputRef} value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                onKeyDown={handleReplyKeyDown}
                disabled={sending}
                rows={editingDraft ? 3 : 1}
                placeholder={editingDraft ? "编辑回复内容..." : "直接回复患者..."}
                sx={{ width: "100%", border: "none", outline: "none", fontSize: TYPE.body.fontSize, fontFamily: "inherit", bgcolor: "transparent", p: 0, resize: "none", lineHeight: 1.7 }}
              />
            </Box>
            <Box onClick={handleSendReply}
              sx={{
                width: 36, height: 36, borderRadius: "50%",
                bgcolor: replyText.trim() ? COLOR.primary : COLOR.text4,
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: replyText.trim() ? "pointer" : "default", flexShrink: 0, mb: 0.5,
                "&:active": replyText.trim() ? { bgcolor: COLOR.primaryHover } : {},
              }}>
              <SendOutlinedIcon sx={{ fontSize: 16, color: COLOR.white }} />
            </Box>
          </Box>
        </Box>
      </Box>
      <SheetDialog
        open={!!confirmDraft}
        onClose={() => { setConfirmDraft(null); setConfirmData(null); }}
        title="确认发送回复"
        desktopMaxWidth={400}
        footer={
          <DialogFooter
            onCancel={() => { setConfirmDraft(null); setConfirmData(null); }}
            cancelLabel="取消"
            onConfirm={handleConfirmedSend}
            confirmLabel="发送"
            confirmLoading={confirming}
            confirmLoadingLabel="发送中…"
          />
        }
      >
        {confirmData && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            <Box sx={{ bgcolor: COLOR.surface, borderRadius: RADIUS.md, p: 1.5 }}>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mb: 0.5 }}>患者消息</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text1, lineHeight: 1.6 }}>
                {confirmData.patient_message || "—"}
              </Typography>
            </Box>
            <Box sx={{ bgcolor: COLOR.primaryLight, border: `1px solid ${COLOR.primary}30`, borderRadius: RADIUS.md, p: 1.5 }}>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 600, mb: 0.5 }}>回复内容</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text1, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                {confirmData.draft_text || ""}
              </Typography>
              {confirmData.cited_rules?.length > 0 && (
                <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                  {confirmData.cited_rules.map((rule) => (
                    <Box key={rule.id} component="span"
                      sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger, bgcolor: COLOR.dangerLight, px: 1, py: 0.5, borderRadius: RADIUS.sm }}>
                      引用: {rule.title}
                    </Box>
                  ))}
                </Box>
              )}
            </Box>
            {confirmData.ai_disclosure && (
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, textAlign: "center" }}>
                {confirmData.ai_disclosure}
              </Typography>
            )}
          </Box>
        )}
      </SheetDialog>
      <ConfirmDialog
        open={!!teachState}
        onClose={() => setTeachState(null)}
        onCancel={() => setTeachState(null)}
        onConfirm={handleSaveAsRule}
        title="保存为知识规则"
        message="你的修改有价值！是否保存为知识规则，帮助 AI 更好地理解你的风格？"
        cancelLabel="跳过"
        confirmLabel="保存"
        confirmLoading={savingRule}
        confirmLoadingLabel="保存中…"
      />
    </>
  );
}

/* ── PatientChatPage ── */

export function PatientChatPage({ patientId, doctorId, onDraftCount, onMessageCount, hidden = false, bubbleView = false, patientName }) {
  const { getPatientChat, replyToPatient, fetchDrafts, editDraft, sendDraft } = useApi();
  const navigate = useAppNavigate();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState([]);
  const [draftsLoading, setDraftsLoading] = useState(false);
  const [open, setOpen] = useState(true);

  const refreshMessages = useCallback(async () => {
    if (!patientId) return;
    const data = await getPatientChat(patientId, doctorId);
    const nextMessages = Array.isArray(data?.messages) ? data.messages : [];
    nextMessages.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
    setMessages(nextMessages);
  }, [patientId, doctorId, getPatientChat]);

  const refreshDrafts = useCallback(async () => {
    if (!patientId || !doctorId) return;
    const data = await fetchDrafts(doctorId, { patientId });
    const allDrafts = Array.isArray(data) ? data : (data?.pending_messages || []);
    // Only keep actual AI drafts (not "undrafted" placeholders)
    const actualDrafts = allDrafts.filter(d => d.type === "draft");
    actualDrafts.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
    setDrafts(actualDrafts);
  }, [patientId, doctorId, fetchDrafts]);

  useEffect(() => {
    if (!patientId) return;
    setLoading(true);
    refreshMessages()
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [patientId, refreshMessages]);

  useEffect(() => {
    if (!patientId || !doctorId) return;
    setDraftsLoading(true);
    refreshDrafts()
      .catch(() => setDrafts([]))
      .finally(() => setDraftsLoading(false));
  }, [patientId, doctorId, refreshDrafts]);

  // Timeline-view handlers. Bubble view owns its own richer handlers (with
  // confirm-send sheet and teach-prompt flow) inside BubbleChatView so hooks
  // aren't conditionally called.
  async function handleDraftEdit(nextText, draft) {
    if (!draft?.id) return;
    await editDraft(draft.id, doctorId, nextText);
    setDrafts((prev) => prev.map((item) => (
      item.id === draft.id ? { ...item, draft_text: nextText } : item
    )));
  }

  async function handleDraftSend(draft) {
    if (!draft?.id) return;
    await sendDraft(draft.id, doctorId);
    setDrafts((prev) => prev.filter((item) => item.id !== draft.id));
    await refreshMessages();
  }

  async function handleManualReply(nextText) {
    const text = nextText.trim();
    if (!text) return;
    await replyToPatient(patientId, text);
    // Draft stays visible — only removed when doctor explicitly sends or dismisses it
    await Promise.allSettled([refreshMessages(), refreshDrafts()]);
  }

  // Build draft lookup by source_message_id for inline timeline display
  const messageIdSet = new Set(messages.map(m => m.id));
  const pendingDrafts = drafts.filter(d => d.status !== "sent" && (d.draft_text || d.content));
  const draftByMsgId = {};
  let matchedCount = 0;
  for (const d of pendingDrafts) {
    if (d.source_message_id && messageIdSet.has(d.source_message_id)) {
      draftByMsgId[d.source_message_id] = d;
      matchedCount++;
    }
  }
  // Don't show orphan drafts — they're stale from old conversations
  const activeDraft = matchedCount > 0 ? pendingDrafts[0] : null; // for backward-compat (counts, hints)
  const timelineCount = messages.length + matchedCount;
  const hasContent = timelineCount > 0;

  // Report counts to parent
  useEffect(() => { onDraftCount?.(drafts.filter((d) => d.status !== "sent").length); }, [drafts.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { onMessageCount?.(messages.length + drafts.filter((d) => d.status !== "sent").length); }, [messages.length, drafts.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Hidden mode: only fetch draft count, don't render UI
  if (hidden) return null;

  /* ── Bubble view (dedicated chat subpage) ── */
  if (bubbleView) {
    return (
      <BubbleChatView
        patientId={patientId}
        doctorId={doctorId}
        patientName={patientName}
        messages={messages}
        drafts={drafts}
        loading={loading}
        draftByMsgId={draftByMsgId}
        matchedCount={matchedCount}
        activeDraft={activeDraft}
        refreshMessages={refreshMessages}
        refreshDrafts={refreshDrafts}
      />
    );
  }

  /* ── Timeline view (inline in patient detail — legacy, kept for fallback) ── */
  return (
    <Box sx={{ bgcolor: COLOR.white, mb: 1 }}>
      <Box
        onClick={() => setOpen((prev) => !prev)}
        sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5, pb: 1, cursor: "pointer" }}
      >
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.heading.fontSize, color: COLOR.text2 }}>
          患者消息
          {timelineCount > 0 && (
            <Box component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, fontWeight: 400, ml: 0.5 }}>
              ({timelineCount})
            </Box>
          )}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {(loading || draftsLoading) && <CircularProgress size={14} sx={{ color: COLOR.success }} />}
          <ExpandMoreIcon
            sx={{
              fontSize: ICON.md,
              color: COLOR.text4,
              transform: open ? "rotate(0deg)" : "rotate(-90deg)",
              transition: "transform 0.16s ease",
            }}
          />
        </Box>
      </Box>

      <Collapse in={open}>
        <Box sx={{ px: 2, pb: 1.5, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          {!loading && !hasContent ? (
            <Box sx={{ pt: 1 }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>暂无患者消息</Typography>
            </Box>
          ) : (
            <MessageTimeline
              messages={messages}
              maxHeight={400}
              draft={activeDraft ? {
                id: activeDraft.id,
                status: activeDraft.status,
                text: activeDraft.draft_text || activeDraft.content || "",
                citedRules: activeDraft.cited_rules || [],
                rule_cited: activeDraft.rule_cited || (activeDraft.cited_rules?.[0]?.title) || null,
              } : undefined}
              onCitationClick={(rule) => {
                if (!rule?.id) return;
                navigate(`${dp("settings/knowledge")}/${rule.id}`);
              }}
              onSaveDraftEdit={handleDraftEdit}
              onSendDraft={handleDraftSend}
              onSendManualReply={handleManualReply}
            />
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

/* ── main component ── */

export default function PatientDetail({ patient, doctorId, onDeleted, onStartInterview, triggerExport, onTriggerExportConsumed }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [expanded, setExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [draftCount, setDraftCount] = useState(0);
  const [messageCount, setMessageCount] = useState(0);
  const chatRef = useCallback((node) => {
    if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // Allow parent to trigger export dialog
  useEffect(() => {
    if (triggerExport) { setExportOpen(true); onTriggerExportConsumed?.(); }
  }, [triggerExport]); // eslint-disable-line react-hooks/exhaustive-deps

  const { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, deleteConfirmOpen, setDeleteConfirmOpen, deleting, load, handleDelete, handleExportPdf, handleExportReport } = usePatientDetailState({ patient, doctorId, onDeleted });
  const navigate = useAppNavigate();

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
  const pendingReviewCount = records.filter((r) => r.status === "pending_review").length;

  /* Filter records by active tab */
  const activeGroup = RECORD_TAB_GROUPS.find((g) => g.key === activeTab);
  const sortedRecords = [...records].sort((a, b) => {
    const actionable = (r) => r.status === "pending_review" || r.status === "interview_active" ? 1 : 0;
    const diff = actionable(b) - actionable(a);
    if (diff !== 0) return diff;
    return (b.created_at || "").localeCompare(a.created_at || "");
  });
  const filteredRecords = activeGroup?.types ? sortedRecords.filter((r) => activeGroup.types.includes(r.record_type)) : sortedRecords;

  // Navigate to dedicated chat subpage (push so back returns to patient detail)
  const goToChat = () => {
    navigate(`${dp("patients")}/${patient.id}?view=chat`);
  };

  // Navigate to first pending review record
  const goToPendingReview = () => {
    const pending = records.find((r) => r.status === "pending_review");
    if (pending) navigate(`${dp("review")}/${pending.id}`);
  };

  return (
    <Box sx={{ overflowY: "auto", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      {/* Profile — collapsed by default */}
      <CollapsibleProfile
        patient={patient} age={age} records={records} expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        overflowOpen={overflowOpen} onOverflowOpen={() => setOverflowOpen(true)} onOverflowClose={() => setOverflowOpen(false)}
        overflowActions={{ onExportPdf: () => setExportOpen(true), onExportReport: handleExportReport, onQRCode: handlePatientQR, onDeleteOpen: () => setDeleteConfirmOpen(true) }}
        onStartInterview={onStartInterview}
      />

      {/* Attention card — pending reviews + drafts */}
      <AttentionCard
        pendingReviewCount={pendingReviewCount} draftCount={draftCount}
        onPendingClick={goToPendingReview} onDraftClick={goToChat}
      />

      {exportError && <Typography variant="caption" color="error.main" sx={{ display: "block", px: 2.5, mt: 0.5 }}>{exportError}</Typography>}
      <DeletePatientDialog open={deleteConfirmOpen} patientName={patient.name} deleting={deleting} onConfirm={handleDelete} onClose={() => setDeleteConfirmOpen(false)} />
      <ExportSelectorDialog open={exportOpen} onClose={() => setExportOpen(false)} patientId={patient.id} patientName={patient.name}
        onExport={(opts) => { setExportOpen(false); handleExportPdf(opts); }} />
      {/* Chat nav — always visible, links to dedicated chat subpage */}
      <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, mb: 1 }}>
        <Box onClick={goToChat} sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5, cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}>
          <Box sx={{ width: 36, height: 36, borderRadius: "6px", bgcolor: COLOR.accentLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <MailOutlineIcon sx={{ fontSize: 18, color: COLOR.accent }} />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500 }}>
              患者消息
              {messageCount > 0 && <Box component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, fontWeight: 400, ml: 0.5 }}>({messageCount})</Box>}
            </Typography>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 0.5 }}>
              {draftCount > 0 ? `${draftCount} 条待回复` : "查看聊天记录"}
            </Typography>
          </Box>
          {draftCount > 0 && (
            <Box sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 600, color: COLOR.white, bgcolor: COLOR.danger, borderRadius: "8px", px: 1, minWidth: 16, textAlign: "center", lineHeight: "18px" }}>
              {draftCount}
            </Box>
          )}
          <Typography sx={{ fontSize: 16, color: COLOR.text4 }}>›</Typography>
        </Box>
      </Box>

      <RecordListSection loading={loading} error={error} records={records} filteredRecords={filteredRecords} activeTab={activeTab} setActiveTab={setActiveTab} setRecords={setRecords} doctorId={doctorId} load={load}
        highlightRecordId={(() => { const p = new URLSearchParams(window.location.search).get("record"); return p ? parseInt(p) : null; })()} />

      <PatientChatPage patientId={patient.id} doctorId={doctorId} onDraftCount={setDraftCount} onMessageCount={setMessageCount} hidden />

      <QRDialog open={qrOpen} onClose={() => setQrOpen(false)} title="患者二维码"
        name={patient.name} url={qrUrl} loading={qrLoading} error={qrError}
        onRegenerate={handlePatientQR} />
      <Box sx={{ height: 24 }} />
    </Box>
  );
}
