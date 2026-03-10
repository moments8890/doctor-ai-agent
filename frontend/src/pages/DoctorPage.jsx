import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  AlertTitle,
  Badge,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  MenuItem,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SearchIcon from "@mui/icons-material/Search";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import MicOutlinedIcon from "@mui/icons-material/MicOutlined";
import StopCircleOutlinedIcon from "@mui/icons-material/StopCircleOutlined";
import AttachFileOutlinedIcon from "@mui/icons-material/AttachFileOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import LogoutIcon from "@mui/icons-material/Logout";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import { Paper } from "@mui/material";
import { getPatients, getRecords, getTasks, patchTask, postponeTask, createTask, updateRecord, sendChat, transcribeAudio, ocrImage, extractFileForChat, getPendingRecord, confirmPendingRecord, abandonPendingRecord, getDoctorProfile, updateDoctorProfile, exportPatientPdf, exportOutpatientReport, getTemplateStatus, uploadTemplate, deleteTemplate, getCvdContext, getLabels, createLabel, deleteLabelById, assignLabelToPatient, removeLabelFromPatient, deletePatient } from "../api";
import RecordFields from "../components/RecordFields";
import { useDoctorStore } from "../store/doctorStore";
import { t } from "../i18n";

// ─── Constants ─────────────────────────────────────────────────────────────

const TASK_TYPE_LABEL = {
  follow_up:   "随访",
  medication:  "用药管理",
  lab_review:  "检验复查",
  referral:    "转诊",
  imaging:     "影像检查",
  appointment: "预约就诊",
  general:     "通用任务",
};
const TASK_STATUS_LABEL = { pending: "待处理", done: "已完成", cancelled: "已取消", snoozed: "已推迟" };
const ENCOUNTER_LABEL = { inpatient: "住院", outpatient: "门诊", first_visit: "初诊", follow_up_visit: "复诊", unknown: "未知" };

const RECORD_FIELDS = [
  { key: "content", label: "临床笔记" },
  { key: "record_type", label: "类型" },
];

const RECORD_TYPE_COLOR = {
  visit: "default",
  referral: "info",
  surgery: "error",
  lab: "success",
  imaging: "warning",
  dictation: "secondary",
  import: "default",
  interview_summary: "info",
};

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

const NAV = [
  { key: "chat", label: "AI 助手", icon: <ChatOutlinedIcon fontSize="small" /> },
  { key: "patients", label: "患者", icon: <PeopleOutlineIcon fontSize="small" /> },
  { key: "tasks", label: "任务", icon: <AssignmentOutlinedIcon fontSize="small" /> },
  { key: "settings", label: "设置", icon: <SettingsOutlinedIcon fontSize="small" /> },
];

// ─── Helpers ───────────────────────────────────────────────────────────────


function NavBtn({ active, icon, children, onClick, badgeCount }) {
  const content = (
    <Button
      onClick={onClick}
      startIcon={icon}
      variant={active ? "contained" : "text"}
      sx={{
        justifyContent: "flex-start", width: "100%", borderRadius: 1.5,
        fontWeight: active ? 700 : 400, color: active ? undefined : "text.secondary",
        py: 1,
      }}
    >
      {children}
    </Button>
  );
  if (badgeCount > 0) {
    return (
      <Badge badgeContent={badgeCount} color="error" sx={{ width: "100%", "& .MuiBadge-badge": { right: 8, top: 8 } }}>
        {content}
      </Badge>
    );
  }
  return content;
}

// ─── Record edit dialog ────────────────────────────────────────────────────

function RecordEditDialog({ record, doctorId, open, onClose, onSaved }) {
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  useEffect(() => {
    if (record) {
      const init = {};
      RECORD_FIELDS.forEach(({ key }) => { init[key] = record[key] || ""; });
      init.tags = Array.isArray(record.tags) ? [...record.tags] : [];
      setForm(init);
      setError("");
    }
  }, [record]);

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const saved = await updateRecord(doctorId, record.id, { ...form, tags: form.tags });
      onSaved(saved);
      onClose();
    } catch (e) {
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth fullScreen={isMobile}>
      <DialogTitle sx={{ fontWeight: 700 }}>编辑病历 <Typography component="span" variant="body2" color="text.secondary">#{record?.id}</Typography></DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Stack spacing={2}>
          {RECORD_FIELDS.map(({ key, label }) => (
            <TextField
              key={key}
              label={label}
              multiline={key === "content"}
              minRows={key === "content" ? 5 : 1}
              maxRows={key === "content" ? 16 : 1}
              size="small"
              fullWidth
              value={form[key] || ""}
              onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
            />
          ))}
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>标签</Typography>
            <Stack direction="row" flexWrap="wrap" spacing={0.5} sx={{ mb: 0.5 }}>
              {(form.tags || []).map((tag, i) => (
                <Chip key={i} label={tag} size="small" onDelete={() => setForm(f => ({ ...f, tags: f.tags.filter((_, j) => j !== i) }))} />
              ))}
            </Stack>
            <TextField
              size="small"
              placeholder="输入标签后按 Enter 添加"
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.target.value.trim()) {
                  e.preventDefault();
                  const newTag = e.target.value.trim();
                  setForm(f => ({ ...f, tags: [...(f.tags || []), newTag] }));
                  e.target.value = "";
                }
              }}
            />
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ gap: 1, px: 2, pb: 2 }}>
        <Button onClick={onClose} disabled={saving}>取消</Button>
        <Button variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ─── Single record card ────────────────────────────────────────────────────

function RecordCard({ record, doctorId, onUpdated }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [current, setCurrent] = useState(record);

  function handleSaved(updated) {
    setCurrent(updated);
    onUpdated?.(updated);
  }

  const date = current.created_at ? current.created_at.slice(0, 10) : "—";
  const typeColor = { visit: "#07C160", dictation: "#5b9bd5", import: "#e8833a", lab: "#9b59b6", imaging: "#1890ff", surgery: "#e74c3c", referral: "#16a085", interview_summary: "#8e44ad" };
  const dotColor = typeColor[current.record_type] || "#bbb";

  return (
    <Box sx={{ borderBottom: "1px solid #f2f2f2" }}>
      {/* Row header — tap to expand */}
      <Box onClick={() => setExpanded((v) => !v)} sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1.3, cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
        {/* colored dot */}
        <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: dotColor, flexShrink: 0, mt: 0.7, mr: 1.4 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, mb: 0.3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, flexWrap: "wrap" }}>
              {current.record_type && (
                <Typography sx={{ fontSize: 12, color: dotColor, fontWeight: 600 }}>
                  {RECORD_TYPE_LABEL[current.record_type] || current.record_type}
                </Typography>
              )}
              {(Array.isArray(current.tags) ? current.tags : []).map((tag, i) => (
                <Typography key={i} sx={{ fontSize: 11, color: "#999", bgcolor: "#f5f5f5", px: 0.6, borderRadius: 0.5 }}>{tag}</Typography>
              ))}
            </Box>
            <Typography sx={{ fontSize: 11, color: "#bbb", flexShrink: 0, fontFamily: "monospace" }}>{date}</Typography>
          </Box>
          <Typography sx={{
            fontSize: 13, color: current.content ? "text.primary" : "#bbb",
            overflow: "hidden", display: "-webkit-box",
            WebkitLineClamp: expanded ? "unset" : 2,
            WebkitBoxOrient: "vertical", whiteSpace: "pre-wrap",
          }}>
            {current.content || "（无记录内容）"}
          </Typography>
        </Box>
        <Box sx={{ ml: 1, flexShrink: 0, display: "flex", alignItems: "center", mt: 0.2 }}>
          {expanded ? <ExpandLessIcon sx={{ fontSize: 18, color: "#bbb" }} /> : <ExpandMoreIcon sx={{ fontSize: 18, color: "#bbb" }} />}
        </Box>
      </Box>

      {expanded && (
        <Box sx={{ px: 2, pb: 1.5, pt: 0 }}>
          <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 0.5 }}>
            <Box onClick={(e) => { e.stopPropagation(); setEditing(true); }}
              sx={{ fontSize: 12, color: "#07C160", cursor: "pointer", display: "flex", alignItems: "center", gap: 0.4 }}>
              <EditOutlinedIcon sx={{ fontSize: 13 }} />编辑
            </Box>
          </Box>
          <Box sx={{ bgcolor: "#f9f9f9", borderRadius: 1.5, p: 1.5 }}>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontSize: 13, color: "#333" }}>
              {current.content || "（无记录内容）"}
            </Typography>
          </Box>
        </Box>
      )}

      <RecordEditDialog
        record={current}
        doctorId={doctorId}
        open={editing}
        onClose={() => setEditing(false)}
        onSaved={handleSaved}
      />
    </Box>
  );
}

// ─── Patient detail panel ──────────────────────────────────────────────────

const CVD_SUBTYPE_LABEL = {
  ICH: "脑出血(ICH)", SAH: "蛛网膜下腔出血(SAH)", ischemic: "缺血性卒中",
  AVM: "动静脉畸形(AVM)", aneurysm: "动脉瘤", moyamoya: "烟雾病", other: "其他",
};
const CVD_SURGERY_STATUS_LABEL = {
  planned: "已计划", done: "已完成", cancelled: "已取消", conservative: "保守治疗",
};
const CVD_VASOSPASM_LABEL = {
  none: "无", clinical: "临床血管痉挛", radiographic: "影像血管痉挛", severe: "重度",
};
const CVD_HYDROCEPHALUS_LABEL = {
  none: "无", acute: "急性脑积水", chronic: "慢性脑积水", shunt_dependent: "分流依赖",
};
const CVD_BYPASS_LABEL = {
  direct_sta_mca: "直接吻合(STA-MCA)", indirect_edas: "间接贴敷(EDAS)",
  combined: "联合手术", other: "其他",
};
const CVD_PERFUSION_LABEL = {
  normal: "正常", mildly_reduced: "轻度减低", severely_reduced: "重度减低", improved: "改善",
};
const MRS_COLOR = (s) => s <= 2 ? "#22c55e" : s <= 4 ? "#eab308" : "#ef4444";

