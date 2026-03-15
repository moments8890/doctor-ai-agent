/**
 * 患者详情面板：展示患者基本信息、标签管理、病历记录列表，支持导出和删除。
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
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import {
  getRecords, getLabels, assignLabelToPatient, removeLabelFromPatient,
  exportPatientPdf, exportOutpatientReport, deletePatient,
} from "../../api";
import { RECORD_TYPE_FILTER_OPTS, PATIENT_MENU_ITEMS } from "./constants";
import RecordCard from "./RecordCard";
import PatientAvatar from "./PatientAvatar";
import LabelPicker from "./LabelPicker";
import ExportSelectorDialog from "./ExportSelectorDialog";

function EmptyPatientPlaceholder() {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "text.secondary", gap: 1.5 }}>
      <PeopleOutlineIcon sx={{ fontSize: 64, opacity: 0.3 }} />
      <Typography color="text.secondary">← 请在左侧选择患者</Typography>
    </Box>
  );
}

function RecordFilterPills({ value, onChange }) {
  return (
    <Box sx={{ display: "flex", gap: 0.6, px: 2, pb: 1.2, overflowX: "auto", WebkitOverflowScrolling: "touch", "&::-webkit-scrollbar": { display: "none" } }}>
      {RECORD_TYPE_FILTER_OPTS.map((opt) => (
        <Box key={opt.value} onClick={() => onChange(opt.value)}
          sx={{
            px: 1.4, py: 0.35, borderRadius: "4px", cursor: "pointer", flexShrink: 0, fontSize: 12,
            bgcolor: value === opt.value ? "#07C160" : "#f0f0f0",
            color: value === opt.value ? "#fff" : "#666",
            fontWeight: value === opt.value ? 600 : 400,
          }}>
          {opt.label}
        </Box>
      ))}
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
        <Typography sx={{ fontWeight: 600, fontSize: 16, textAlign: "center", mb: 0.8 }}>删除患者</Typography>
        <Typography sx={{ fontSize: 13, color: "#999", textAlign: "center", mb: 2.5, lineHeight: 1.7 }}>
          确定删除「{patientName}」？{"\n"}所有病历和任务将一并删除，无法恢复。
        </Typography>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 15, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!deleting ? onConfirm : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: "4px", bgcolor: "#FA5151", cursor: deleting ? "default" : "pointer", fontSize: 15, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
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
          sx={{ backgroundColor: l.color || "#d9d9d9", fontSize: 11, height: 22, borderRadius: "4px" }}
          onDelete={() => onRemoveLabel(l.id)} />
      ))}
      <Box sx={{ position: "relative" }}>
        <Box ref={labelAnchorRef} onClick={onOpenLabelPicker}
          sx={{ fontSize: 12, color: "#07C160", cursor: "pointer", px: 0.8, py: 0.3, borderRadius: "4px", border: "1px dashed #b7ebd0" }}>
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
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: exportingPdf ? "default" : "pointer", color: exportingPdf ? "#ccc" : "#07C160", fontSize: 13 }}>
        {exportingPdf ? <CircularProgress size={12} sx={{ color: "#ccc" }} /> : <FileDownloadOutlinedIcon sx={{ fontSize: 16 }} />}
        病历PDF
      </Box>
      <Box onClick={!exportingPdf && !exportingReport ? onExportReport : undefined}
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: exportingReport ? "default" : "pointer", color: exportingReport ? "#ccc" : "#5b9bd5", fontSize: 13 }}>
        {exportingReport ? <CircularProgress size={12} sx={{ color: "#ccc" }} /> : <FileDownloadOutlinedIcon sx={{ fontSize: 16 }} />}
        门诊报告
      </Box>
      <Box sx={{ flex: 1 }} />
      <Box onClick={onDeleteOpen}
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer", color: "#FA5151", fontSize: 13, "&:active": { opacity: 0.6 } }}>
        <DeleteOutlineIcon sx={{ fontSize: 16 }} />
        删除患者
      </Box>
    </Stack>
  );
}

function PatientProfileBlock({ patient, age, patientLabels, labelPickerOpen, labelAnchorRef, allLabels, labelError, exportingPdf, exportingReport, onOpenLabelPicker, onRemoveLabel, onAssignLabel, onLabelsChange, onCloseLabelPicker, onExportPdf, onExportReport, onDeleteOpen, onNavigateToChat, onCreateTask }) {
  return (
    <Box sx={{ bgcolor: "#fff", px: 2.5, pt: 2.5, pb: 2, mb: 0.8 }}>
      <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1.5 }}>
        <PatientAvatar name={patient.name} size={60} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 700, fontSize: 18 }}>{patient.name}</Typography>
          <Typography variant="caption" color="text.secondary">
            {[
              patient.gender ? { male: "男", female: "女" }[patient.gender] || patient.gender : null,
              age ? `${age} 岁` : null,
              `${patient.record_count} 份病历`,
            ].filter(Boolean).join(" · ")}
          </Typography>
        </Box>
      </Stack>
      <PatientLabelRow
        patient={patient} patientLabels={patientLabels} labelPickerOpen={labelPickerOpen}
        labelAnchorRef={labelAnchorRef} allLabels={allLabels} labelError={labelError}
        onOpenLabelPicker={onOpenLabelPicker} onRemoveLabel={onRemoveLabel}
        onAssignLabel={onAssignLabel} onLabelsChange={onLabelsChange} onCloseLabelPicker={onCloseLabelPicker}
      />
      <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
        <Box onClick={onCreateTask}
          sx={{ flex: 1, textAlign: "center", height: 36, lineHeight: "36px", borderRadius: "4px", fontSize: 14, cursor: "pointer", border: "1px solid #07C160", color: "#07C160", bgcolor: "#fff", "&:active": { opacity: 0.7 } }}>
          新建任务
        </Box>
        <Box onClick={!exportingPdf ? onExportPdf : undefined}
          sx={{ flex: 1, textAlign: "center", height: 36, lineHeight: "36px", borderRadius: "4px", fontSize: 14, cursor: exportingPdf ? "default" : "pointer", border: "1px solid #ddd", color: exportingPdf ? "#ccc" : "#333", bgcolor: "#fff", "&:active": { opacity: 0.7 } }}>
          {exportingPdf ? "导出中…" : "导出PDF"}
        </Box>
      </Box>
      <Box onClick={onNavigateToChat}
        sx={{ textAlign: "center", height: 44, lineHeight: "44px", borderRadius: "4px", fontSize: 15, fontWeight: 500, cursor: "pointer", bgcolor: "#07C160", color: "#fff", "&:active": { opacity: 0.7 } }}>
        AI对话咨询
      </Box>
      <Box sx={{ mt: 1.5, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Box onClick={!exportingReport ? onExportReport : undefined}
          sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: exportingReport ? "default" : "pointer", color: exportingReport ? "#ccc" : "#5b9bd5", fontSize: 13 }}>
          {exportingReport ? <CircularProgress size={12} sx={{ color: "#ccc" }} /> : <FileDownloadOutlinedIcon sx={{ fontSize: 16 }} />}
          门诊报告
        </Box>
        <Box onClick={onDeleteOpen}
          sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer", color: "#FA5151", fontSize: 13, "&:active": { opacity: 0.6 } }}>
          <DeleteOutlineIcon sx={{ fontSize: 16 }} />
          删除患者
        </Box>
      </Box>
    </Box>
  );
}

function PatientMenuSection({ records, patient, onNavigate }) {
  const counts = {};
  PATIENT_MENU_ITEMS.forEach((item) => {
    if (item.key === "allergy") {
      counts[item.key] = 0;
    } else if (item.recordTypes.length > 0) {
      counts[item.key] = records.filter(
        (r) => item.recordTypes.includes(r.record_type)
      ).length;
    } else {
      counts[item.key] = 0;
    }
  });

  const hasAbnormalLab = records.some(
    (r) => r.record_type === "lab" &&
      ((r.content || "").includes("异常") ||
       (r.tags || "").includes("异常"))
  );

  const allergyText = patient?.allergy_info || patient?.allergies || "";

  return (
    <Box sx={{ bgcolor: "#fff", mb: 0.8, py: 0.5 }}>
      {PATIENT_MENU_ITEMS.map((item, idx) => {
        const Icon = item.icon;
        const count = counts[item.key];
        const isAllergy = item.key === "allergy";
        const displayValue = isAllergy
          ? (allergyText || "暂无过敏信息记录")
          : (count > 0
              ? `${count} 项${item.key === "lab" && hasAbnormalLab ? " (有异常)" : ""}`
              : null);
        return (
          <Box key={item.key} onClick={() => onNavigate(item.key)}
            sx={{
              display: "flex", alignItems: "center", px: 2, py: 1.75,
              cursor: "pointer", bgcolor: "#fff",
              borderBottom: idx < PATIENT_MENU_ITEMS.length - 1
                ? "0.5px solid #f0f0f0" : "none",
              "&:active": { bgcolor: "#f9f9f9" },
            }}>
            <Box sx={{
              width: 36, height: 36, borderRadius: "8px",
              bgcolor: item.iconBg,
              display: "flex", alignItems: "center",
              justifyContent: "center", flexShrink: 0, mr: 1.5,
            }}>
              <Icon sx={{ color: item.iconColor, fontSize: 20 }} />
            </Box>
            <Typography sx={{ flex: 1, fontSize: 15, color: "#111" }}>
              {item.label}
            </Typography>
            {displayValue && (
              <Typography sx={{
                fontSize: 13, mr: 0.5,
                color: item.key === "lab" && hasAbnormalLab
                  ? "#e74c3c" : "#999",
                fontWeight: item.key === "lab" && hasAbnormalLab
                  ? 600 : 400,
                maxWidth: 140, overflow: "hidden",
                textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>
                {displayValue}
              </Typography>
            )}
            <ArrowBackIcon sx={{
              fontSize: 16, color: "#ccc",
              transform: "rotate(180deg)",
            }} />
          </Box>
        );
      })}
    </Box>
  );
}

function RecordSubPage({ title, records, doctorId, onBack, setRecords, allergyText }) {
  const isAllergy = title === "过敏信息";
  return (
    <Box sx={{ display: "flex", flexDirection: "column",
      height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48,
        px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5",
        flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex",
          alignItems: "center", gap: 0.3, cursor: "pointer",
          color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>
            患者详情
          </Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center",
          fontWeight: 600, fontSize: 16, mr: 5 }}>{title}</Typography>
      </Box>
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {isAllergy ? (
          <Box sx={{ py: 6, textAlign: "center" }}>
            <Typography color="text.secondary">
              {allergyText || "暂无过敏信息记录"}
            </Typography>
          </Box>
        ) : records.length === 0 ? (
          <Box sx={{ py: 6, textAlign: "center" }}>
            <Typography color="text.secondary">暂无记录</Typography>
          </Box>
        ) : (
          records.map((r) => (
            <RecordCard key={r.id} record={r} doctorId={doctorId}
              onUpdated={(updated) => setRecords((prev) =>
                prev.map((x) => x.id === updated.id
                  ? { ...x, ...updated } : x))}
              onDeleted={(id) => setRecords((prev) =>
                prev.filter((x) => x.id !== id))} />
          ))
        )}
        <Box sx={{ height: 24 }} />
      </Box>
    </Box>
  );
}

function RecordListSection({ loading, error, records, filteredRecords, recordTypeFilter, setRecordTypeFilter, setRecords, doctorId, load }) {
  return (
    <Box sx={{ bgcolor: "#fff", mb: 0.8 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5, pb: 1 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 14, color: "#333" }}>病历记录</Typography>
        {loading && <CircularProgress size={14} sx={{ color: "#07C160" }} />}
      </Box>
      <RecordFilterPills value={recordTypeFilter} onChange={setRecordTypeFilter} />
      {error && <Box sx={{ px: 2, pb: 1 }}><Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert></Box>}
      {!loading && !error && records.length === 0 && <Box sx={{ px: 2, pb: 2 }}><Typography variant="body2" color="text.secondary">暂无病历。</Typography></Box>}
      {filteredRecords.length === 0 && records.length > 0 ? (
        <Box sx={{ px: 2, pb: 2 }}><Typography variant="body2" color="text.secondary">该类型暂无病历。</Typography></Box>
      ) : (
        filteredRecords.map((r, idx) => (
          <Box key={r.id} sx={idx > 0 ? { borderTop: "0.5px solid #f0f0f0" } : {}}>
            <RecordCard record={r} doctorId={doctorId}
              onUpdated={(updated) => setRecords((prev) => prev.map((x) => x.id === updated.id ? { ...x, ...updated } : x))}
              onDeleted={(id) => setRecords((prev) => prev.filter((x) => x.id !== id))} />
          </Box>
        ))
      )}
    </Box>
  );
}

function usePatientDetailState({ patient, doctorId, onDeleted }) {
  const navigate = useNavigate();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportingReport, setExportingReport] = useState(false);
  const [exportError, setExportError] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
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
  async function handleExportWithSections(sections) { setExportOpen(false); setExportingPdf(true); setExportError(""); try { await exportPatientPdf(patient.id, doctorId, sections); } catch (e) { setExportError(e.message || "导出失败"); } finally { setExportingPdf(false); } }
  async function handleExportReport() { setExportingReport(true); setExportError(""); try { await exportOutpatientReport(patient.id, doctorId); } catch (e) { setExportError(e.message || "生成失败，请确认已有病历记录"); } finally { setExportingReport(false); } }

  const [menuSubPage, setMenuSubPage] = useState(null);

  // Reset sub-page when patient changes
  useEffect(() => { setMenuSubPage(null); }, [patient?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, exportOpen, setExportOpen, deleteConfirmOpen, setDeleteConfirmOpen, deleting, allLabels, labelPickerOpen, setLabelPickerOpen, labelError, patientLabels, setPatientLabels, labelAnchorRef, load, handleOpenLabelPicker, handleRemoveLabel, handleAssignLabel, handleDelete, handleExportPdf, handleExportWithSections, handleExportReport, navigate, menuSubPage, setMenuSubPage };
}

export default function PatientDetail({ patient, doctorId, onDeleted }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [recordTypeFilter, setRecordTypeFilter] = useState("");
  const { records, setRecords, loading, error, exportingPdf, exportingReport, exportError, exportOpen, setExportOpen, deleteConfirmOpen, setDeleteConfirmOpen, deleting, allLabels, labelPickerOpen, setLabelPickerOpen, labelError, patientLabels, setPatientLabels, labelAnchorRef, load, handleOpenLabelPicker, handleRemoveLabel, handleAssignLabel, handleDelete, handleExportPdf, handleExportWithSections, handleExportReport, navigate, menuSubPage, setMenuSubPage } = usePatientDetailState({ patient, doctorId, onDeleted });

  if (!patient) return <EmptyPatientPlaceholder />;

  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;
  const filteredRecords = recordTypeFilter ? records.filter((r) => r.record_type === recordTypeFilter) : records;

  // Sub-page rendering: when a menu row is tapped, show filtered records
  if (menuSubPage) {
    const menuItem = PATIENT_MENU_ITEMS.find((m) => m.key === menuSubPage);
    const subPageTitle = menuItem ? menuItem.label : "";
    const subPageRecords = menuItem && menuItem.recordTypes.length > 0
      ? records.filter((r) => menuItem.recordTypes.includes(r.record_type))
      : [];
    const allergyText = patient?.allergy_info || patient?.allergies || "";
    return (
      <RecordSubPage
        title={subPageTitle}
        records={subPageRecords}
        doctorId={doctorId}
        onBack={() => setMenuSubPage(null)}
        setRecords={setRecords}
        allergyText={allergyText}
      />
    );
  }

  return (
    <Box sx={{ overflowY: "auto", height: "100%", bgcolor: "#ededed" }}>
      <PatientProfileBlock patient={patient} age={age} patientLabels={patientLabels} labelPickerOpen={labelPickerOpen} labelAnchorRef={labelAnchorRef} allLabels={allLabels} labelError={labelError} exportingPdf={exportingPdf} exportingReport={exportingReport}
        onOpenLabelPicker={handleOpenLabelPicker} onRemoveLabel={handleRemoveLabel} onAssignLabel={handleAssignLabel} onLabelsChange={setPatientLabels} onCloseLabelPicker={() => setLabelPickerOpen(false)} onExportPdf={() => setExportOpen(true)} onExportReport={handleExportReport} onDeleteOpen={() => setDeleteConfirmOpen(true)}
        onNavigateToChat={() => navigate("/doctor/chat")} onCreateTask={() => navigate("/doctor/tasks")} />
      {exportError && <Typography variant="caption" color="error.main" sx={{ display: "block", px: 2.5, mt: 0.5 }}>{exportError}</Typography>}
      <DeletePatientDialog open={deleteConfirmOpen} patientName={patient.name} deleting={deleting} isMobile={isMobile} onConfirm={handleDelete} onClose={() => setDeleteConfirmOpen(false)} />
      <ExportSelectorDialog open={exportOpen} onClose={() => setExportOpen(false)} patientId={patient.id} patientName={patient.name} onExport={handleExportWithSections} />
      <PatientMenuSection records={records} patient={patient} onNavigate={setMenuSubPage} />
      <RecordListSection loading={loading} error={error} records={records} filteredRecords={filteredRecords} recordTypeFilter={recordTypeFilter} setRecordTypeFilter={setRecordTypeFilter} setRecords={setRecords} doctorId={doctorId} load={load} />
      <Box sx={{ height: 24 }} />
    </Box>
  );
}
