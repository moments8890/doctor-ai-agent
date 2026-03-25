/**
 * 患者详情面板：可折叠个人信息、带计数的病历标签页、置顶操作栏。
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert, Box, Button, CircularProgress, Dialog,
  Stack, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  getRecords,
  exportPatientPdf, exportOutpatientReport, deletePatient,
  getPatientChat, replyToPatient,
} from "../../api";
import { RECORD_TAB_GROUPS } from "./constants";
import RecordCard from "./RecordCard";
import ExportSelectorDialog from "./ExportSelectorDialog";
import { TYPE, ICON, COLOR } from "../../theme";

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

function DeletePatientDialog({ open, patientName, deleting, isMobile, onConfirm, onClose }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      PaperProps={{ sx: isMobile
        ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "12px 12px 0 0", width: "100%" }
        : { borderRadius: 2, minWidth: 300 }
      }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}
    >
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize, textAlign: "center", mb: 0.8 }}>删除患者</Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", textAlign: "center", mb: 2.5, lineHeight: 1.7 }}>
          确定删除「{patientName}」？{"\n"}所有病历和任务将一并删除，无法恢复。
        </Typography>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: TYPE.action.fontSize, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!deleting ? onConfirm : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: "4px", bgcolor: "#FA5151", cursor: deleting ? "default" : "pointer", fontSize: TYPE.action.fontSize, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
            {deleting ? "删除中…" : "确认删除"}
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}

function PatientActionBar({ exportingPdf, exportingReport, onExportPdf, onExportReport, onDeleteOpen }) {
  return (
    <Stack direction="row" spacing={2} sx={{ pt: 0.5, borderTop: "0.5px solid #f0f0f0" }} alignItems="center">
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
      <Box sx={{ flex: 1 }} />
      <Box onClick={onDeleteOpen}
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer", color: "#FA5151", fontSize: TYPE.secondary.fontSize, "&:active": { opacity: 0.6 } }}>
        <DeleteOutlineIcon sx={{ fontSize: ICON.sm }} />
        删除患者
      </Box>
    </Stack>
  );
}

/* ── CollapsibleProfile ── */

function CollapsibleProfile({ patient, age, records, expanded, onToggle, exportingPdf, exportingReport, onExportPdf, onExportReport, onDeleteOpen }) {
  const genderStr = patient.gender ? { male: "男", female: "女" }[patient.gender] || patient.gender : null;
  const stats = computeRecordStats(records);

  if (!expanded) {
    const summaryParts = [
      genderStr,
      age ? `${age}岁` : null,
      `门诊${stats.visitCount}`,
      `最近${stats.lastVisitStr}`,
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
          { label: "最近就诊", value: stats.lastVisitStr },
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
      />
    </Box>
  );
}

/* ── RecordTabs ── */

function RecordTabs({ activeTab, onChange, records }) {
  function countForGroup(group) {
    if (!group.types) return records.length;
    return records.filter((r) => group.types.includes(r.record_type)).length;
  }

  return (
    <Box sx={{ display: "flex", gap: 0, px: 2, borderBottom: "0.5px solid #f0f0f0" }}>
      {RECORD_TAB_GROUPS.map((g) => {
        const active = activeTab === g.key;
        const count = countForGroup(g);
        return (
          <Box key={g.key} onClick={() => onChange(g.key)}
            sx={{
              px: 1.5, py: 1, cursor: "pointer", fontSize: TYPE.secondary.fontSize,
              color: active ? "#07C160" : "#999",
              fontWeight: active ? 600 : 400,
              borderBottom: active ? "2px solid #07C160" : "2px solid transparent",
              flexShrink: 0,
            }}>
            {g.label} {count > 0 && <Box component="span" sx={{ fontSize: TYPE.micro.fontSize }}>{count}</Box>}
          </Box>
        );
      })}
    </Box>
  );
}

/* ── StickyTopBar ── */

function StickyTopBar({ patient, isMobile, onStartInterview, onExportOpen }) {
  const navigate = useNavigate();
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

function RecordListSection({ loading, error, records, filteredRecords, activeTab, setActiveTab, setRecords, doctorId, load }) {
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
          <RecordCard key={r.id} record={r} doctorId={doctorId}
            onUpdated={(updated) => setRecords((prev) => prev.map((x) => x.id === updated.id ? { ...x, ...updated } : x))}
            onDeleted={(id) => setRecords((prev) => prev.filter((x) => x.id !== id))} />
        ))
      )}
    </Box>
  );
}

/* ── hook ── */

function usePatientDetailState({ patient, doctorId, onDeleted }) {
  const navigate = useNavigate();
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
  async function handleExportPdf() { setExportingPdf(true); setExportError(""); try { await exportPatientPdf(patient.id, doctorId); } catch (e) { setExportError(e.message || "导出失败"); } finally { setExportingPdf(false); } }
  async function handleExportReport() { setExportingReport(true); setExportError(""); try { await exportOutpatientReport(patient.id, doctorId); } catch (e) { setExportError(e.message || "生成失败，请确认已有病历记录"); } finally { setExportingReport(false); } }

  return { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, deleteConfirmOpen, setDeleteConfirmOpen, deleting, load, handleDelete, handleExportPdf, handleExportReport };
}