function NeuroCVDContextCard({ patientId, doctorId }) {
  const [ctx, setCtx] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!patientId) return;
    getCvdContext(patientId, doctorId)
      .then((d) => { setCtx(d); setLoaded(true); })
      .catch(() => setLoaded(true)); // 404 = no data, skip silently
  }, [patientId, doctorId]);

  if (!loaded || !ctx) return null;

  const rows = [
    ctx.diagnosis_subtype && ["诊断亚型", CVD_SUBTYPE_LABEL[ctx.diagnosis_subtype] || ctx.diagnosis_subtype],
    ctx.hemorrhage_location && ["出血部位", ctx.hemorrhage_location],
    ctx.gcs_score != null && ["GCS", ctx.gcs_score],
    // ICH
    ctx.ich_score != null && ["ICH评分", `${ctx.ich_score} 分`],
    ctx.ich_volume_ml != null && ["出血量", `${ctx.ich_volume_ml} mL`],
    ctx.hemorrhage_etiology && ["出血病因", ctx.hemorrhage_etiology],
    // SAH grading
    ctx.hunt_hess_grade != null && ["Hunt-Hess", `${ctx.hunt_hess_grade} 级`],
    ctx.fisher_grade != null && ["Fisher", `${ctx.fisher_grade} 级`],
    ctx.wfns_grade != null && ["WFNS", `${ctx.wfns_grade} 级`],
    ctx.modified_fisher_grade != null && ["改良Fisher", `${ctx.modified_fisher_grade} 级`],
    // SAH post-op
    ctx.vasospasm_status && ctx.vasospasm_status !== "none" && ["血管痉挛", CVD_VASOSPASM_LABEL[ctx.vasospasm_status] || ctx.vasospasm_status],
    ctx.nimodipine_regimen && ["尼莫地平方案", ctx.nimodipine_regimen],
    // Shared complication
    ctx.hydrocephalus_status && ctx.hydrocephalus_status !== "none" && ["脑积水", CVD_HYDROCEPHALUS_LABEL[ctx.hydrocephalus_status] || ctx.hydrocephalus_status],
    // AVM
    ctx.spetzler_martin_grade != null && ["Spetzler-Martin", `${ctx.spetzler_martin_grade} 级`],
    // Aneurysm
    ctx.aneurysm_location && ["动脉瘤位置", ctx.aneurysm_location],
    ctx.aneurysm_size_mm != null && ["动脉瘤大小", `${ctx.aneurysm_size_mm} mm`],
    ctx.aneurysm_neck_width_mm != null && ["瘤颈宽度", `${ctx.aneurysm_neck_width_mm} mm`],
    ctx.aneurysm_daughter_sac === "yes" && ["子囊", "有"],
    ctx.aneurysm_treatment && ["动脉瘤处理", ctx.aneurysm_treatment],
    ctx.phases_score != null && ["PHASES评分", `${ctx.phases_score} 分`],
    // Moyamoya
    ctx.suzuki_stage != null && ["铃木分期", `${ctx.suzuki_stage} 期`],
    ctx.bypass_type && ["搭桥方式", CVD_BYPASS_LABEL[ctx.bypass_type] || ctx.bypass_type],
    ctx.perfusion_status && ["灌注状态", CVD_PERFUSION_LABEL[ctx.perfusion_status] || ctx.perfusion_status],
    // Surgical
    ctx.surgery_type && ["手术方式", ctx.surgery_type],
    ctx.surgery_status && ["手术状态", CVD_SURGERY_STATUS_LABEL[ctx.surgery_status] || ctx.surgery_status],
    ctx.surgery_date && ["手术日期", ctx.surgery_date],
    // Outcome
    ctx.mrs_score != null && ["mRS", ctx.mrs_score],
    ctx.barthel_index != null && ["Barthel指数", ctx.barthel_index],
  ].filter(Boolean);

  if (rows.length === 0) return null;

  return (
    <Box sx={{ bgcolor: "#fff", mb: 0.8, px: 2, pt: 1.5, pb: 1.8 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 1, gap: 0.8 }}>
        <Box sx={{ width: 3, height: 14, borderRadius: 1, bgcolor: "#009688", flexShrink: 0 }} />
        <Typography sx={{ fontSize: 13, fontWeight: 700, color: "#009688" }}>脑血管专科病情</Typography>
        <Typography sx={{ fontSize: 11, color: "#bbb", ml: "auto" }}>更新于 {ctx.created_at}</Typography>
      </Box>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: "8px 16px" }}>
        {rows.map(([label, value]) => (
          <Box key={label}>
            <Typography sx={{ fontSize: 10, color: "#999", display: "block", mb: 0.2 }}>{label}</Typography>
            <Typography sx={{ fontWeight: 600, fontSize: 13, color: label === "mRS" ? MRS_COLOR(value) : "#222" }}>
              {value}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

const LABEL_PRESET_COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6", "#8b5cf6"];

const RECORD_TYPE_FILTER_OPTS = [
  { value: "", label: "全部" },
  { value: "visit", label: "门诊" },
  { value: "dictation", label: "语音录入" },
  { value: "import", label: "导入" },
  { value: "lab", label: "检验" },
  { value: "imaging", label: "影像" },
  { value: "surgery", label: "手术" },
  { value: "referral", label: "转诊" },
  { value: "interview_summary", label: "问诊总结" },
];

function PatientDetail({ patient, doctorId, onDeleted }) {
  const navigate = useNavigate();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportingReport, setExportingReport] = useState(false);
  const [exportError, setExportError] = useState("");
  const [recordTypeFilter, setRecordTypeFilter] = useState("");
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  async function handleDelete() {
    setDeleting(true);
    try {
      await deletePatient(patient.id, doctorId);
      setDeleteConfirmOpen(false);
      if (onDeleted) { onDeleted(patient.id); return; }
      navigate("/doctor/patients");
    } catch (e) {
      setError(e.message || "删除失败");
      setDeleteConfirmOpen(false);
    } finally {
      setDeleting(false);
    }
  }

  // Label management
  const [allLabels, setAllLabels] = useState([]);
  const [labelPickerOpen, setLabelPickerOpen] = useState(false);
  const [labelError, setLabelError] = useState("");
  const [creatingLabel, setCreatingLabel] = useState(false);
  const [newLabelName, setNewLabelName] = useState("");
  const [newLabelColor, setNewLabelColor] = useState(LABEL_PRESET_COLORS[0]);
  const [patientLabels, setPatientLabels] = useState(patient?.labels || []);
  const labelAnchorRef = useRef(null);

  const load = useCallback(() => {
    if (!patient) return;
    setLoading(true);
    setError("");
    getRecords({ doctorId, patientId: patient.id, limit: 100 })
      .then((d) => setRecords(d.items || []))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [patient?.id, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  // Sync label state when patient changes
  useEffect(() => { setPatientLabels(patient?.labels || []); }, [patient?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function loadAllLabels() {
    getLabels(doctorId).then((d) => setAllLabels(Array.isArray(d) ? d : (d.items || []))).catch(() => {});
  }

  function handleOpenLabelPicker() {
    setLabelPickerOpen(true);
    setLabelError("");
    setNewLabelName("");
    setNewLabelColor(LABEL_PRESET_COLORS[0]);
    loadAllLabels();
  }

  async function handleRemoveLabel(labelId) {
    setLabelError("");
    try {
      await removeLabelFromPatient({ doctorId, patientId: patient.id, labelId });
      setPatientLabels((prev) => prev.filter((l) => l.id !== labelId));
    } catch (e) {
      setLabelError(e.message || "移除标签失败");
    }
  }

  async function handleAssignLabel(label) {
    setLabelError("");
    if (patientLabels.some((l) => l.id === label.id)) {
      setLabelPickerOpen(false);
      return;
    }
    try {
      await assignLabelToPatient({ doctorId, patientId: patient.id, labelId: label.id });
      setPatientLabels((prev) => [...prev, { id: label.id, name: label.name, color: label.color }]);
      setLabelPickerOpen(false);
    } catch (e) {
      setLabelError(e.message || "分配标签失败");
    }
  }

  async function handleCreateAndAssignLabel() {
    if (!newLabelName.trim() || creatingLabel) return;
    setCreatingLabel(true);
    setLabelError("");
    try {
      const created = await createLabel({ doctorId, name: newLabelName.trim(), color: newLabelColor });
      await assignLabelToPatient({ doctorId, patientId: patient.id, labelId: created.id });
      setPatientLabels((prev) => [...prev, { id: created.id, name: created.name, color: created.color }]);
      setNewLabelName("");
      setLabelPickerOpen(false);
    } catch (e) {
      setLabelError(e.message || "标签创建失败");
    } finally {
      setCreatingLabel(false);
    }
  }

  if (!patient) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "text.secondary", gap: 1.5 }}>
        <PeopleOutlineIcon sx={{ fontSize: 64, opacity: 0.3 }} />
        <Typography color="text.secondary">← 请在左侧选择患者</Typography>
      </Box>
    );
  }

  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;

  function handleRecordUpdated(updated) {
    setRecords((prev) => prev.map((r) => (r.id === updated.id ? { ...r, ...updated } : r)));
  }

  async function handleExportPdf() {
    setExportingPdf(true); setExportError("");
    try { await exportPatientPdf(patient.id, doctorId); }
    catch (e) { setExportError(e.message || "导出失败"); }
    finally { setExportingPdf(false); }
  }

  async function handleExportReport() {
    setExportingReport(true); setExportError("");
    try { await exportOutpatientReport(patient.id, doctorId); }
    catch (e) { setExportError(e.message || "生成失败，请确认已有病历记录"); }
    finally { setExportingReport(false); }
  }

  return (
    <Box sx={{ overflowY: "auto", height: "100%", bgcolor: "#f7f7f7" }}>

      {/* ── Patient profile block ─────────────────────────────────────── */}
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

        {/* Labels row */}
        <Stack direction="row" spacing={0.5} flexWrap="wrap" alignItems="center" sx={{ mb: 1 }}>
          {patientLabels.map((l) => (
            <Chip key={l.id} label={l.name} size="small"
              sx={{ backgroundColor: l.color || "#e2e8f0", fontSize: 11, height: 22 }}
              onDelete={() => handleRemoveLabel(l.id)} />
          ))}
          <Box sx={{ position: "relative" }}>
            <Box ref={labelAnchorRef} onClick={handleOpenLabelPicker}
              sx={{ fontSize: 12, color: "#07C160", cursor: "pointer", px: 0.8, py: 0.3, borderRadius: 1, border: "1px dashed #b7ebd0" }}>
              + 标签
            </Box>
            {labelPickerOpen && (
              <Paper elevation={4} sx={{ position: "absolute", top: "110%", left: 0, zIndex: 1300, p: 2, minWidth: 240, borderRadius: 2 }}>
                <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 1 }}>选择标签</Typography>
                {labelError && <Alert severity="error" sx={{ mb: 1, py: 0 }}>{labelError}</Alert>}
                <Stack spacing={0.5} sx={{ mb: 1.5, maxHeight: "50vh", overflowY: "auto" }}>
                  {allLabels.length === 0 && <Typography variant="caption" color="text.secondary">暂无标签</Typography>}
                  {allLabels.map((l) => (
                    <Box key={l.id} onClick={() => handleAssignLabel(l)}
                      sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 1, borderRadius: 1, cursor: "pointer", minHeight: 40,
                        bgcolor: patientLabels.some((pl) => pl.id === l.id) ? "#f0fdf4" : "transparent",
                        "&:hover": { bgcolor: "#f1f5f9" } }}>
                      <Box sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: l.color || "#94a3b8", flexShrink: 0 }} />
                      <Typography variant="caption">{l.name}</Typography>
                      {patientLabels.some((pl) => pl.id === l.id) && <Typography variant="caption" color="success.main" sx={{ ml: "auto" }}>✓</Typography>}
                    </Box>
                  ))}
                </Stack>
                <Divider sx={{ mb: 1 }} />
                <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>新建标签</Typography>
                <TextField size="small" fullWidth placeholder="标签名称" value={newLabelName}
                  onChange={(e) => setNewLabelName(e.target.value)} sx={{ mb: 0.8 }} />
                <Stack direction="row" spacing={0.5} sx={{ mb: 1 }}>
                  {LABEL_PRESET_COLORS.map((c) => (
                    <Box key={c} onClick={() => setNewLabelColor(c)}
                      sx={{ width: 20, height: 20, borderRadius: "50%", bgcolor: c, cursor: "pointer",
                        border: newLabelColor === c ? "2px solid #1e293b" : "2px solid transparent" }} />
                  ))}
                </Stack>
                <Stack direction="row" spacing={1}>
                  <Button size="small" variant="contained" disabled={!newLabelName.trim() || creatingLabel} onClick={handleCreateAndAssignLabel} sx={{ flex: 1 }}>
                    {creatingLabel ? <CircularProgress size={14} /> : "创建并添加"}
                  </Button>
                  <Button size="small" color="inherit" onClick={() => setLabelPickerOpen(false)}>关闭</Button>
                </Stack>
              </Paper>
            )}
          </Box>
        </Stack>

        {/* Export text links + delete */}
        <Stack direction="row" spacing={2} sx={{ pt: 0.5, borderTop: "1px solid #f2f2f2" }} alignItems="center">
          <Box onClick={!exportingPdf && !exportingReport ? handleExportPdf : undefined}
            sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: exportingPdf ? "default" : "pointer", color: exportingPdf ? "#ccc" : "#07C160", fontSize: 13 }}>
            {exportingPdf ? <CircularProgress size={12} sx={{ color: "#ccc" }} /> : <FileDownloadOutlinedIcon sx={{ fontSize: 16 }} />}
            病历PDF
          </Box>
          <Box onClick={!exportingPdf && !exportingReport ? handleExportReport : undefined}
            sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: exportingReport ? "default" : "pointer", color: exportingReport ? "#ccc" : "#5b9bd5", fontSize: 13 }}>
            {exportingReport ? <CircularProgress size={12} sx={{ color: "#ccc" }} /> : <FileDownloadOutlinedIcon sx={{ fontSize: 16 }} />}
            门诊报告
          </Box>
          <Box sx={{ flex: 1 }} />
          <Box onClick={() => setDeleteConfirmOpen(true)}
            sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer", color: "#e74c3c", fontSize: 13, "&:active": { opacity: 0.6 } }}>
            <DeleteOutlineIcon sx={{ fontSize: 16 }} />
            删除患者
          </Box>
        </Stack>
        {exportError && <Typography variant="caption" color="error.main" sx={{ display: "block", mt: 0.5 }}>{exportError}</Typography>}
      </Box>

      {/* Delete confirm dialog */}
      <Dialog
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        PaperProps={{ sx: isMobile ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "16px 16px 0 0", width: "100%" } : { borderRadius: 2, minWidth: 300 } }}
        sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}
      >
        <Box sx={{ p: 2.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 16, textAlign: "center", mb: 0.8 }}>删除患者</Typography>
          <Typography sx={{ fontSize: 13, color: "#999", textAlign: "center", mb: 2.5, lineHeight: 1.7 }}>
            确定删除「{patient.name}」？{"\n"}所有病历和任务将一并删除，无法恢复。
          </Typography>
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Box onClick={() => setDeleteConfirmOpen(false)}
              sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 15, color: "#666", "&:active": { opacity: 0.7 } }}>
              取消
            </Box>
            <Box onClick={!deleting ? handleDelete : undefined}
              sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: 1.5, bgcolor: "#e74c3c", cursor: deleting ? "default" : "pointer", fontSize: 15, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
              {deleting ? "删除中…" : "确认删除"}
            </Box>
          </Box>
        </Box>
      </Dialog>

      {/* ── CVD specialty context ─────────────────────────────────────── */}
      <NeuroCVDContextCard patientId={patient.id} doctorId={doctorId} />

      {/* ── Records section ───────────────────────────────────────────── */}
      <Box sx={{ bgcolor: "#fff", mb: 0.8 }}>
        {/* Section header */}
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5, pb: 1 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 14, color: "#333" }}>病历记录</Typography>
          {loading && <CircularProgress size={14} sx={{ color: "#07C160" }} />}
        </Box>

        {/* Record type filter pills */}
        <Box sx={{ display: "flex", gap: 0.6, px: 2, pb: 1.2, overflowX: "auto", WebkitOverflowScrolling: "touch", "&::-webkit-scrollbar": { display: "none" } }}>
          {RECORD_TYPE_FILTER_OPTS.map((opt) => (
            <Box key={opt.value} onClick={() => setRecordTypeFilter(opt.value)}
              sx={{ px: 1.4, py: 0.35, borderRadius: "12px", cursor: "pointer", flexShrink: 0, fontSize: 12,
                bgcolor: recordTypeFilter === opt.value ? "#07C160" : "#f2f2f2",
                color: recordTypeFilter === opt.value ? "#fff" : "#666",
                fontWeight: recordTypeFilter === opt.value ? 600 : 400,
              }}>
              {opt.label}
            </Box>
          ))}
        </Box>

        {error && (
          <Box sx={{ px: 2, pb: 1 }}>
            <Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>
          </Box>
        )}

        {!loading && !error && records.length === 0 && (
          <Box sx={{ px: 2, pb: 2, color: "text.secondary" }}>
            <Typography variant="body2" color="text.secondary">暂无病历。</Typography>
          </Box>
        )}

        {/* Record rows */}
        {(() => {
          const filteredRecords = recordTypeFilter
            ? records.filter((r) => r.record_type === recordTypeFilter)
            : records;
          return filteredRecords.length === 0 && records.length > 0 ? (
            <Box sx={{ px: 2, pb: 2 }}>
              <Typography variant="body2" color="text.secondary">该类型暂无病历。</Typography>
            </Box>
          ) : (
            filteredRecords.map((r) => (
              <RecordCard key={r.id} record={r} doctorId={doctorId} onUpdated={handleRecordUpdated} />
            ))
          );
        })()}
      </Box>

      <Box sx={{ height: 24 }} />
    </Box>
  );
}

