/**
 * 患者详情面板：可折叠个人信息、带计数的病历标签页、置顶操作栏。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog,
  Stack, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  getRecords, getLabels, assignLabelToPatient, removeLabelFromPatient,
  exportPatientPdf, exportOutpatientReport, deletePatient,
} from "../../api";
import { RECORD_TAB_GROUPS } from "./constants";
import RecordCard from "./RecordCard";
import LabelPicker from "./LabelPicker";
import ExportSelectorDialog from "./ExportSelectorDialog";
import { TYPE, ICON } from "../../theme";

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

function PatientLabelRow({ patient, patientLabels, labelPickerOpen, labelAnchorRef, allLabels, labelError, onOpenLabelPicker, onRemoveLabel, onAssignLabel, onLabelsChange, onCloseLabelPicker }) {
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" alignItems="center" sx={{ mb: 1 }}>
      {patientLabels.map((l) => (
        <Chip key={l.id} label={l.name} size="small"
          sx={{ backgroundColor: l.color || "#f0f0f0", fontSize: TYPE.micro.fontSize, height: 22, borderRadius: "4px" }}
          onDelete={() => onRemoveLabel(l.id)} />
      ))}
      <Box sx={{ position: "relative" }}>
        <Box ref={labelAnchorRef} onClick={onOpenLabelPicker}
          sx={{ fontSize: TYPE.caption.fontSize, color: "#07C160", cursor: "pointer", px: 0.8, py: 0.3, borderRadius: 1, border: "1px dashed #b7ebd0" }}>
          + 标签
        </Box>
        {labelPickerOpen && (
          <LabelPicker
            doctorId={patient.doctor_id}
            patientId={patient.id}
            allLabels={allLabels}
            patientLabels={patientLabels}
            labelError={labelError}
            onAssign={onAssignLabel}
            onClose={onCloseLabelPicker}
            onLabelsChange={onLabelsChange}
          />
        )}
      </Box>
    </Stack>
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

function CollapsibleProfile({ patient, age, records, expanded, onToggle, patientLabels, labelPickerOpen, labelAnchorRef, allLabels, labelError, exportingPdf, exportingReport, onOpenLabelPicker, onRemoveLabel, onAssignLabel, onLabelsChange, onCloseLabelPicker, onExportPdf, onExportReport, onDeleteOpen }) {
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
        <PatientLabelRow
          patient={patient} patientLabels={patientLabels} labelPickerOpen={labelPickerOpen}
          labelAnchorRef={labelAnchorRef} allLabels={allLabels} labelError={labelError}
          onOpenLabelPicker={onOpenLabelPicker} onRemoveLabel={onRemoveLabel}
          onAssignLabel={onAssignLabel} onLabelsChange={onLabelsChange} onCloseLabelPicker={onCloseLabelPicker}
        />
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

      {/* Labels */}
      <PatientLabelRow
        patient={patient} patientLabels={patientLabels} labelPickerOpen={labelPickerOpen}
        labelAnchorRef={labelAnchorRef} allLabels={allLabels} labelError={labelError}
        onOpenLabelPicker={onOpenLabelPicker} onRemoveLabel={onRemoveLabel}
        onAssignLabel={onAssignLabel} onLabelsChange={onLabelsChange} onCloseLabelPicker={onCloseLabelPicker}
      />

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
  const [allLabels, setAllLabels] = useState([]);
  const [labelPickerOpen, setLabelPickerOpen] = useState(false);
  const [labelError, setLabelError] = useState("");
  const [patientLabels, setPatientLabels] = useState(patient?.labels || []);
  const labelAnchorRef = useRef(null);

  const load = useCallback(() => {
    if (!patient) return; setLoading(true); setError("");
    getRecords({ doctorId, patientId: patient.id, limit: 100 }).then((d) => setRecords(d.items || [])).catch((e) => setError(e.message || "加载失败")).finally(() => setLoading(false));
  }, [patient?.id, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPatientLabels(patient?.labels || []); }, [patient?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleOpenLabelPicker() { setLabelPickerOpen(true); setLabelError(""); getLabels(doctorId).then((d) => setAllLabels(Array.isArray(d) ? d : (d.items || []))).catch(() => {}); }
  async function handleRemoveLabel(labelId) { setLabelError(""); try { await removeLabelFromPatient({ doctorId, patientId: patient.id, labelId }); setPatientLabels((prev) => prev.filter((l) => l.id !== labelId)); } catch (e) { setLabelError(e.message || "移除标签失败"); } }
  async function handleAssignLabel(label) { setLabelError(""); if (patientLabels.some((l) => l.id === label.id)) { setLabelPickerOpen(false); return; } try { await assignLabelToPatient({ doctorId, patientId: patient.id, labelId: label.id }); setPatientLabels((prev) => [...prev, { id: label.id, name: label.name, color: label.color }]); setLabelPickerOpen(false); } catch (e) { setLabelError(e.message || "分配标签失败"); } }
  async function handleDelete() { setDeleting(true); try { await deletePatient(patient.id, doctorId); setDeleteConfirmOpen(false); if (onDeleted) { onDeleted(patient.id); return; } navigate("/doctor/patients"); } catch (e) { setError(e.message || "删除失败"); setDeleteConfirmOpen(false); } finally { setDeleting(false); } }
  async function handleExportPdf() { setExportingPdf(true); setExportError(""); try { await exportPatientPdf(patient.id, doctorId); } catch (e) { setExportError(e.message || "导出失败"); } finally { setExportingPdf(false); } }
  async function handleExportReport() { setExportingReport(true); setExportError(""); try { await exportOutpatientReport(patient.id, doctorId); } catch (e) { setExportError(e.message || "生成失败，请确认已有病历记录"); } finally { setExportingReport(false); } }

  return { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, deleteConfirmOpen, setDeleteConfirmOpen, deleting, allLabels, labelPickerOpen, setLabelPickerOpen, labelError, patientLabels, setPatientLabels, labelAnchorRef, load, handleOpenLabelPicker, handleRemoveLabel, handleAssignLabel, handleDelete, handleExportPdf, handleExportReport };
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

  const { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, deleteConfirmOpen, setDeleteConfirmOpen, deleting, allLabels, labelPickerOpen, setLabelPickerOpen, labelError, patientLabels, setPatientLabels, labelAnchorRef, load, handleOpenLabelPicker, handleRemoveLabel, handleAssignLabel, handleDelete, handleExportPdf, handleExportReport } = usePatientDetailState({ patient, doctorId, onDeleted });

  if (!patient) return <EmptyPatientPlaceholder />;

  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;

  /* Filter records by active tab */
  const activeGroup = RECORD_TAB_GROUPS.find((g) => g.key === activeTab);
  const filteredRecords = activeGroup?.types ? records.filter((r) => activeGroup.types.includes(r.record_type)) : records;

  return (
    <Box sx={{ overflowY: "auto", height: "100%", bgcolor: "#ededed" }}>
      <CollapsibleProfile
        patient={patient} age={age} records={records} expanded={expanded} onToggle={() => setExpanded((v) => !v)}
        patientLabels={patientLabels} labelPickerOpen={labelPickerOpen} labelAnchorRef={labelAnchorRef}
        allLabels={allLabels} labelError={labelError} exportingPdf={exportingPdf} exportingReport={exportingReport}
        onOpenLabelPicker={handleOpenLabelPicker} onRemoveLabel={handleRemoveLabel}
        onAssignLabel={handleAssignLabel} onLabelsChange={setPatientLabels}
        onCloseLabelPicker={() => setLabelPickerOpen(false)} onExportPdf={() => setExportOpen(true)}
        onExportReport={handleExportReport} onDeleteOpen={() => setDeleteConfirmOpen(true)}
      />
      {exportError && <Typography variant="caption" color="error.main" sx={{ display: "block", px: 2.5, mt: 0.5 }}>{exportError}</Typography>}
      <DeletePatientDialog open={deleteConfirmOpen} patientName={patient.name} deleting={deleting} isMobile={isMobile} onConfirm={handleDelete} onClose={() => setDeleteConfirmOpen(false)} />
      <ExportSelectorDialog open={exportOpen} onClose={() => setExportOpen(false)} patientId={patient.id} patientName={patient.name}
        onExport={(opts) => { setExportOpen(false); handleExportPdf(); }} />
      <RecordListSection loading={loading} error={error} records={records} filteredRecords={filteredRecords} activeTab={activeTab} setActiveTab={setActiveTab} setRecords={setRecords} doctorId={doctorId} load={load} />
      <Box sx={{ height: 24 }} />
    </Box>
  );
}