/* ── PatientChatSection ── */

function PatientChatSection({ patientId, doctorId }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!patientId) return;
    setLoading(true);
    getPatientChat(patientId)
      .then(data => setMessages(data.messages || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [patientId]);

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

  // Show only escalated/unhandled messages in triage summary
  const escalated = messages.filter(m => m.source === "patient" || (m.ai_handled === false));
  const hasMessages = messages.length > 0;

  return (
    <Box sx={{ bgcolor: "#fff", mb: 0.8 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5, pb: 0.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.heading.fontSize, color: COLOR.text2 }}>
          患者消息 {hasMessages && <Box component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, fontWeight: 400 }}>({messages.length})</Box>}
        </Typography>
        {loading && <CircularProgress size={14} sx={{ color: COLOR.success }} />}
      </Box>

      {!loading && !hasMessages && (
        <Box sx={{ px: 2, pb: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>暂无患者消息</Typography>
        </Box>
      )}

      {!loading && hasMessages && (
        <>
          {/* Triage summary — escalated messages only */}
          {!expanded && escalated.length > 0 && (
            <Box sx={{ px: 2, pb: 1 }}>
              {escalated.slice(-3).map(m => (
                <Box key={m.id} sx={{ py: 0.5, borderBottom: "0.5px solid #f5f5f5", display: "flex", gap: 0.8, alignItems: "baseline" }}>
                  <Box sx={{
                    width: 6, height: 6, borderRadius: "50%", flexShrink: 0, mt: 0.8,
                    bgcolor: m.triage_category === "urgent" ? COLOR.danger : (m.source === "patient" ? COLOR.accent : COLOR.success),
                  }} />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.5 }} noWrap>
                      {m.content}
                    </Typography>
                    <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                      {m.created_at ? new Date(m.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : ""}
                    </Typography>
                  </Box>
                </Box>
              ))}
            </Box>
          )}

          {/* Expand toggle */}
          <Box onClick={() => setExpanded(v => !v)}
            sx={{ px: 2, py: 0.8, cursor: "pointer", borderTop: "0.5px solid #f0f0f0" }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.success, textAlign: "center" }}>
              {expanded ? "收起对话 ▴" : `查看完整对话 (${messages.length}) ▾`}
            </Typography>
          </Box>

          {/* Full thread */}
          {expanded && (
            <Box sx={{ px: 2, pb: 1, maxHeight: 300, overflowY: "auto" }}>
              {messages.map(m => (
                <Box key={m.id} sx={{ py: 0.5, display: "flex", gap: 0.8, alignItems: "flex-start" }}>
                  <Typography sx={{
                    fontSize: TYPE.micro.fontSize, fontWeight: 500, flexShrink: 0, mt: 0.3,
                    color: m.source === "patient" ? COLOR.accent : (m.source === "doctor" ? COLOR.success : COLOR.text4),
                  }}>
                    {m.source === "patient" ? "患者" : (m.source === "doctor" ? "医生" : "AI")}
                  </Typography>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                      {m.content}
                    </Typography>
                    <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
                      {m.created_at ? new Date(m.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : ""}
                    </Typography>
                  </Box>
                </Box>
              ))}
            </Box>
          )}

          {/* Reply input */}
          {expanded && (
            <Box sx={{ display: "flex", gap: 1, px: 2, py: 1, borderTop: "0.5px solid #f0f0f0" }}>
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

  if (!patient) return <EmptyPatientPlaceholder />;

  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;

  /* Filter records by active tab */
  const activeGroup = RECORD_TAB_GROUPS.find((g) => g.key === activeTab);
  const filteredRecords = activeGroup?.types ? records.filter((r) => activeGroup.types.includes(r.record_type)) : records;

  return (
    <Box sx={{ overflowY: "auto", height: "100%", bgcolor: "#ededed" }}>
      <CollapsibleProfile
        patient={patient} age={age} records={records} expanded={expanded} onToggle={() => setExpanded((v) => !v)}
        exportingPdf={exportingPdf} exportingReport={exportingReport}
        onExportPdf={() => setExportOpen(true)}
        onExportReport={handleExportReport} onDeleteOpen={() => setDeleteConfirmOpen(true)}
      />
      {exportError && <Typography variant="caption" color="error.main" sx={{ display: "block", px: 2.5, mt: 0.5 }}>{exportError}</Typography>}
      <DeletePatientDialog open={deleteConfirmOpen} patientName={patient.name} deleting={deleting} isMobile={isMobile} onConfirm={handleDelete} onClose={() => setDeleteConfirmOpen(false)} />
      <ExportSelectorDialog open={exportOpen} onClose={() => setExportOpen(false)} patientId={patient.id} patientName={patient.name}
        onExport={(opts) => { setExportOpen(false); handleExportPdf(); }} />
      <RecordListSection loading={loading} error={error} records={records} filteredRecords={filteredRecords} activeTab={activeTab} setActiveTab={setActiveTab} setRecords={setRecords} doctorId={doctorId} load={load} />
      <PatientChatSection patientId={patient.id} doctorId={doctorId} />
      <Box sx={{ height: 24 }} />
    </Box>
  );
}