// ─── Patient list panel ─────────────────────────────────────────────────────

const AVATAR_COLORS = ["#07C160","#5b9bd5","#e8833a","#9b59b6","#e74c3c","#16a085","#d35400","#8e44ad","#2980b9","#c0392b"];
function nameColor(name) {
  let h = 0;
  for (let i = 0; i < (name||"").length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}
function PatientAvatar({ name, size = 42 }) {
  return (
    <Box sx={{ width: size, height: size, borderRadius: "50%", flexShrink: 0, bgcolor: nameColor(name), display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Typography sx={{ color: "#fff", fontSize: size * 0.42, fontWeight: 600, lineHeight: 1 }}>{(name||"?")[0]}</Typography>
    </Box>
  );
}
function groupPatients(list) {
  const groups = {};
  list.forEach(p => { const k = (p.name||"#")[0]; (groups[k] = groups[k]||[]).push(p); });
  return Object.entries(groups).sort(([a],[b]) => a.localeCompare(b, "zh-CN"));
}

function PatientsSection({ doctorId, onNavigateToChat, onInsertChatText, onAutoSendToChat, onPatientSelected, refreshKey = 0 }) {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  // Delete flow: action sheet target + confirm dialog
  const [deleteTarget, setDeleteTarget] = useState(null); // { id, name }
  const [confirmDelete, setConfirmDelete] = useState(null); // { id, name }
  const [deleting, setDeleting] = useState(false);
  const longPressTimer = useRef(null);
  const importFileRef = useRef(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");

  async function handleImportFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setImporting(true);
    setImportError("");
    try {
      const { text } = await extractFileForChat(file);
      if (text?.trim()) {
        onAutoSendToChat?.(text.trim());
      } else {
        setImportError("未能从文件中提取到文字，请尝试其他文件");
      }
    } catch {
      setImportError("文件解析失败，请重试");
    } finally {
      setImporting(false);
    }
  }

  const selectedId = patientId ? Number(patientId) : null;
  const selectedPatient = patients.find((p) => p.id === selectedId) || null;

  function startLongPress(p) {
    longPressTimer.current = setTimeout(() => setDeleteTarget({ id: p.id, name: p.name }), 500);
  }
  function cancelLongPress() {
    if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
  }

  async function handleDeleteConfirm() {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      await deletePatient(confirmDelete.id, doctorId);
      setPatients((prev) => prev.filter((p) => p.id !== confirmDelete.id));
      if (selectedId === confirmDelete.id) navigate("/doctor/patients");
    } catch (e) {
      setError(e.message || "删除失败");
    } finally {
      setDeleting(false);
      setConfirmDelete(null);
    }
  }

  useEffect(() => {
    onPatientSelected?.(selectedPatient?.name || "");
  }, [selectedPatient?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    getPatients(doctorId, {}, 200)
      .then((d) => setPatients(d.items || []))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [doctorId]);

  useEffect(() => { load(); }, [load, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = search.trim()
    ? patients.filter((p) => p.name.includes(search.trim()))
    : patients;

  // Mobile: show only detail when a patient is selected
  if (isMobile && selectedId) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
        {/* WeChat-style topbar */}
        <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
          <Box onClick={() => navigate("/doctor/patients")} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
            <ArrowBackIcon sx={{ fontSize: 20 }} />
            <Typography sx={{ fontSize: 15, color: "#07C160" }}>患者</Typography>
          </Box>
          <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }} noWrap>
            {selectedPatient?.name || ""}
          </Typography>
        </Box>
        <Box sx={{ flex: 1, overflow: "hidden" }}>
          <PatientDetail patient={selectedPatient} doctorId={doctorId} />
        </Box>
      </Box>
    );
  }

  // Mobile: full-width patient list (no split layout)
  if (isMobile) {
    return (
      <>
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
        <Box sx={{ px: 1.5, py: 1, borderBottom: "1px solid #e2e8f0", bgcolor: "#f7f7f7" }}>
          <TextField
            size="small" fullWidth placeholder={`搜索患者${patients.length > 0 ? ` (共${patients.length}人)` : ""}`}
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: "20px", bgcolor: "#fff" } }}
          />
        </Box>
        {error && <Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>}
        <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#fff" }}>
          {loading && <Box sx={{ p: 2, textAlign: "center" }}><CircularProgress size={20} /></Box>}

          {/* Import card — always visible at top */}
          {!loading && !search.trim() && (
            <Box sx={{ bgcolor: "#f7f7f7", borderBottom: "1px solid #e5e5e5" }}>
              <Box sx={{ px: 2, py: 0.5 }}>
                <Typography sx={{ fontSize: 11, color: "#aaa", fontWeight: 600, letterSpacing: 0.3 }}>导入患者</Typography>
              </Box>
              <Box
                onClick={() => importFileRef.current?.click()}
                sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2, bgcolor: "#fff",
                  borderBottom: "1px solid #f2f2f2", cursor: "pointer", userSelect: "none", WebkitUserSelect: "none",
                  "&:active": { bgcolor: "#f5f5f5" } }}>
                <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#e8f5e9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  {importing ? <CircularProgress size={18} sx={{ color: "#07C160" }} /> : <UploadFileOutlinedIcon sx={{ fontSize: 20, color: "#07C160" }} />}
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: 14, fontWeight: 500 }}>{importing ? "解析中…" : "上传 PDF / 图片"}</Typography>
                  <Typography sx={{ fontSize: 12, color: "#aaa" }}>出院小结、检验报告、门诊病历</Typography>
                </Box>
                <KeyboardArrowDownIcon sx={{ fontSize: 18, color: "#ccc", transform: "rotate(-90deg)" }} />
              </Box>
              <Box
                onClick={() => { onNavigateToChat?.(); }}
                sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2, bgcolor: "#fff",
                  cursor: "pointer", userSelect: "none", WebkitUserSelect: "none",
                  "&:active": { bgcolor: "#f5f5f5" } }}>
                <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#e3f2fd", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <ChatOutlinedIcon sx={{ fontSize: 20, color: "#1976d2" }} />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: 14, fontWeight: 500 }}>粘贴微信聊天记录</Typography>
                  <Typography sx={{ fontSize: 12, color: "#aaa" }}>在聊天框直接粘贴，自动提取建档</Typography>
                </Box>
                <KeyboardArrowDownIcon sx={{ fontSize: 18, color: "#ccc", transform: "rotate(-90deg)" }} />
              </Box>
              {importError && (
                <Box sx={{ px: 2, py: 0.8, bgcolor: "#fff3f3" }}>
                  <Typography sx={{ fontSize: 12, color: "#e74c3c" }}>{importError}</Typography>
                </Box>
              )}
            </Box>
          )}
          <input ref={importFileRef} type="file" hidden accept=".pdf,image/jpeg,image/png,image/webp" onChange={handleImportFile} />

          {!loading && filtered.length === 0 && !error && (
            search.trim() ? (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  未找到患者「{search.trim()}」
                </Typography>
                <Chip label={`建档 ${search.trim()}`} size="small" clickable color="primary" variant="outlined"
                  onClick={() => { onInsertChatText?.(`建档${search.trim()}`); onNavigateToChat?.(); }} />
              </Box>
            ) : (
              <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 4, gap: 1 }}>
                <Typography variant="body2" color="text.disabled">暂无患者档案</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
                  通过上方方式导入，或在聊天中建档
                </Typography>
              </Box>
            )
          )}
          {groupPatients(filtered).map(([letter, group]) => (
            <Box key={letter}>
              <Box sx={{ px: 2, py: 0.5, bgcolor: "#f7f7f7", borderBottom: "1px solid #ebebeb" }}>
                <Typography sx={{ fontSize: 12, color: "#888", fontWeight: 600 }}>{letter}</Typography>
              </Box>
              {group.map((p, idx) => {
                const age = p.year_of_birth ? new Date().getFullYear() - p.year_of_birth : null;
                const isSelected = p.id === selectedId;
                return (
                  <Box key={p.id}
                    onClick={() => { cancelLongPress(); navigate(`/doctor/patients/${p.id}`); }}
                    onMouseDown={() => startLongPress(p)}
                    onMouseUp={cancelLongPress}
                    onMouseLeave={cancelLongPress}
                    onTouchStart={() => startLongPress(p)}
                    onTouchEnd={cancelLongPress}
                    onTouchMove={cancelLongPress}
                    sx={{
                      display: "flex", alignItems: "center", gap: 1.5,
                      px: 2, py: 1.2, bgcolor: isSelected ? "#f0faf4" : "#fff",
                      borderBottom: idx < group.length - 1 ? "1px solid #f2f2f2" : "none",
                      cursor: "pointer", userSelect: "none", WebkitUserSelect: "none",
                      "&:active": { bgcolor: "#f5f5f5" },
                    }}>
                    <PatientAvatar name={p.name} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{ fontWeight: 500, fontSize: "15px" }}>{p.name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {[p.gender ? ({ male: "男", female: "女" }[p.gender] || p.gender) : null, age ? `${age}岁` : null, `${p.record_count}份病历`].filter(Boolean).join(" · ")}
                      </Typography>
                    </Box>
                    {isSelected && <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "#07C160", flexShrink: 0 }} />}
                  </Box>
                );
              })}
            </Box>
          ))}
        </Box>
      </Box>

      {/* WeChat-style action sheet — appears after long press */}
      <Dialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        PaperProps={{ sx: { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "16px 16px 0 0", width: "100%" } }}
        sx={{ "& .MuiDialog-container": { alignItems: "flex-end" } }}
      >
        <Box sx={{ pb: 2 }}>
          <Box sx={{ textAlign: "center", py: 1.5, borderBottom: "1px solid #f2f2f2" }}>
            <Typography sx={{ fontSize: 13, color: "#999" }}>{deleteTarget?.name}</Typography>
          </Box>
          <Box onClick={() => { setConfirmDelete(deleteTarget); setDeleteTarget(null); }}
            sx={{ textAlign: "center", py: 1.8, cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
            <Typography sx={{ fontSize: 17, color: "#e74c3c" }}>删除患者</Typography>
          </Box>
          <Box sx={{ height: 8, bgcolor: "#f7f7f7" }} />
          <Box onClick={() => setDeleteTarget(null)}
            sx={{ textAlign: "center", py: 1.8, cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
            <Typography sx={{ fontSize: 17, color: "#333" }}>取消</Typography>
          </Box>
        </Box>
      </Dialog>

      {/* Confirm delete dialog */}
      <Dialog
        open={Boolean(confirmDelete)}
        onClose={() => setConfirmDelete(null)}
        PaperProps={{ sx: { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "16px 16px 0 0", width: "100%" } }}
        sx={{ "& .MuiDialog-container": { alignItems: "flex-end" } }}
      >
        <Box sx={{ p: 2.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 16, textAlign: "center", mb: 0.8 }}>删除患者</Typography>
          <Typography sx={{ fontSize: 13, color: "#999", textAlign: "center", mb: 2.5, lineHeight: 1.7 }}>
            确定删除「{confirmDelete?.name}」？{"\n"}所有病历和任务将一并删除，无法恢复。
          </Typography>
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Box onClick={() => setConfirmDelete(null)}
              sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 15, color: "#666", "&:active": { opacity: 0.7 } }}>
              取消
            </Box>
            <Box onClick={!deleting ? handleDeleteConfirm : undefined}
              sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: 1.5, bgcolor: "#e74c3c", cursor: deleting ? "default" : "pointer", fontSize: 15, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
              {deleting ? "删除中…" : "删除"}
            </Box>
          </Box>
        </Box>
      </Dialog>
      </>
    );
  }

  // Desktop: split layout
  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left: patient list */}
      <Box sx={{ width: 300, flexShrink: 0, borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column", bgcolor: "#f7f7f7" }}>
        <Box sx={{ px: 1.5, py: 1, borderBottom: "1px solid #e2e8f0", bgcolor: "#f7f7f7" }}>
          <TextField
            size="small" fullWidth placeholder={`搜索患者${patients.length > 0 ? ` (共${patients.length}人)` : ""}`}
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: "20px", bgcolor: "#fff" } }}
          />
        </Box>

        {error && <Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>}

        <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#fff" }}>
          {loading && <Box sx={{ p: 2, textAlign: "center" }}><CircularProgress size={20} /></Box>}

          {/* Import card — always visible at top */}
          {!loading && !search.trim() && (
            <Box sx={{ bgcolor: "#f7f7f7", borderBottom: "1px solid #e5e5e5" }}>
              <Box sx={{ px: 2, py: 0.5 }}>
                <Typography sx={{ fontSize: 11, color: "#aaa", fontWeight: 600, letterSpacing: 0.3 }}>导入患者</Typography>
              </Box>
              <Box
                onClick={() => importFileRef.current?.click()}
                sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2, bgcolor: "#fff",
                  borderBottom: "1px solid #f2f2f2", cursor: "pointer", "&:hover": { bgcolor: "#f5f5f5" }, "&:active": { bgcolor: "#ebebeb" } }}>
                <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#e8f5e9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  {importing ? <CircularProgress size={18} sx={{ color: "#07C160" }} /> : <UploadFileOutlinedIcon sx={{ fontSize: 20, color: "#07C160" }} />}
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: 14, fontWeight: 500 }}>{importing ? "解析中…" : "上传 PDF / 图片"}</Typography>
                  <Typography sx={{ fontSize: 12, color: "#aaa" }}>出院小结、检验报告、门诊病历</Typography>
                </Box>
                <KeyboardArrowDownIcon sx={{ fontSize: 18, color: "#ccc", transform: "rotate(-90deg)" }} />
              </Box>
              <Box
                onClick={() => { onNavigateToChat?.(); }}
                sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2, bgcolor: "#fff",
                  cursor: "pointer", "&:hover": { bgcolor: "#f5f5f5" }, "&:active": { bgcolor: "#ebebeb" } }}>
                <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#e3f2fd", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <ChatOutlinedIcon sx={{ fontSize: 20, color: "#1976d2" }} />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: 14, fontWeight: 500 }}>粘贴微信聊天记录</Typography>
                  <Typography sx={{ fontSize: 12, color: "#aaa" }}>在聊天框直接粘贴，自动提取建档</Typography>
                </Box>
                <KeyboardArrowDownIcon sx={{ fontSize: 18, color: "#ccc", transform: "rotate(-90deg)" }} />
              </Box>
              {importError && (
                <Box sx={{ px: 2, py: 0.8, bgcolor: "#fff3f3" }}>
                  <Typography sx={{ fontSize: 12, color: "#e74c3c" }}>{importError}</Typography>
                </Box>
              )}
            </Box>
          )}

          {!loading && filtered.length === 0 && !error && (
            search.trim() ? (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  未找到患者「{search.trim()}」
                </Typography>
                <Chip label={`建档 ${search.trim()}`} size="small" clickable color="primary" variant="outlined"
                  onClick={() => { onInsertChatText?.(`建档${search.trim()}`); onNavigateToChat?.(); }} />
              </Box>
            ) : (
              <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 4, gap: 1 }}>
                <Typography variant="body2" color="text.disabled">暂无患者档案</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
                  通过上方方式导入，或在聊天中建档
                </Typography>
              </Box>
            )
          )}
          {groupPatients(filtered).map(([letter, group]) => (
            <Box key={letter}>
              <Box sx={{ px: 2, py: 0.5, bgcolor: "#f7f7f7", borderBottom: "1px solid #ebebeb" }}>
                <Typography sx={{ fontSize: 12, color: "#888", fontWeight: 600 }}>{letter}</Typography>
              </Box>
              {group.map((p, idx) => {
                const age = p.year_of_birth ? new Date().getFullYear() - p.year_of_birth : null;
                const isSelected = p.id === selectedId;
                return (
                  <Box key={p.id}
                    onClick={() => navigate(`/doctor/patients/${p.id}`)}
                    sx={{
                      display: "flex", alignItems: "center", gap: 1.5,
                      px: 2, py: 1.2, bgcolor: isSelected ? "#f0faf4" : "#fff",
                      borderBottom: idx < group.length - 1 ? "1px solid #f2f2f2" : "none",
                      cursor: "pointer", position: "relative",
                      "&:hover": { bgcolor: "#f5f5f5" },
                      "&:hover .del-btn": { opacity: 1 },
                      "&:active": { bgcolor: "#ebebeb" },
                    }}>
                    <PatientAvatar name={p.name} size={38} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{ fontWeight: 500, fontSize: "14px" }}>{p.name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {[p.gender ? ({ male: "男", female: "女" }[p.gender] || p.gender) : null, age ? `${age}岁` : null, `${p.record_count}份病历`].filter(Boolean).join(" · ")}
                      </Typography>
                    </Box>
                    {isSelected && <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "#07C160", flexShrink: 0 }} />}
                    {/* Desktop: delete icon appears on hover */}
                    <Box className="del-btn"
                      onClick={(e) => { e.stopPropagation(); setConfirmDelete({ id: p.id, name: p.name }); }}
                      sx={{ opacity: 0, transition: "opacity 0.15s", ml: 0.5, p: 0.5, borderRadius: 1,
                        "&:hover": { bgcolor: "#fef2f2" }, "&:active": { opacity: 0.7 } }}>
                      <DeleteOutlineIcon sx={{ fontSize: 17, color: "#e74c3c" }} />
                    </Box>
                  </Box>
                );
              })}
            </Box>
          ))}
        </Box>
      </Box>

      {/* Right: patient detail */}
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <PatientDetail patient={selectedPatient} doctorId={doctorId}
          onDeleted={(id) => { setPatients((prev) => prev.filter((p) => p.id !== id)); navigate("/doctor/patients"); }} />
      </Box>

      {/* Confirm delete dialog (desktop) */}
      <Dialog open={Boolean(confirmDelete)} onClose={() => setConfirmDelete(null)} PaperProps={{ sx: { borderRadius: 2, minWidth: 300 } }}>
        <Box sx={{ p: 3 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 16, mb: 0.8 }}>删除患者</Typography>
          <Typography sx={{ fontSize: 13, color: "#999", mb: 2.5, lineHeight: 1.7 }}>
            确定删除「{confirmDelete?.name}」？所有病历和任务将一并删除，无法恢复。
          </Typography>
          <Box sx={{ display: "flex", gap: 1.5, justifyContent: "flex-end" }}>
            <Box onClick={() => setConfirmDelete(null)}
              sx={{ px: 2, py: 0.8, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
              取消
            </Box>
            <Box onClick={!deleting ? handleDeleteConfirm : undefined}
              sx={{ px: 2, py: 0.8, borderRadius: 1.5, bgcolor: "#e74c3c", cursor: deleting ? "default" : "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
              {deleting ? "删除中…" : "确认删除"}
            </Box>
          </Box>
        </Box>
      </Dialog>
    </Box>
  );
}

// ─── Tasks section ──────────────────────────────────────────────────────────

const TASK_STATUS_OPTS = [
  { value: "pending", label: "待处理" },
  { value: "snoozed", label: "已推迟" },
  { value: "completed", label: "已完成" },
  { value: "cancelled", label: "已取消" },
];

function TasksSection({ doctorId }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("pending");
  const [createOpen, setCreateOpen] = useState(false);
  function tomorrowStr() { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10); }
  const [createForm, setCreateForm] = useState({ taskType: "follow_up", title: "", dueAt: tomorrowStr(), patientId: "", patientSearch: "", content: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [patientOptions, setPatientOptions] = useState([]);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  // Postpone popover state
  const [postponeAnchor, setPostponeAnchor] = useState(null);
  const [postponeTaskId, setPostponeTaskId] = useState(null);
  const [postponeDate, setPostponeDate] = useState("");
  const [cancelConfirmId, setCancelConfirmId] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    getTasks(doctorId, statusFilter || null)
      .then((d) => setTasks(Array.isArray(d) ? d : (d.items || [])))
      .catch((e) => setError(e.message || "任务加载失败"))
      .finally(() => setLoading(false));
  }, [doctorId, statusFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleStatus(taskId, status) {
    try {
      await patchTask(taskId, doctorId, status);
      load();
    } catch (e) {
      setError(e.message || "任务状态更新失败");
    }
  }

  async function handleCreate() {
    if (!createForm.taskType) return;
    setCreating(true);
    setCreateError("");
    try {
      await createTask(doctorId, {
        taskType: createForm.taskType,
        title: createForm.title || TASK_TYPE_LABEL[createForm.taskType] || createForm.taskType,
        dueAt: createForm.dueAt || undefined,
        patientId: createForm.patientId ? Number(createForm.patientId) : undefined,
        content: createForm.content || undefined,
      });
      setCreateOpen(false);
      setCreateForm({ taskType: "follow_up", title: "", dueAt: tomorrowStr(), patientId: "", patientSearch: "", content: "" });
      load();
    } catch (e) {
      setCreateError(e.message || "创建失败");
    } finally {
      setCreating(false);
    }
  }

  function handleOpenPostpone(e, taskId) {
    setPostponeAnchor(true);
    setPostponeTaskId(taskId);
    setPostponeDate("");
  }

  function handleClosePostpone() {
    setPostponeAnchor(null);
    setPostponeTaskId(null);
    setPostponeDate("");
  }

  async function handleConfirmPostpone() {
    if (!postponeDate || !postponeTaskId) return;
    try {
      await postponeTask(postponeTaskId, doctorId, postponeDate);
      handleClosePostpone();
      load();
    } catch (e) {
      setError(e.message || "推迟失败");
      handleClosePostpone();
    }
  }

  // Group tasks by due date into WeChat-style sections
  const today = new Date(); today.setHours(0,0,0,0);
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const weekEnd = new Date(today); weekEnd.setDate(today.getDate() + 7);

  function taskDateGroup(task) {
    if (!task.due_at) return "无截止日期";
    const d = new Date(task.due_at); d.setHours(0,0,0,0);
    if (d < today) return "已逾期";
    if (d.getTime() === today.getTime()) return "今天";
    if (d.getTime() === tomorrow.getTime()) return "明天";
    if (d < weekEnd) return "本周";
    return "之后";
  }

  const GROUP_ORDER = ["已逾期", "今天", "明天", "本周", "之后", "无截止日期"];
  const taskGroups = {};
  tasks.forEach(t => { const g = taskDateGroup(t); (taskGroups[g] = taskGroups[g] || []).push(t); });
  const sortedGroups = GROUP_ORDER.filter(g => taskGroups[g]);

  const TASK_TYPE_ICON_COLOR = {
    follow_up:   "#07C160",
    medication:  "#5b9bd5",
    lab_review:  "#e8833a",
    referral:    "#9b59b6",
    imaging:     "#1890ff",
    appointment: "#16a085",
    general:     "#8e44ad",
  };
  const TASK_TYPE_ICON_CHAR = {
    follow_up:   "随",
    medication:  "药",
    lab_review:  "检",
    referral:    "转",
    imaging:     "影",
    appointment: "约",
    general:     "务",
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      {/* WeChat-style topbar */}
      <Box sx={{ display: "flex", alignItems: "center", px: 2, height: 48, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box sx={{ display: "flex", gap: 0.6, flex: 1, overflowX: "auto", WebkitOverflowScrolling: "touch", "&::-webkit-scrollbar": { display: "none" } }}>
          {TASK_STATUS_OPTS.map((o) => (
            <Box key={o.value} onClick={() => setStatusFilter(o.value)}
              sx={{ px: 1.4, py: 0.4, borderRadius: "12px", cursor: "pointer", flexShrink: 0, fontSize: 13,
                bgcolor: statusFilter === o.value ? "#07C160" : "transparent",
                color: statusFilter === o.value ? "#fff" : "#555",
                fontWeight: statusFilter === o.value ? 600 : 400,
                "&:active": { opacity: 0.7 },
              }}>
              {o.label}
            </Box>
          ))}
        </Box>
        {loading && <CircularProgress size={14} sx={{ mr: 1, color: "#07C160" }} />}
        <Box onClick={() => { setCreateOpen(true); setCreateError(""); getPatients(doctorId, {}, 200).then((d) => setPatientOptions(d.items || [])).catch(() => {}); }}
          sx={{ width: 28, height: 28, borderRadius: "50%", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.8 } }}>
          <Typography sx={{ color: "#fff", fontSize: 20, lineHeight: 1, mt: "-2px" }}>+</Typography>
        </Box>
      </Box>

      {/* Scrollable content */}
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {error && (
          <Box sx={{ px: 2, pt: 1.5 }}>
            <Alert severity="error" onClose={() => setError("")}>{error}</Alert>
          </Box>
        )}

        {!loading && !error && tasks.length === 0 && (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1, px: 2 }}>
            <AssignmentOutlinedIcon sx={{ fontSize: 48, color: "#ccc" }} />
            <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 500 }}>暂无任务</Typography>
            <Typography variant="caption" color="text.disabled" sx={{ textAlign: "center", maxWidth: 200 }}>
              在聊天中说「今日任务」或点击 + 新建
            </Typography>
          </Box>
        )}

        {sortedGroups.map((group) => (
          <Box key={group}>
            {/* Date section header */}
            <Box sx={{ px: 2, py: 0.6, pt: 1.2 }}>
              <Typography sx={{ fontSize: 12, color: group === "已逾期" ? "#e74c3c" : "#999", fontWeight: 500 }}>
                {group}
              </Typography>
            </Box>
            {/* Task rows — full-width white cell group */}
            <Box sx={{ bgcolor: "#fff" }}>
              {taskGroups[group].map((task, idx) => {
                const isOverdue = group === "已逾期";
                const iconColor = TASK_TYPE_ICON_COLOR[task.task_type] || "#999";
                const iconChar = TASK_TYPE_ICON_CHAR[task.task_type] || "务";
                return (
                  <Box key={task.id} sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1.4,
                    borderBottom: idx < taskGroups[group].length - 1 ? "1px solid #f2f2f2" : "none" }}>
                    {/* Left avatar */}
                    <Box sx={{ width: 40, height: 40, borderRadius: "10px", bgcolor: iconColor,
                      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5, mt: 0.3 }}>
                      <Typography sx={{ color: "#fff", fontSize: 14, fontWeight: 600 }}>{iconChar}</Typography>
                    </Box>
                    {/* Content */}
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: isOverdue ? "#e74c3c" : "text.primary", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                          {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
                        </Typography>
                        {task.due_at && (
                          <Typography variant="caption" sx={{ color: isOverdue ? "#e74c3c" : "#bbb", flexShrink: 0, fontSize: 11 }}>
                            {task.due_at.slice(5, 10)}
                          </Typography>
                        )}
                      </Box>
                      {task.content && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {task.content}
                        </Typography>
                      )}
                      {task.patient_name && (
                        <Typography variant="caption" sx={{ color: "#999", display: "block", mt: 0.2 }}>
                          {task.patient_name}
                        </Typography>
                      )}
                      {/* Actions — WeChat-style text links */}
                      {task.status === "pending" && (
                        <Box sx={{ display: "flex", gap: 2, mt: 0.8 }}>
                          <Typography onClick={() => handleStatus(task.id, "completed")}
                            sx={{ fontSize: 12, color: "#07C160", cursor: "pointer", "&:active": { opacity: 0.6 } }}>完成</Typography>
                          <Typography onClick={(e) => handleOpenPostpone(e, task.id)}
                            sx={{ fontSize: 12, color: "#999", cursor: "pointer", "&:active": { opacity: 0.6 } }}>推迟</Typography>
                          <Typography onClick={() => setCancelConfirmId(task.id)}
                            sx={{ fontSize: 12, color: "#ccc", cursor: "pointer", "&:active": { opacity: 0.6 } }}>取消</Typography>
                        </Box>
                      )}
                    </Box>
                  </Box>
                );
              })}
            </Box>
          </Box>
        ))}

        <Box sx={{ height: 24 }} />
      </Box>{/* end scrollable content */}

      {/* 推迟任务 — WeChat-style bottom sheet on mobile, popover on desktop */}
      <Dialog
        open={Boolean(postponeAnchor)}
        onClose={handleClosePostpone}
        PaperProps={{ sx: isMobile
          ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "16px 16px 0 0", width: "100%" }
          : { borderRadius: 2, minWidth: 240 }
        }}
        sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}
      >
        <Box sx={{ p: 2.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 1.5, color: "#333" }}>选择新到期日</Typography>
          <TextField
            type="date" size="small" fullWidth
            InputLabelProps={{ shrink: true }}
            value={postponeDate}
            onChange={(e) => setPostponeDate(e.target.value)}
            sx={{ mb: 2 }}
          />
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Box onClick={handleClosePostpone}
              sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
              取消
            </Box>
            <Box onClick={postponeDate ? handleConfirmPostpone : undefined}
              sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: postponeDate ? "#07C160" : "#e0e0e0", cursor: postponeDate ? "pointer" : "default", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": postponeDate ? { opacity: 0.7 } : {} }}>
              确认
            </Box>
          </Box>
        </Box>
      </Dialog>

      {/* 取消任务 — WeChat action-sheet style */}
      <Dialog
        open={Boolean(cancelConfirmId)}
        onClose={() => setCancelConfirmId(null)}
        PaperProps={{ sx: isMobile
          ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "16px 16px 0 0", width: "100%" }
          : { borderRadius: 2, minWidth: 240 }
        }}
        sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}
      >
        <Box sx={{ p: 2.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 0.5, textAlign: "center", color: "#333" }}>取消任务</Typography>
          <Typography sx={{ fontSize: 13, color: "#999", mb: 2.5, textAlign: "center" }}>此任务将被标记为已取消</Typography>
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Box onClick={() => setCancelConfirmId(null)}
              sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
              保留
            </Box>
            <Box onClick={() => { handleStatus(cancelConfirmId, "cancelled"); setCancelConfirmId(null); }}
              sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#e74c3c", cursor: "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
              确认取消
            </Box>
          </Box>
        </Box>
      </Dialog>

      {/* 新建任务 Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="xs" fullWidth fullScreen={isMobile}>
        <DialogTitle sx={{ fontWeight: 700 }}>新建任务</DialogTitle>
        <DialogContent dividers>
          {createError && <Alert severity="error" sx={{ mb: 2 }}>{createError}</Alert>}
          <Stack spacing={2.5} sx={{ mt: 0.5 }}>
            <TextField
              select label="任务类型" size="small" fullWidth
              value={createForm.taskType}
              onChange={(e) => setCreateForm((f) => ({ ...f, taskType: e.target.value }))}
            >
              {Object.entries(TASK_TYPE_LABEL).map(([k, v]) => (
                <MenuItem key={k} value={k}>{v}</MenuItem>
              ))}
            </TextField>
            <TextField
              label="标题（可选）" size="small" fullWidth
              value={createForm.title}
              onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value }))}
            />
            <TextField
              label="到期日期" size="small" fullWidth type="date"
              InputLabelProps={{ shrink: true }}
              value={createForm.dueAt}
              onChange={(e) => setCreateForm((f) => ({ ...f, dueAt: e.target.value }))}
            />
            <TextField
              select size="small" fullWidth label="关联患者（可选）"
              value={createForm.patientId}
              onChange={(e) => setCreateForm((f) => ({ ...f, patientId: e.target.value }))}
            >
              <MenuItem value=""><em>不关联患者</em></MenuItem>
              {patientOptions.filter((p) => !createForm.patientSearch || p.name.includes(createForm.patientSearch)).map((p) => (
                <MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>
              ))}
            </TextField>
            <TextField
              label="备注/说明（可选）" size="small" fullWidth multiline minRows={2}
              value={createForm.content}
              onChange={(e) => setCreateForm((f) => ({ ...f, content: e.target.value }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} color="inherit">取消</Button>
          <Button onClick={handleCreate} variant="contained" disabled={creating}>
            {creating ? <CircularProgress size={16} /> : "创建"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ─── Chat section ───────────────────────────────────────────────────────────

function MsgBubble({ msg }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const isUser = msg.role === "user";

  if (isMobile) {
    return (
      <Box sx={{ display: "flex", flexDirection: isUser ? "row-reverse" : "row", alignItems: "flex-end", gap: 1, px: 1.5 }}>
        <Box sx={{
          width: 36, height: 36, borderRadius: "8px", flexShrink: 0, mb: 0.5,
          bgcolor: isUser ? "#5b9bd5" : "#07C160",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          {isUser
            ? <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: 20 }} />
            : <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: 20 }} />}
        </Box>
        <Box sx={{ maxWidth: "72%", display: "flex", flexDirection: "column", alignItems: isUser ? "flex-end" : "flex-start" }}>
          <Box sx={{
            px: "12px", py: "9px",
            borderRadius: isUser ? "14px 2px 14px 14px" : "2px 14px 14px 14px",
            bgcolor: isUser ? "#07C160" : "#fff",
            boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
          }}>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.8, color: isUser ? "#fff" : "#111" }}>{msg.content}</Typography>
            {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
          </Box>
          <Typography sx={{ mt: 0.3, px: 0.5, color: "#888", fontSize: 11 }}>{msg.ts}</Typography>
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: isUser ? "row-reverse" : "row", alignItems: "flex-end", gap: 1.2, px: 2 }}>
      <Box sx={{ width: 38, height: 38, borderRadius: "8px", flexShrink: 0, mb: 0.5,
        bgcolor: isUser ? "#5b9bd5" : "#07C160", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {isUser ? <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: 20 }} /> : <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: 20 }} />}
      </Box>
      <Box sx={{ maxWidth: "min(70%, 600px)", display: "flex", flexDirection: "column", alignItems: isUser ? "flex-end" : "flex-start" }}>
        <Box sx={{ px: "14px", py: "10px",
          borderRadius: isUser ? "14px 2px 14px 14px" : "2px 14px 14px 14px",
          bgcolor: isUser ? "#07C160" : "#fff",
          boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
        }}>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.7, color: isUser ? "#fff" : "#191919" }}>{msg.content}</Typography>
          {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
        </Box>
        <Typography sx={{ mt: 0.4, px: 0.5, color: "#aaa", fontSize: 11 }}>{msg.ts}</Typography>
      </Box>
    </Box>
  );
}

const QUICK_COMMANDS = [
  { label: "新建患者", icon: "👤", insert: "新建患者：" },
  { label: "查询患者", icon: "🔍", insert: "查询患者：" },
  { label: "患者列表", icon: "📋", insert: "患者列表" },
  { label: "补充记录", icon: "➕", insert: "补充记录：" },
  { label: "修正上条", icon: "✏️", insert: "刚才写错了，应该是" },
  { label: "导出PDF", icon: "📄", insert: "导出病历PDF：" },
  { label: "今日任务", icon: "📌", insert: "今日任务" },
  { label: "功能帮助", icon: "💡", insert: "帮助" },
];

function ChatSection({ doctorId, onMessageCountChange, externalInput, onExternalInputConsumed, onPatientCreated, autoSendText, onAutoSendConsumed }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [failedText, setFailedText] = useState(null);
  const [messages, setMessages] = useState([]);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const recordingTimerRef = useRef(null);
  const [mediaProcessing, setMediaProcessing] = useState(false);
  const [mediaError, setMediaError] = useState(null);
  const [commandsShown, setCommandsShown] = useState(() => {
    try { return localStorage.getItem("chat_commands_shown") !== "false"; } catch { return true; }
  });
  const bottomRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const fileInputRef = useRef(null);

  function nowTs() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
  const storageKey = `doctor_ai_chat_history:${(doctorId || "anon")}`;

  useEffect(() => {
    const raw = localStorage.getItem(storageKey);
    try {
      const parsed = raw ? JSON.parse(raw) : null;
      setMessages(Array.isArray(parsed) && parsed.length ? parsed : [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
    } catch {
      setMessages([{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  useEffect(() => {
    if (messages.length) localStorage.setItem(storageKey, JSON.stringify(messages));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  useEffect(() => { onMessageCountChange?.(messages.length); }, [messages.length, onMessageCountChange]);

  useEffect(() => () => clearInterval(recordingTimerRef.current), []);

  // Consume external input (e.g. inserted from PatientsSection quick action)
  useEffect(() => {
    if (externalInput) {
      setInput(externalInput);
      onExternalInputConsumed?.();
    }
  }, [externalInput]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleCommands() {
    setCommandsShown((v) => {
      const next = !v;
      try { localStorage.setItem("chat_commands_shown", String(next)); } catch {}
      return next;
    });
  }

  // Trim to last 20 messages before sending — backend rejects history > 40 entries,
  // and routing only uses the last 2 anyway.
  const history = useMemo(() => messages.slice(-20).map((m) => ({ role: m.role, content: m.content })), [messages]);

  function onClear() {
    const fresh = [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }];
    setMessages(fresh);
    localStorage.setItem(storageKey, JSON.stringify(fresh));
  }

  async function startRecording() {
    setMediaError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        setMediaProcessing(true);
        try {
          const { text } = await transcribeAudio(blob);
          if (text) setInput((prev) => (prev ? prev + " " + text : text));
        } catch {
          setMediaError("语音识别失败，请重试");
        } finally {
          setMediaProcessing(false);
        }
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
      setRecordingSeconds(0);
      recordingTimerRef.current = setInterval(() => setRecordingSeconds(s => s + 1), 1000);
    } catch {
      setMediaError("无法访问麦克风，请检查权限");
    }
  }

  function stopRecording() {
    clearInterval(recordingTimerRef.current);
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  async function onFileSelect(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setMediaError(null);
    setMediaProcessing(true);
    try {
      if (file.type.startsWith("audio/")) {
        const { text } = await transcribeAudio(file, file.name);
        if (text) setInput((prev) => (prev ? prev + " " + text : text));
      } else if (file.type.startsWith("image/")) {
        const { text } = await ocrImage(file);
        if (text) setInput((prev) => (prev ? prev + "\n" + text : text));
      } else {
        setMediaError("不支持的文件类型，请上传音频或图片");
      }
    } catch {
      setMediaError("文件处理失败，请重试");
    } finally {
      setMediaProcessing(false);
    }
  }

  async function sendText(text) {
    if (!text || loading) return;
    setFailedText(null);
    setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setLoading(true);
    try {
      const data = await sendChat({ text, doctor_id: doctorId, history });
      const reply = data.reply || t("chat.received");
      setMessages((prev) => [...prev, { role: "assistant", content: reply, record: data.record || null, ts: nowTs() }]);
      if (onPatientCreated && (reply.includes("已建档") || reply.includes("已为") && reply.includes("建档"))) {
        onPatientCreated();
      }
    } catch (error) {
      const isNetworkError = error.message === "Failed to fetch" || error.message === "NetworkError" || error.name === "TypeError";
      const friendlyMsg = isNetworkError
        ? "网络连接失败，请检查网络后重试。"
        : t("chat.requestFailed", { message: error.message });
      setMessages((prev) => [...prev, { role: "assistant", content: friendlyMsg, ts: nowTs() }]);
      setFailedText(text);
    } finally {
      setLoading(false);
    }
  }

  async function onSend() {
    await sendText(input.trim());
  }

  // Auto-send from external source (e.g. PDF import)
  useEffect(() => {
    if (autoSendText) {
      onAutoSendConsumed?.();
      sendText(autoSendText);
    }
  }, [autoSendText]); // eslint-disable-line react-hooks/exhaustive-deps

  async function onRetry() {
    if (!failedText) return;
    const t = failedText;
    setFailedText(null);
    setInput(t);
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Topbar */}
      <Box sx={{ px: isMobile ? 2 : 3, height: 48, borderBottom: "1px solid #e5e5e5", backgroundColor: isMobile ? "#ededed" : "#fff", display: "flex", alignItems: "center" }}>
        <Box sx={{ flex: 1, textAlign: isMobile ? "center" : "left" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, color: "#191919", fontSize: 15 }}>{t("chat.workspaceTitle")}</Typography>
          {isMobile && doctorId && (
            <Typography variant="caption" sx={{ color: "#999", fontSize: 10, display: "block", lineHeight: 1 }}>
              ID: {doctorId}
            </Typography>
          )}
        </Box>
        <Tooltip title="清空对话">
          <IconButton size="small" onClick={() => setClearConfirmOpen(true)} sx={{ color: "text.secondary" }}>
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: isMobile ? 1.8 : 1.4, bgcolor: "#ededed" }}>
        {messages.map((msg, idx) => <MsgBubble key={`${msg.role}-${idx}`} msg={msg} />)}
        {loading && (
          isMobile
            ? <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1, px: 1.5 }}>
                <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: 20 }} />
                </Box>
                <Box sx={{ px: "12px", py: "10px", borderRadius: "2px 14px 14px 14px", bgcolor: "#fff", boxShadow: "0 1px 2px rgba(0,0,0,0.1)", display: "flex", alignItems: "center", gap: 0.5 }}>
                  {[0, 1, 2].map((i) => (
                    <Box key={i} sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: "#aaa", animation: "dotPulse 1.4s ease-in-out infinite", animationDelay: `${i * 0.2}s`, "@keyframes dotPulse": { "0%, 80%, 100%": { opacity: 0.3, transform: "scale(0.8)" }, "40%": { opacity: 1, transform: "scale(1)" } } }} />
                  ))}
                </Box>
              </Box>
            : <Box sx={{ px: 2 }}><Typography variant="caption" color="text.secondary">AI 正在回复…</Typography></Box>
        )}
        <div ref={bottomRef} />
      </Box>
      {/* Quick commands panel */}
      <Box sx={{ px: isMobile ? 0.5 : 1.5, pt: 0.5, pb: isMobile ? 0.3 : 0.4, borderTop: "1px solid #e5e5e5", backgroundColor: "#f7f7f7" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: commandsShown ? 0.6 : 0 }}>
          <Typography sx={{ color: "#888", fontSize: 11, fontWeight: 600 }}>常用命令</Typography>
          <IconButton size="small" onClick={toggleCommands} sx={{ color: "text.disabled", p: 0.3 }}>
            {commandsShown ? <KeyboardArrowUpIcon sx={{ fontSize: 16 }} /> : <KeyboardArrowDownIcon sx={{ fontSize: 16 }} />}
          </IconButton>
        </Stack>
        {commandsShown && (
          <Box sx={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(4, 1fr)" : "repeat(8, 1fr)", gap: isMobile ? 0.8 : 0.7, mb: 0.8 }}>
            {QUICK_COMMANDS.map((cmd) => (
              <Box
                key={cmd.label}
                component="button"
                onClick={() => setInput(cmd.insert)}
                sx={{
                  display: "inline-flex", flexDirection: isMobile ? "column" : "row", alignItems: "center", justifyContent: "center",
                  gap: isMobile ? 0.3 : 0.5,
                  px: isMobile ? 0.3 : 1.2, py: isMobile ? 0.5 : 0.5,
                  borderRadius: isMobile ? "8px" : "14px",
                  border: isMobile ? "none" : "1px solid #e5e5e5",
                  backgroundColor: isMobile ? "transparent" : "#fff",
                  cursor: "pointer", fontSize: isMobile ? 10 : 11, color: "#555",
                  fontFamily: "inherit", lineHeight: 1.3, whiteSpace: "nowrap", width: "100%",
                  minHeight: isMobile ? 46 : 28,
                  transition: "all 0.1s",
                  "&:hover": { backgroundColor: isMobile ? "rgba(0,0,0,0.04)" : "#f0f7ff" },
                  "&:active": { opacity: 0.7, transform: "scale(0.96)" },
                }}
              >
                {isMobile ? (
                  <Box sx={{ width: 32, height: 32, borderRadius: "8px", bgcolor: "#f2f2f2", display: "flex", alignItems: "center", justifyContent: "center", mb: 0.2 }}>
                    <span style={{ fontSize: 17 }}>{cmd.icon}</span>
                  </Box>
                ) : (
                  <span style={{ fontSize: 12 }}>{cmd.icon}</span>
                )}
                {cmd.label}
              </Box>
            ))}
          </Box>
        )}
      </Box>

      {/* Input */}
      <input ref={fileInputRef} type="file" accept="audio/*,image/*" style={{ display: "none" }} onChange={onFileSelect} />
      {isMobile ? (
        <Box sx={{ borderTop: "1px solid #d9d9d9", backgroundColor: "#f5f5f5" }}>
          {failedText && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 0.5, bgcolor: "#fff0f0", borderTop: "1px solid #fecaca" }}>
              <Typography variant="caption" color="error" sx={{ flex: 1 }}>上条消息发送失败</Typography>
              <Button size="small" variant="text" color="error" sx={{ fontSize: 12, py: 0, minWidth: "auto" }} onClick={onRetry}>重试</Button>
              <Button size="small" variant="text" sx={{ fontSize: 12, py: 0, minWidth: "auto", color: "text.secondary" }} onClick={() => setFailedText(null)}>忽略</Button>
            </Box>
          )}
          {recording && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 0.5, bgcolor: "#fff0f0" }}>
              <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "error.main", animation: "recBlink 1s ease-in-out infinite", "@keyframes recBlink": { "0%,100%": { opacity: 1 }, "50%": { opacity: 0.3 } } }} />
              <Typography variant="caption" color="error" sx={{ fontWeight: 700 }}>
                录音中 {Math.floor(recordingSeconds/60)}:{String(recordingSeconds%60).padStart(2,"0")}
              </Typography>
              <Typography variant="caption" color="text.secondary">· 点击停止</Typography>
            </Box>
          )}
          {mediaError && (
            <Alert severity="error" onClose={() => setMediaError(null)} sx={{ mx: 1, mt: 0.5, py: 0 }}>{mediaError}</Alert>
          )}
          {mediaProcessing && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 2, pt: 0.5 }}>
              <CircularProgress size={10} /> 处理中…
            </Typography>
          )}
          <Stack direction="row" alignItems="center" sx={{ px: 1, py: 0.8, gap: 0.5 }}>
            <IconButton size="small" onClick={() => fileInputRef.current?.click()} disabled={mediaProcessing || recording}
              sx={{ color: "#666", p: 1.1 }}>
              <AttachFileOutlinedIcon />
            </IconButton>
            <TextField
              multiline minRows={1} maxRows={4} fullWidth size="small"
              placeholder={t("chat.placeholder")}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
              disabled={mediaProcessing}
              sx={{
                "& .MuiOutlinedInput-root": {
                  borderRadius: "20px", backgroundColor: "#fff",
                  fontSize: "0.9rem",
                  "& fieldset": { borderColor: "#ddd" },
                },
              }}
            />
            {input.trim() ? (
              <IconButton onClick={onSend} disabled={loading}
                sx={{ bgcolor: "#07C160", color: "#fff", p: 1.2, borderRadius: "50%", "&:hover": { bgcolor: "#06ad56" }, flexShrink: 0, minWidth: 44, minHeight: 44 }}>
                <SendOutlinedIcon fontSize="small" />
              </IconButton>
            ) : (
              <IconButton size="small"
                onClick={recording ? stopRecording : startRecording}
                disabled={mediaProcessing}
                sx={{ color: recording ? "error.main" : "#666", p: 1.1, minWidth: 44, minHeight: 44 }}>
                {recording ? <StopCircleOutlinedIcon /> : <MicOutlinedIcon />}
              </IconButton>
            )}
          </Stack>
        </Box>
      ) : (
        <Box sx={{ px: 2, py: 1.2, borderTop: "1px solid #e5e5e5", backgroundColor: "#f7f7f7" }}>
          {failedText && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 0.5, bgcolor: "#fff0f0", borderTop: "1px solid #fecaca", mb: 1 }}>
              <Typography variant="caption" color="error" sx={{ flex: 1 }}>上条消息发送失败</Typography>
              <Button size="small" variant="text" color="error" sx={{ fontSize: 12, py: 0, minWidth: "auto" }} onClick={onRetry}>重试</Button>
              <Button size="small" variant="text" sx={{ fontSize: 12, py: 0, minWidth: "auto", color: "text.secondary" }} onClick={() => setFailedText(null)}>忽略</Button>
            </Box>
          )}
          {mediaError && (
            <Alert severity="error" onClose={() => setMediaError(null)} sx={{ mb: 1, py: 0 }}>{mediaError}</Alert>
          )}
          <Stack direction="row" spacing={1} alignItems="flex-end">
            <Box sx={{ flex: 1 }}>
              <TextField
                multiline minRows={2} maxRows={6} fullWidth size="small"
                placeholder={t("chat.placeholder")}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
                disabled={mediaProcessing}
                sx={{ "& .MuiOutlinedInput-root": { borderRadius: 1.5 } }}
              />
              {input.length > 0 && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.3 }}>
                  {input.length} 字
                </Typography>
              )}
              {mediaProcessing && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.3 }}>
                  <CircularProgress size={10} /> 处理中…
                </Typography>
              )}
            </Box>
            <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flexShrink: 0 }}>
              <Tooltip title="上传音频或图片">
                <span>
                  <IconButton size="small" onClick={() => fileInputRef.current?.click()} disabled={mediaProcessing || recording}
                    sx={{ color: "text.secondary" }}>
                    <AttachFileOutlinedIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title={recording ? "停止录音" : "语音输入"}>
                <span>
                  <IconButton size="small"
                    onClick={recording ? stopRecording : startRecording}
                    disabled={mediaProcessing}
                    sx={{ color: recording ? "error.main" : "text.secondary" }}>
                    {recording ? <StopCircleOutlinedIcon fontSize="small" /> : <MicOutlinedIcon fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>
              <Button variant="contained" onClick={onSend} disabled={loading || !input.trim()}
                sx={{ borderRadius: 1.5, minWidth: 48, height: 48 }}>
                <SendOutlinedIcon fontSize="small" />
              </Button>
            </Stack>
          </Stack>
        </Box>
      )}

      {/* Clear confirmation dialog */}
      <Dialog open={clearConfirmOpen} onClose={() => setClearConfirmOpen(false)}>
        <DialogTitle>清空对话记录</DialogTitle>
        <DialogContent>
          <Typography>确定清空所有对话记录？此操作无法撤销。</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClearConfirmOpen(false)}>取消</Button>
          <Button color="error" onClick={() => { onClear(); setClearConfirmOpen(false); }}>清空</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ─── Home / dashboard ───────────────────────────────────────────────────────

function StatCard({ label, value, color = "primary.main", onClick }) {
  return (
    <Box onClick={onClick} sx={{
      flex: 1, minWidth: 100, textAlign: "center", py: 2.5, px: 1,
      bgcolor: "#fff", borderRadius: 1.5, cursor: onClick ? "pointer" : "default",
      "&:active": onClick ? { bgcolor: "#f5f5f5" } : {},
    }}>
      <Typography variant="h4" sx={{ fontWeight: 800, color, lineHeight: 1 }}>{value ?? "—"}</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>{label}</Typography>
    </Box>
  );
}

function HomeSection({ doctorId, navigate }) {
  const [stats, setStats] = useState(null);
  const [pendingTasks, setPendingTasks] = useState([]);
  const [recentRecords, setRecentRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  useEffect(() => {
    Promise.all([
      getPatients(doctorId, {}, 200),
      getTasks(doctorId, "pending"),
      getRecords({ doctorId, limit: 5 }),
    ]).then(([pData, tData, rData]) => {
      const patients = pData.items || [];
      const tasks = Array.isArray(tData) ? tData : (tData.items || []);
      const records = rData.items || [];
      setStats({
        patients: patients.length,
        pendingTasks: tasks.length,
      });
      setPendingTasks(tasks.slice(0, 5));
      setRecentRecords(records.slice(0, 5));
    }).catch(() => {}).finally(() => setLoading(false));
  }, [doctorId]);

  if (loading) return <Box sx={{ p: 4, textAlign: "center" }}><CircularProgress /></Box>;

  return (
    <Box sx={{ overflowY: "auto", height: "100%", bgcolor: "#f7f7f7" }}>
      {/* Stats row */}
      <Stack direction="row" spacing={0} sx={{ mx: 2, mt: 2, mb: 2, gap: 1 }}>
        <StatCard label="患者总数" value={stats?.patients} onClick={() => navigate("/doctor/patients")} />
        <StatCard label="待处理任务" value={stats?.pendingTasks} color={stats?.pendingTasks > 0 ? "warning.main" : "success.main"} onClick={() => navigate("/doctor/tasks")} />
      </Stack>

      {/* Quick actions */}
      <Box sx={{ bgcolor: "#fff", borderRadius: 1.5, mx: 2, mb: 2, overflow: "hidden" }}>
        {[
          { label: "进入对话", sub: "记录病历、查询患者", path: "/doctor/chat" },
          { label: "患者列表", sub: "查看所有患者", path: "/doctor/patients" },
          { label: "任务列表", sub: "待办随访提醒", path: "/doctor/tasks" },
        ].map((item, idx, arr) => (
          <Box key={item.path} onClick={() => navigate(item.path)}
            sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, cursor: "pointer",
              borderBottom: idx < arr.length - 1 ? "1px solid #f2f2f2" : "none",
              "&:active": { bgcolor: "#f5f5f5" } }}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 500 }}>{item.label}</Typography>
              <Typography variant="caption" color="text.secondary">{item.sub}</Typography>
            </Box>
            <Typography sx={{ color: "#ccc", fontSize: 18, lineHeight: 1 }}>›</Typography>
          </Box>
        ))}
      </Box>

      {/* Pending tasks */}
      {pendingTasks.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 0.8 }}>
            <Typography variant="caption" sx={{ color: "#888", fontWeight: 600, fontSize: 12 }}>待处理任务</Typography>
            <Typography variant="caption" sx={{ color: "#07C160", cursor: "pointer" }} onClick={() => navigate("/doctor/tasks")}>查看全部 ›</Typography>
          </Stack>
          <Box sx={{ bgcolor: "#fff", borderRadius: 1.5, mx: 2, overflow: "hidden" }}>
            {pendingTasks.map((task, idx) => {
              const isOverdue = task.due_at && new Date(task.due_at) < new Date();
              return (
                <Box key={task.id} sx={{ px: 2, py: 1.2, borderBottom: idx < pendingTasks.length - 1 ? "1px solid #f2f2f2" : "none" }}>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>{task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}</Typography>
                  {task.due_at && (
                    <Typography variant="caption" sx={{ color: isOverdue ? "error.main" : "text.secondary" }}>
                      {isOverdue ? "⚠ 已逾期 " : "📅 "}{task.due_at.slice(0, 10)}
                    </Typography>
                  )}
                </Box>
              );
            })}
          </Box>
        </Box>
      )}

      {/* Recent records */}
      {recentRecords.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 0.8 }}>
            <Typography variant="caption" sx={{ color: "#888", fontWeight: 600, fontSize: 12 }}>最近病历</Typography>
            <Typography variant="caption" sx={{ color: "#07C160", cursor: "pointer" }} onClick={() => navigate("/doctor/patients")}>查看患者 ›</Typography>
          </Stack>
          <Box sx={{ bgcolor: "#fff", borderRadius: 1.5, mx: 2, overflow: "hidden" }}>
            {recentRecords.map((r, idx) => (
              <Box key={r.id} onClick={() => r.patient_id && navigate(`/doctor/patients/${r.patient_id}`)}
                sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2,
                  borderBottom: idx < recentRecords.length - 1 ? "1px solid #f2f2f2" : "none",
                  cursor: r.patient_id ? "pointer" : "default", "&:active": r.patient_id ? { bgcolor: "#f5f5f5" } : {} }}>
                <PatientAvatar name={r.patient_name || "?"} size={36} />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>{r.patient_name || "未知患者"}</Typography>
                  <Typography variant="caption" color="text.secondary" noWrap>
                    {r.content ? (r.content.length > 40 ? r.content.slice(0, 40) + "…" : r.content) : "无记录"} · {r.created_at?.slice(0, 10)}
                  </Typography>
                </Box>
                <Typography sx={{ color: "#ccc", fontSize: 18, lineHeight: 1 }}>›</Typography>
              </Box>
            ))}
          </Box>
        </Box>
      )}
    </Box>
  );
}

// ─── Settings section ────────────────────────────────────────────────────────

function TemplateSubpage({ doctorId, onBack }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [msg, setMsg] = useState({ type: "", text: "" });
  const fileRef = useRef(null);

  const loadStatus = useCallback(() => {
    setLoading(true);
    getTemplateStatus(doctorId)
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false));
  }, [doctorId]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setMsg({ type: "", text: "" });
    try {
      await uploadTemplate(doctorId, file);
      setMsg({ type: "success", text: `模板已上传（${file.name}）` });
      loadStatus();
    } catch (err) {
      setMsg({ type: "error", text: err.message || "上传失败" });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDelete() {
    setDeleting(true); setMsg({ type: "", text: "" });
    try {
      await deleteTemplate(doctorId);
      setMsg({ type: "success", text: "模板已删除，将使用默认格式" });
      loadStatus();
    } catch (err) {
      setMsg({ type: "error", text: err.message || "删除失败" });
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      {/* WeChat-style topbar */}
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>设置</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }}>报告模板</Typography>
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {/* Current status */}
        <Box sx={{ px: 2, pt: 2, pb: 0.6 }}>
          <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>当前模板</Typography>
        </Box>
        <Box sx={{ bgcolor: "#fff", px: 2, py: 2, mb: 0.8 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Box sx={{ width: 44, height: 44, borderRadius: "10px", bgcolor: "#e8f5e9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <UploadFileOutlinedIcon sx={{ color: "#07C160", fontSize: 22 }} />
            </Box>
            <Box sx={{ flex: 1 }}>
              <Typography sx={{ fontWeight: 500, fontSize: 14 }}>门诊病历报告模板</Typography>
              <Typography variant="caption" color="text.secondary">
                {loading ? "加载中…" : status?.has_template
                  ? `已上传自定义模板（${status.char_count?.toLocaleString()} 字符）`
                  : "使用国家卫生部 2010 年标准格式"}
              </Typography>
            </Box>
            {status?.has_template && (
              <Box sx={{ px: 1, py: 0.3, borderRadius: "10px", bgcolor: "#e8f5e9" }}>
                <Typography sx={{ fontSize: 11, color: "#07C160", fontWeight: 600 }}>已自定义</Typography>
              </Box>
            )}
          </Box>
        </Box>

        {/* Actions */}
        <Box sx={{ px: 2, pb: 0.6 }}>
          <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>操作</Typography>
        </Box>
        <Box sx={{ bgcolor: "#fff" }}>
          <Box onClick={() => fileRef.current?.click()} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.6,
            borderBottom: status?.has_template ? "1px solid #f2f2f2" : "none", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
            {uploading
              ? <CircularProgress size={18} sx={{ mr: 1.5, color: "#07C160" }} />
              : <Box sx={{ width: 18, mr: 1.5 }} />}
            <Typography sx={{ flex: 1, fontSize: 15, color: uploading ? "#999" : "#07C160", fontWeight: 500 }}>
              {uploading ? "上传中…" : status?.has_template ? "替换模板文件" : "上传模板文件"}
            </Typography>
            <ArrowBackIcon sx={{ fontSize: 16, color: "#ccc", transform: "rotate(180deg)" }} />
          </Box>
          {status?.has_template && (
            <Box onClick={!deleting ? handleDelete : undefined} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.6, cursor: deleting ? "default" : "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
              {deleting
                ? <CircularProgress size={18} sx={{ mr: 1.5, color: "#e74c3c" }} />
                : <Box sx={{ width: 18, mr: 1.5 }} />}
              <Typography sx={{ flex: 1, fontSize: 15, color: deleting ? "#999" : "#e74c3c" }}>
                {deleting ? "删除中…" : "删除模板，恢复默认"}
              </Typography>
            </Box>
          )}
        </Box>

        {msg.text && (
          <Box sx={{ mx: 2, mt: 1.5 }}>
            <Alert severity={msg.type || "info"} onClose={() => setMsg({ type: "", text: "" })}>{msg.text}</Alert>
          </Box>
        )}

        <Box sx={{ px: 2, mt: 2 }}>
          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.8 }}>
            支持格式：PDF、DOCX、DOC、TXT、JPG、PNG，最大 1 MB。{"\n"}
            上传后，AI 生成门诊病历报告时将参照您的格式。
          </Typography>
        </Box>

        <input ref={fileRef} type="file" hidden accept=".pdf,.docx,.doc,.txt,image/jpeg,image/png,image/webp" onChange={handleUpload} />
      </Box>
    </Box>
  );
}

function SettingsSection({ doctorId, onLogout }) {
  const [subpage, setSubpage] = useState(null); // null | "template"
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const { doctorName, setAuth, accessToken } = useDoctorStore();
  const [nameDialogOpen, setNameDialogOpen] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [nameSaving, setNameSaving] = useState(false);
  const [nameError, setNameError] = useState("");

  function openNameDialog() {
    setNameInput(doctorName || "");
    setNameError("");
    setNameDialogOpen(true);
  }

  async function handleSaveName() {
    const trimmed = nameInput.trim();
    if (!trimmed) { setNameError("姓名不能为空"); return; }
    setNameSaving(true); setNameError("");
    try {
      await updateDoctorProfile(doctorId, { name: trimmed });
      setAuth(doctorId, trimmed, accessToken);
      setNameDialogOpen(false);
    } catch (e) {
      setNameError(e.message || "保存失败");
    } finally {
      setNameSaving(false);
    }
  }

  if (subpage === "template") {
    return <TemplateSubpage doctorId={doctorId} onBack={() => setSubpage(null)} />;
  }

  function SettingsRow({ icon, label, sublabel, onClick, danger }) {
    return (
      <Box onClick={onClick} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, cursor: onClick ? "pointer" : "default",
        borderBottom: "1px solid #f2f2f2", "&:active": onClick ? { bgcolor: "#f9f9f9" } : {} }}>
        <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: danger ? "#fef2f2" : "#f0faf4",
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5 }}>
          {icon}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: 15, color: danger ? "#e74c3c" : "#222" }}>{label}</Typography>
          {sublabel && <Typography variant="caption" color="text.secondary">{sublabel}</Typography>}
        </Box>
        {onClick && !danger && <ArrowBackIcon sx={{ fontSize: 16, color: "#ccc", transform: "rotate(180deg)" }} />}
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      {/* WeChat-style topbar (mobile only — desktop uses sidebar) */}
      {isMobile && (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: 48, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 16 }}>设置</Typography>
        </Box>
      )}

      <Box sx={{ flex: 1, overflowY: "auto" }}>

      {/* Account group */}
      <Box sx={{ px: 2, pt: 2, pb: 0.6 }}>
        <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>账户</Typography>
      </Box>
      <Box sx={{ bgcolor: "#fff" }}>
        <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.8, borderBottom: "1px solid #f2f2f2" }}>
          <Box sx={{ width: 52, height: 52, borderRadius: "50%", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5 }}>
            <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: 26 }} />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontWeight: 600, fontSize: 16 }}>{doctorName || doctorId}</Typography>
            <Typography variant="caption" color="text.secondary">{doctorId}</Typography>
          </Box>
        </Box>
        {/* Name edit row */}
        <Box onClick={openNameDialog} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "1px solid #f2f2f2", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
          <Typography sx={{ fontSize: 14, color: "#555", flex: 1 }}>昵称</Typography>
          <Typography sx={{ fontSize: 14, color: "#999", mr: 0.8 }}>{doctorName || "未设置"}</Typography>
          <ArrowBackIcon sx={{ fontSize: 16, color: "#ccc", transform: "rotate(180deg)" }} />
        </Box>
      </Box>

      {/* Tools group */}
      <Box sx={{ px: 2, pt: 2, pb: 0.6 }}>
        <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>工具</Typography>
      </Box>
      <Box sx={{ bgcolor: "#fff" }}>
        <SettingsRow
          icon={<UploadFileOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />}
          label="报告模板"
          sublabel="自定义门诊病历报告格式"
          onClick={() => setSubpage("template")}
        />
      </Box>

      {/* Logout — only shown on mobile (desktop has sidebar) */}
      {isMobile && (
        <>
          <Box sx={{ px: 2, pt: 2, pb: 0.6 }}>
            <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>账户操作</Typography>
          </Box>
          <Box sx={{ bgcolor: "#fff" }}>
            <SettingsRow
              icon={<LogoutIcon sx={{ color: "#e74c3c", fontSize: 20 }} />}
              label="退出登录"
              onClick={onLogout}
              danger
            />
          </Box>
        </>
      )}

      <Box sx={{ height: 32 }} />
      </Box>{/* end inner scroll */}

      {/* Name edit Dialog */}
      <Dialog open={nameDialogOpen} onClose={() => setNameDialogOpen(false)}
        PaperProps={{ sx: isMobile ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "16px 16px 0 0", width: "100%" } : { borderRadius: 2, minWidth: 300 } }}
        sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
        <Box sx={{ p: 2.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 0.5, color: "#333" }}>设置昵称</Typography>
          <Typography sx={{ fontSize: 12, color: "#999", mb: 2 }}>AI 助手将用此姓名称呼您，例如「好的，张医生」</Typography>
          <TextField
            fullWidth size="small" placeholder="请输入您的姓名（如：张伟）"
            value={nameInput} onChange={(e) => setNameInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSaveName(); }}
            autoFocus sx={{ mb: nameError ? 0.5 : 2 }}
          />
          {nameError && <Typography sx={{ fontSize: 12, color: "#e74c3c", mb: 1.5 }}>{nameError}</Typography>}
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Box onClick={() => setNameDialogOpen(false)}
              sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
              取消
            </Box>
            <Box onClick={!nameSaving ? handleSaveName : undefined}
              sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#07C160", cursor: nameSaving ? "default" : "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
              {nameSaving ? "保存中…" : "保存"}
            </Box>
          </Box>
        </Box>
      </Dialog>
    </Box>
  );
}

// ─── Main DoctorPage ────────────────────────────────────────────────────────

export default function DoctorPage() {
  const { section, patientId } = useParams();
  const navigate = useNavigate();
  const { doctorId, doctorName, accessToken, clearAuth, setAuth } = useDoctorStore();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [pendingTaskCount, setPendingTaskCount] = useState(0);
  const [pendingRecord, setPendingRecord] = useState(null);
  const [confirmSnackbar, setConfirmSnackbar] = useState(false);
  const [pendingError, setPendingError] = useState("");
  // Cross-section: text to insert into chat input
  const [chatInsertText, setChatInsertText] = useState("");
  // Text to auto-send in chat (e.g. extracted PDF content from patients section)
  const [chatAutoSendText, setChatAutoSendText] = useState("");
  // Increment to force PatientsSection to re-fetch after chat creates a patient
  const [patientRefreshKey, setPatientRefreshKey] = useState(0);
  // Selected patient name for mobile topbar
  const [selectedPatientName, setSelectedPatientName] = useState("");

  // Onboarding dialog state
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardName, setOnboardName] = useState("");
  const [onboardSaving, setOnboardSaving] = useState(false);

  const activeSection = patientId ? "patients" : (section || "chat");

  // Check onboarding status on mount
  useEffect(() => {
    if (!doctorId) return;
    getDoctorProfile(doctorId)
      .then((profile) => {
        if (!profile.onboarded) {
          setOnboardName(profile.name || "");
          setShowOnboarding(true);
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  async function handleOnboardSubmit() {
    if (!onboardName.trim() || onboardSaving) return;
    setOnboardSaving(true);
    try {
      await updateDoctorProfile(doctorId, { name: onboardName.trim() });
      setAuth(doctorId, onboardName.trim(), accessToken);
      setShowOnboarding(false);
    } catch {
      // ignore — leave dialog open so user can retry
    } finally {
      setOnboardSaving(false);
    }
  }

  useEffect(() => {
    if (!doctorId) return;
    getTasks(doctorId, "pending")
      .then((d) => {
        const tasks = Array.isArray(d) ? d : (d.items || []);
        setPendingTaskCount(tasks.length);
      })
      .catch(() => {});
  }, [doctorId]);

  useEffect(() => {
    if (!doctorId) return;
    const fetchPending = () => {
      getPendingRecord(doctorId)
        .then((data) => setPendingRecord(data || null))
        .catch(() => {});
    };
    fetchPending();
    const id = setInterval(fetchPending, 30000);
    return () => clearInterval(id);
  }, [doctorId]);

  async function handleConfirmPending() {
    try {
      await confirmPendingRecord(doctorId);
      setPendingRecord(null);
      setConfirmSnackbar(true);
    } catch (_) {}
  }

  async function handleAbandonPending() {
    try {
      await abandonPendingRecord(doctorId);
      setPendingRecord(null);
      setPendingError("");
    } catch (e) {
      setPendingError(e.message || "操作失败，请重试");
    }
  }

  function handleNav(key) {
    if (key === "chat") navigate("/doctor/chat");
    else navigate(`/doctor/${key}`);
  }

  function handleLogout() {
    clearAuth();
    // Notify WeChat Mini Program web-view to return to MP login page
    if (window.__wxjs_environment === "miniprogram") {
      wx.miniProgram?.postMessage?.({ data: { action: "logout" } }); // eslint-disable-line no-undef
    }
    navigate("/login");
  }

  const navBadge = { tasks: pendingTaskCount, chat: pendingRecord ? 1 : 0 };

  return (
    <Box sx={{ display: "flex", height: "100vh", bgcolor: "#f7f7f7" }}>
      {/* Sidebar — desktop only */}
      {!isMobile && (
        <Box sx={{
          width: 220, flexShrink: 0, borderRight: "1px solid #e5e5e5",
          backgroundColor: "#f7f7f7", display: "flex", flexDirection: "column", py: 2, px: 0,
        }}>
          {/* Header */}
          <Box sx={{ mb: 2, px: 2 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "#07C160" }}>医生工作台</Typography>
            <Typography variant="caption" color="text.secondary">{doctorName || doctorId}</Typography>
          </Box>

          {/* Nav */}
          <Box sx={{ flex: 1 }}>
            {NAV.map((item) => (
              <Box key={item.key} onClick={() => handleNav(item.key)}
                sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, cursor: "pointer", borderRadius: 0,
                  bgcolor: activeSection === item.key ? "#07C160" : "transparent",
                  color: activeSection === item.key ? "#fff" : "#555",
                  "&:hover": { bgcolor: activeSection === item.key ? "#07C160" : "rgba(0,0,0,0.05)" },
                  "&:active": { opacity: 0.8 },
                }}>
                <Box sx={{ "& svg": { fontSize: 20, color: activeSection === item.key ? "#fff" : "#555" } }}>
                  {navBadge[item.key] > 0
                    ? <Badge badgeContent={navBadge[item.key]} color="error">{item.icon}</Badge>
                    : item.icon}
                </Box>
                <Typography sx={{ fontSize: 14, fontWeight: activeSection === item.key ? 600 : 400, color: "inherit" }}>{item.label}</Typography>
              </Box>
            ))}
          </Box>

          {/* Footer */}
          <Box onClick={handleLogout}
            sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, cursor: "pointer",
              color: "#888", "&:hover": { bgcolor: "rgba(0,0,0,0.05)" }, "&:active": { opacity: 0.8 } }}>
            <LogoutIcon fontSize="small" sx={{ color: "#888" }} />
            <Typography sx={{ fontSize: 14, color: "#888" }}>退出登录</Typography>
          </Box>
        </Box>
      )}

      {/* Main content */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", pb: isMobile ? "56px" : 0 }}>
        {/* Topbar — hidden for chat/tasks/settings/patients (each has its own topbar) */}
        {activeSection !== "chat" && activeSection !== "tasks" && activeSection !== "settings" && activeSection !== "patients" && (
          <Box sx={{ px: isMobile ? 2 : 3, py: 1.2, borderBottom: "1px solid #e2e8f0", backgroundColor: "#fff" }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "text.secondary" }}>
              {activeSection === "patients" && (isMobile && patientId && selectedPatientName ? selectedPatientName : "患者管理")}
              {activeSection === "tasks" && "任务列表"}
              {activeSection === "settings" && "设置"}
            </Typography>
          </Box>
        )}

        {/* Pending record confirmation banner */}
        {pendingError && (
          <Alert severity="error" sx={{ mx: 2, mt: 1.5, borderRadius: 1.5 }} onClose={() => setPendingError("")}>
            {pendingError}
          </Alert>
        )}
        {pendingRecord && (
          isMobile ? (
            <Box sx={{ mx: 0, mt: 0, px: 2, py: 1.2, backgroundColor: "#fff7e6", borderBottom: "1px solid #ffd666", display: "flex", alignItems: "center", gap: 1 }}>
              <Typography sx={{ fontSize: 13, color: "#d46b08", flex: 1 }}>
                ⏳ 待确认：{pendingRecord.patient_name || "未关联"} — {pendingRecord.content_preview?.slice(0, 20)}{pendingRecord.content_preview?.length > 20 ? "…" : ""}
                {pendingRecord.expires_at && (() => { const mins = Math.max(0, Math.round((new Date(pendingRecord.expires_at) - Date.now()) / 60000)); return <span style={{ marginLeft: 4, fontWeight: 700, color: mins <= 2 ? "#cf1322" : "#d46b08" }}>({mins}分钟)</span>; })()}
              </Typography>
              <Box onClick={handleConfirmPending} sx={{ px: 1.5, py: 0.4, borderRadius: "12px", bgcolor: "#07C160", cursor: "pointer", "&:active": { opacity: 0.8 } }}>
                <Typography sx={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>确认</Typography>
              </Box>
              <Box onClick={handleAbandonPending} sx={{ px: 1.5, py: 0.4, borderRadius: "12px", bgcolor: "#f2f2f2", cursor: "pointer", "&:active": { opacity: 0.8 } }}>
                <Typography sx={{ color: "#555", fontSize: 12 }}>撤销</Typography>
              </Box>
            </Box>
          ) : (
            <Box sx={{ mx: 2, mt: 1, px: 2, py: 1, backgroundColor: "#fff7e6", border: "1px solid #ffd666", borderRadius: 1.5, display: "flex", alignItems: "center", gap: 1.5 }}>
              <Typography sx={{ fontSize: 13, color: "#d46b08", flex: 1 }}>
                ⏳ <strong>待确认病历</strong>：{pendingRecord.patient_name || "未关联"} — {pendingRecord.content_preview}
                {pendingRecord.expires_at && (() => { const mins = Math.max(0, Math.round((new Date(pendingRecord.expires_at) - Date.now()) / 60000)); return <span style={{ marginLeft: 8, fontWeight: 700, color: mins <= 2 ? "#cf1322" : "#d46b08" }}>{mins <= 0 ? "即将过期" : `${mins}分钟后过期`}</span>; })()}
              </Typography>
              <Box onClick={handleConfirmPending} sx={{ px: 2, py: 0.6, borderRadius: "12px", bgcolor: "#07C160", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.8 } }}>
                <Typography sx={{ color: "#fff", fontSize: 13, fontWeight: 600 }}>确认保存</Typography>
              </Box>
              <Box onClick={handleAbandonPending} sx={{ px: 2, py: 0.6, borderRadius: "12px", bgcolor: "#f2f2f2", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.8 } }}>
                <Typography sx={{ color: "#555", fontSize: 13 }}>撤销</Typography>
              </Box>
            </Box>
          )
        )}

        {/* Section content */}
        <Box sx={{ flex: 1, overflow: "hidden" }}>
          {activeSection === "chat" && (
            <ChatSection
              doctorId={doctorId}
              onMessageCountChange={() => {}}
              externalInput={chatInsertText}
              onExternalInputConsumed={() => setChatInsertText("")}
              onPatientCreated={() => setPatientRefreshKey((k) => k + 1)}
              autoSendText={chatAutoSendText}
              onAutoSendConsumed={() => setChatAutoSendText("")}
            />
          )}
          {activeSection === "patients" && (
            <PatientsSection
              doctorId={doctorId}
              onNavigateToChat={() => navigate("/doctor/chat")}
              onInsertChatText={(text) => { setChatInsertText(text); navigate("/doctor/chat"); }}
              onAutoSendToChat={(text) => { setChatAutoSendText(text); navigate("/doctor/chat"); }}
              onPatientSelected={(name) => setSelectedPatientName(name || "")}
              refreshKey={patientRefreshKey}
            />
          )}
          {activeSection === "tasks" && <TasksSection doctorId={doctorId} />}
          {activeSection === "settings" && <SettingsSection doctorId={doctorId} onLogout={handleLogout} />}
        </Box>
      </Box>

      {/* Bottom navigation — mobile only */}
      {isMobile && (
        <Box sx={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 10, borderTop: "1px solid #e2e8f0" }}>
          <BottomNavigation
            value={activeSection}
            onChange={(_, val) => handleNav(val)}
            sx={{
              height: 64,
              "& .MuiBottomNavigationAction-root": { minWidth: 56, paddingTop: "8px", color: "#888" },
              "& .Mui-selected": { color: "#07C160" },
              "& .Mui-selected .MuiBottomNavigationAction-label": { color: "#07C160", fontWeight: 600 },
            }}
          >
            {NAV.map((item) => (
              <BottomNavigationAction
                key={item.key}
                label={item.label}
                value={item.key}
                showLabel
                icon={
                  item.key === "tasks" && pendingTaskCount > 0
                    ? <Badge badgeContent={pendingTaskCount} color="error">{item.icon}</Badge>
                    : item.key === "chat" && pendingRecord
                    ? <Badge variant="dot" color="warning">{item.icon}</Badge>
                    : item.icon
                }
                sx={{ minWidth: 0, "& .MuiBottomNavigationAction-label": { fontSize: 11 } }}
              />
            ))}
          </BottomNavigation>
        </Box>
      )}

      {/* Confirm success snackbar */}
      <Snackbar
        open={confirmSnackbar}
        autoHideDuration={3000}
        onClose={() => setConfirmSnackbar(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert onClose={() => setConfirmSnackbar(false)} severity="success" sx={{ width: "100%" }}>
          病历已保存
        </Alert>
      </Snackbar>

      {/* First-time onboarding dialog — not dismissable */}
      <Dialog open={showOnboarding} maxWidth="xs" fullWidth>
        <DialogTitle>欢迎，请完成初始设置</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="您的姓名"
              value={onboardName}
              onChange={(e) => setOnboardName(e.target.value)}
              fullWidth
              autoFocus
              required
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            variant="contained"
            disabled={!onboardName.trim() || onboardSaving}
            onClick={handleOnboardSubmit}
          >
            {onboardSaving ? "保存中..." : "完成设置"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
