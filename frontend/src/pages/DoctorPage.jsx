import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  AlertTitle,
  Badge,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
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
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
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
import { Paper, Popover } from "@mui/material";
import { getPatients, getRecords, getTasks, patchTask, postponeTask, createTask, updateRecord, sendChat, transcribeAudio, ocrImage, getPendingRecord, confirmPendingRecord, abandonPendingRecord, getDoctorProfile, updateDoctorProfile, exportPatientPdf, exportOutpatientReport, getTemplateStatus, uploadTemplate, deleteTemplate, getCvdContext, getLabels, createLabel, deleteLabelById, assignLabelToPatient, removeLabelFromPatient } from "../api";
import RecordFields from "../components/RecordFields";
import { useDoctorStore } from "../store/doctorStore";
import { t } from "../i18n";

// ─── Constants ─────────────────────────────────────────────────────────────

const TASK_TYPE_LABEL = {
  follow_up: "随访", review: "复查", call: "电话联系", message: "发送消息",
  prescription: "处方续开", referral: "转诊", education: "患者教育",
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
  { key: "home", label: "首页", icon: <HomeOutlinedIcon fontSize="small" /> },
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
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
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
      <DialogActions>
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

  return (
    <Card variant="outlined" sx={{ borderRadius: 1.5, mb: 1.2 }}>
      <CardActionArea onClick={() => setExpanded((v) => !v)} sx={{ px: 2, py: 1.2 }}>
        <Stack direction="row" alignItems="flex-start" spacing={1.5}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>{date}</Typography>
              {current.record_type && (
                <Chip
                  label={RECORD_TYPE_LABEL[current.record_type] || current.record_type}
                  size="small"
                  color={RECORD_TYPE_COLOR[current.record_type] || "default"}
                  sx={{ fontSize: 11, height: 18 }}
                />
              )}
              {(Array.isArray(current.tags) ? current.tags : []).map((tag, i) => (
                <Chip key={i} label={tag} size="small" sx={{ fontSize: 11, maxWidth: 160 }} />
              ))}
            </Stack>
            <Typography variant="body2" sx={{ mt: 0.4, color: "text.primary", fontWeight: 500 }} noWrap={!expanded}>
              {current.content || <span style={{ color: "#94a3b8" }}>（无记录内容）</span>}
            </Typography>
          </Box>
          <Stack direction="row" spacing={0.5} alignItems="center" onClick={(e) => e.stopPropagation()}>
            <Tooltip title="编辑">
              <IconButton size="small" onClick={() => setEditing(true)}>
                <EditOutlinedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            {expanded ? <ExpandLessIcon fontSize="small" sx={{ color: "text.secondary" }} /> : <ExpandMoreIcon fontSize="small" sx={{ color: "text.secondary" }} />}
          </Stack>
        </Stack>
      </CardActionArea>

      {expanded && (
        <Box sx={{ px: 2, pb: 2, pt: 0.5 }}>
          <Divider sx={{ mb: 1.5 }} />
          <Stack spacing={1.2}>
            {RECORD_FIELDS.map(({ key, label }) => current[key] ? (
              <Box key={key}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: "block" }}>{label}</Typography>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{current[key]}</Typography>
              </Box>
            ) : null)}
          </Stack>
        </Box>
      )}

      <RecordEditDialog
        record={current}
        doctorId={doctorId}
        open={editing}
        onClose={() => setEditing(false)}
        onSaved={handleSaved}
      />
    </Card>
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
    <Card variant="outlined" sx={{ borderRadius: 2, mb: 2, borderColor: "#b2dfdb" }}>
      <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
        <Typography variant="caption" sx={{ fontWeight: 700, color: "teal", letterSpacing: 0.5, textTransform: "uppercase" }}>
          脑血管专科病情
        </Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "4px 12px", mt: 0.8 }}>
          {rows.map(([label, value]) => (
            <Box key={label}>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: 10 }}>{label}</Typography>
              <Typography variant="body2" sx={{
                fontWeight: 600, fontSize: 13,
                color: label === "mRS" ? MRS_COLOR(value) : "text.primary",
              }}>
                {value}
              </Typography>
            </Box>
          ))}
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
          更新于 {ctx.created_at}
        </Typography>
      </CardContent>
    </Card>
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

function PatientDetail({ patient, doctorId }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportingReport, setExportingReport] = useState(false);
  const [exportError, setExportError] = useState("");
  const [recordTypeFilter, setRecordTypeFilter] = useState("");

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
    <Box sx={{ p: 2.5, overflowY: "auto", height: "100%" }}>
      {/* Patient header */}
      <Card variant="outlined" sx={{ borderRadius: 2, mb: 2.5, p: 2 }}>
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" flexWrap="wrap" spacing={1}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>{patient.name}</Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }} flexWrap="wrap">
              {patient.gender && <Typography variant="caption" color="text.secondary">{{ male: "男", female: "女" }[patient.gender] || patient.gender}</Typography>}
              {age && <Typography variant="caption" color="text.secondary">{age} 岁</Typography>}
            </Stack>
            <Stack direction="row" spacing={0.5} sx={{ mt: 0.8 }} flexWrap="wrap" alignItems="center">
              {patientLabels.map((l) => (
                <Chip
                  key={l.id}
                  label={l.name}
                  size="small"
                  sx={{ backgroundColor: l.color || "#e2e8f0", fontSize: 11 }}
                  onDelete={() => handleRemoveLabel(l.id)}
                />
              ))}
              <Box sx={{ position: "relative" }}>
                <Button
                  ref={labelAnchorRef}
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: 11, py: 0.2, px: 1, minWidth: 0, borderRadius: 2 }}
                  onClick={handleOpenLabelPicker}
                >
                  + 添加标签
                </Button>
                {labelPickerOpen && (
                  <Paper elevation={4} sx={{ position: "absolute", top: "110%", left: 0, zIndex: 1300, p: 1.5, minWidth: 200, borderRadius: 2 }}>
                    <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 1 }}>选择标签</Typography>
                    {labelError && <Alert severity="error" sx={{ mb: 1, py: 0 }}>{labelError}</Alert>}
                    <Stack spacing={0.5} sx={{ mb: 1.5, maxHeight: 180, overflowY: "auto" }}>
                      {allLabels.length === 0 && <Typography variant="caption" color="text.secondary">暂无标签</Typography>}
                      {allLabels.map((l) => (
                        <Box
                          key={l.id}
                          onClick={() => handleAssignLabel(l)}
                          sx={{
                            display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5,
                            borderRadius: 1, cursor: "pointer",
                            bgcolor: patientLabels.some((pl) => pl.id === l.id) ? "#f0fdf4" : "transparent",
                            "&:hover": { bgcolor: "#f1f5f9" },
                          }}
                        >
                          <Box sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: l.color || "#94a3b8", flexShrink: 0 }} />
                          <Typography variant="caption">{l.name}</Typography>
                          {patientLabels.some((pl) => pl.id === l.id) && <Typography variant="caption" color="success.main" sx={{ ml: "auto" }}>✓</Typography>}
                        </Box>
                      ))}
                    </Stack>
                    <Divider sx={{ mb: 1 }} />
                    <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>新建标签</Typography>
                    <TextField
                      size="small" fullWidth placeholder="标签名称"
                      value={newLabelName}
                      onChange={(e) => setNewLabelName(e.target.value)}
                      sx={{ mb: 0.8 }}
                    />
                    <Stack direction="row" spacing={0.5} sx={{ mb: 1 }}>
                      {LABEL_PRESET_COLORS.map((c) => (
                        <Box
                          key={c}
                          onClick={() => setNewLabelColor(c)}
                          sx={{
                            width: 20, height: 20, borderRadius: "50%", bgcolor: c, cursor: "pointer",
                            border: newLabelColor === c ? "2px solid #1e293b" : "2px solid transparent",
                          }}
                        />
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
          </Box>
          <Stack alignItems="flex-end" spacing={0.5}>
            <Typography variant="caption" color="text.secondary">{patient.record_count} 份病历</Typography>
            <Stack direction="row" spacing={0.8}>
              <Tooltip title="导出全部病历 PDF">
                <span>
                  <Button size="small" variant="outlined"
                    startIcon={exportingPdf ? <CircularProgress size={12} /> : <FileDownloadOutlinedIcon />}
                    disabled={exportingPdf || exportingReport} onClick={handleExportPdf}>
                    病历PDF
                  </Button>
                </span>
              </Tooltip>
              <Tooltip title="AI 提取结构化字段，生成标准门诊病历报告">
                <span>
                  <Button size="small" variant="outlined" color="secondary"
                    startIcon={exportingReport ? <CircularProgress size={12} /> : <FileDownloadOutlinedIcon />}
                    disabled={exportingPdf || exportingReport} onClick={handleExportReport}>
                    门诊报告
                  </Button>
                </span>
              </Tooltip>
            </Stack>
            {exportError && <Typography variant="caption" color="error.main">{exportError}</Typography>}
          </Stack>
        </Stack>
      </Card>

      {/* CVD specialty context */}
      <NeuroCVDContextCard patientId={patient.id} doctorId={doctorId} />

      {/* Records */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>病历记录</Typography>
        {loading && <CircularProgress size={16} />}
      </Stack>

      {/* Record type filter */}
      <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mb: 1.5 }}>
        {RECORD_TYPE_FILTER_OPTS.map((opt) => (
          <Chip
            key={opt.value}
            label={opt.label}
            size="small"
            clickable
            variant={recordTypeFilter === opt.value ? "filled" : "outlined"}
            color={recordTypeFilter === opt.value ? "primary" : "default"}
            onClick={() => setRecordTypeFilter(opt.value)}
          />
        ))}
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 1.5 }} action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>
      )}

      {!loading && !error && records.length === 0 && (
        <Typography variant="body2" color="text.secondary">暂无病历。</Typography>
      )}

      {(() => {
        const filteredRecords = recordTypeFilter
          ? records.filter((r) => r.record_type === recordTypeFilter)
          : records;
        return filteredRecords.length === 0 && records.length > 0 ? (
          <Typography variant="body2" color="text.secondary">该类型暂无病历。</Typography>
        ) : (
          filteredRecords.map((r) => (
            <RecordCard key={r.id} record={r} doctorId={doctorId} onUpdated={handleRecordUpdated} />
          ))
        );
      })()}
    </Box>
  );
}

// ─── Patient list panel ─────────────────────────────────────────────────────

const RISK_OPTS = [
  { value: "", label: "全部风险" },
  { value: "critical", label: "危重" },
  { value: "high", label: "高风险" },
  { value: "medium", label: "中风险" },
  { value: "low", label: "低风险" },
];

function PatientsSection({ doctorId, onNavigateToChat, onInsertChatText, onPatientSelected }) {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [risk, setRisk] = useState("");

  const selectedId = patientId ? Number(patientId) : null;
  const selectedPatient = patients.find((p) => p.id === selectedId) || null;

  useEffect(() => {
    onPatientSelected?.(selectedPatient?.name || "");
  }, [selectedPatient?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    getPatients(doctorId, risk ? { risk } : {}, 200)
      .then((d) => setPatients(d.items || []))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [doctorId, risk]);

  useEffect(() => { load(); }, [load]);

  const filtered = search.trim()
    ? patients.filter((p) => p.name.includes(search.trim()))
    : patients;

  // Mobile: show only detail when a patient is selected
  if (isMobile && selectedId) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <Box sx={{ px: 1.5, py: 1, borderBottom: "1px solid #e2e8f0", backgroundColor: "#fff" }}>
          <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/doctor/patients")} size="small">
            返回列表
          </Button>
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
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <Box sx={{ p: 1.5, borderBottom: "1px solid #e2e8f0" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
            患者管理{patients.length > 0 ? ` (${patients.length})` : ""}
          </Typography>
          <TextField
            size="small" fullWidth placeholder="搜索患者姓名"
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
            sx={{ mb: 1 }}
          />
          <TextField select size="small" fullWidth value={risk} onChange={(e) => setRisk(e.target.value)} label="风险筛选">
            {RISK_OPTS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
        </Box>
        {error && <Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>}
        <Box sx={{ flex: 1, overflowY: "auto", p: 1 }}>
          {loading && <Box sx={{ p: 2, textAlign: "center" }}><CircularProgress size={20} /></Box>}
          {!loading && filtered.length === 0 && !error && (
            search.trim() ? (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  未找到患者「{search.trim()}」。说「建档{search.trim()}」可创建新患者。
                </Typography>
                <Chip
                  label={`建档${search.trim()}`}
                  size="small"
                  clickable
                  color="primary"
                  variant="outlined"
                  onClick={() => { onInsertChatText?.(`建档${search.trim()}`); onNavigateToChat?.(); }}
                />
              </Box>
            ) : (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  暂无患者。在聊天中说「建档姓名」即可创建。
                </Typography>
                <Button size="small" variant="outlined" onClick={onNavigateToChat}>去聊天</Button>
              </Box>
            )
          )}
          {filtered.map((p) => {
            const age = p.year_of_birth ? new Date().getFullYear() - p.year_of_birth : null;
            const isSelected = p.id === selectedId;
            return (
              <Card
                key={p.id}
                variant="outlined"
                onClick={() => navigate(`/doctor/patients/${p.id}`)}
                sx={{
                  mb: 0.8, borderRadius: 1.5, cursor: "pointer",
                  borderColor: isSelected ? "primary.main" : "divider",
                  backgroundColor: isSelected ? "primary.50" : "background.paper",
                  "&:hover": { borderColor: "primary.main", backgroundColor: "primary.50" },
                }}
              >
                <CardContent sx={{ py: 1.2, px: 1.5, "&:last-child": { pb: 1.2 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{p.name}</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.4 }} flexWrap="wrap">
                    {p.gender && <Typography variant="caption" color="text.secondary">{p.gender}</Typography>}
                    {age && <Typography variant="caption" color="text.secondary">{age} 岁</Typography>}
                    <Typography variant="caption" color="text.secondary">{p.record_count} 份病历</Typography>
                  </Stack>
                </CardContent>
              </Card>
            );
          })}
        </Box>
      </Box>
    );
  }

  // Desktop: split layout
  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left: patient list */}
      <Box sx={{ width: 320, flexShrink: 0, borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column" }}>
        <Box sx={{ p: 1.5, borderBottom: "1px solid #e2e8f0" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
            患者管理{patients.length > 0 ? ` (${patients.length})` : ""}
          </Typography>
          <TextField
            size="small" fullWidth placeholder="搜索患者姓名"
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
            sx={{ mb: 1 }}
          />
          <TextField select size="small" fullWidth value={risk} onChange={(e) => setRisk(e.target.value)} label="风险筛选">
            {RISK_OPTS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
        </Box>

        {error && <Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>}

        <Box sx={{ flex: 1, overflowY: "auto", p: 1 }}>
          {loading && <Box sx={{ p: 2, textAlign: "center" }}><CircularProgress size={20} /></Box>}
          {!loading && filtered.length === 0 && !error && (
            search.trim() ? (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  未找到患者「{search.trim()}」。说「建档{search.trim()}」可创建新患者。
                </Typography>
                <Chip
                  label={`建档${search.trim()}`}
                  size="small"
                  clickable
                  color="primary"
                  variant="outlined"
                  onClick={() => { onInsertChatText?.(`建档${search.trim()}`); onNavigateToChat?.(); }}
                />
              </Box>
            ) : (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  暂无患者。在聊天中说「建档姓名」即可创建。
                </Typography>
                <Button size="small" variant="outlined" onClick={onNavigateToChat}>去聊天</Button>
              </Box>
            )
          )}
          {filtered.map((p) => {
            const age = p.year_of_birth ? new Date().getFullYear() - p.year_of_birth : null;
            const isSelected = p.id === selectedId;
            return (
              <Card
                key={p.id}
                variant="outlined"
                onClick={() => navigate(`/doctor/patients/${p.id}`)}
                sx={{
                  mb: 0.8, borderRadius: 1.5, cursor: "pointer",
                  borderColor: isSelected ? "primary.main" : "divider",
                  backgroundColor: isSelected ? "primary.50" : "background.paper",
                  "&:hover": { borderColor: "primary.main", backgroundColor: "primary.50" },
                }}
              >
                <CardContent sx={{ py: 1.2, px: 1.5, "&:last-child": { pb: 1.2 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{p.name}</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.4 }} flexWrap="wrap">
                    {p.gender && <Typography variant="caption" color="text.secondary">{p.gender}</Typography>}
                    {age && <Typography variant="caption" color="text.secondary">{age} 岁</Typography>}
                    <Typography variant="caption" color="text.secondary">{p.record_count} 份病历</Typography>
                  </Stack>
                </CardContent>
              </Card>
            );
          })}
        </Box>
      </Box>

      {/* Right: patient detail */}
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <PatientDetail patient={selectedPatient} doctorId={doctorId} />
      </Box>
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
  const [createForm, setCreateForm] = useState({ taskType: "follow_up", title: "", dueAt: "", patientId: "", content: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  // Postpone popover state
  const [postponeAnchor, setPostponeAnchor] = useState(null);
  const [postponeTaskId, setPostponeTaskId] = useState(null);
  const [postponeDate, setPostponeDate] = useState("");

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
      setCreateForm({ taskType: "follow_up", title: "", dueAt: "", patientId: "", content: "" });
      load();
    } catch (e) {
      setCreateError(e.message || "创建失败");
    } finally {
      setCreating(false);
    }
  }

  function handleOpenPostpone(e, taskId) {
    setPostponeAnchor(e.currentTarget);
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

  return (
    <Box sx={{ p: 3, overflowY: "auto", height: "100%" }}>
      <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2.5 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>任务列表</Typography>
        {loading && <CircularProgress size={18} />}
        <Box sx={{ flex: 1 }} />
        <Button size="small" variant="contained" onClick={() => { setCreateOpen(true); setCreateError(""); }}>+ 新建任务</Button>
        <Stack direction="row" spacing={0.5} flexWrap="wrap">
          {TASK_STATUS_OPTS.map((o) => (
            <Chip
              key={o.value}
              label={o.label}
              size="small"
              onClick={() => setStatusFilter(o.value)}
              variant={statusFilter === o.value ? "filled" : "outlined"}
              color={statusFilter === o.value ? "primary" : "default"}
              clickable
            />
          ))}
        </Stack>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setError("")}>{error}</Alert>
      )}

      {!loading && !error && tasks.length === 0 && (
        <Typography color="text.secondary" variant="body2">
          暂无任务。在聊天中说「待办任务」可查看，或点击「新建任务」创建。
        </Typography>
      )}

      <Stack spacing={1.2}>
        {tasks.map((task) => {
          const isOverdue = task.due_at && new Date(task.due_at) < new Date() && task.status === "pending";
          return (
            <Card key={task.id} variant="outlined" sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
                <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}</Typography>
                    {task.description && (
                      <Typography variant="caption" color="text.secondary">{task.description}</Typography>
                    )}
                    {task.due_at && (
                      <Typography variant="caption" sx={{ display: "block", mt: 0.3, color: isOverdue ? "error.main" : "text.secondary" }}>
                        {isOverdue ? "已逾期 · " : "到期 · "}{task.due_at.slice(0, 10)}
                      </Typography>
                    )}
                  </Box>
                  {task.status === "pending" && (
                    <Stack direction="row" spacing={0.5}>
                      <Button size="small" variant="contained" onClick={() => handleStatus(task.id, "completed")}>完成</Button>
                      <Button size="small" color="inherit" onClick={() => handleStatus(task.id, "cancelled")}>取消</Button>
                      <Button size="small" color="warning" variant="outlined" onClick={(e) => handleOpenPostpone(e, task.id)}>推迟</Button>
                    </Stack>
                  )}
                </Stack>
              </CardContent>
            </Card>
          );
        })}
      </Stack>

      {/* 推迟任务 Popover */}
      <Popover
        open={Boolean(postponeAnchor)}
        anchorEl={postponeAnchor}
        onClose={handleClosePostpone}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      >
        <Box sx={{ p: 2, minWidth: 220 }}>
          <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 1 }}>选择新到期日</Typography>
          <TextField
            type="date"
            size="small"
            fullWidth
            InputLabelProps={{ shrink: true }}
            value={postponeDate}
            onChange={(e) => setPostponeDate(e.target.value)}
            sx={{ mb: 1.5 }}
          />
          <Stack direction="row" spacing={1}>
            <Button size="small" variant="contained" disabled={!postponeDate} onClick={handleConfirmPostpone} sx={{ flex: 1 }}>确认</Button>
            <Button size="small" color="inherit" onClick={handleClosePostpone}>取消</Button>
          </Stack>
        </Box>
      </Popover>

      {/* 新建任务 Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>新建任务</DialogTitle>
        <DialogContent dividers>
          {createError && <Alert severity="error" sx={{ mb: 2 }}>{createError}</Alert>}
          <Stack spacing={2} sx={{ mt: 0.5 }}>
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
              label="关联患者 ID（可选）" size="small" fullWidth
              value={createForm.patientId}
              onChange={(e) => setCreateForm((f) => ({ ...f, patientId: e.target.value }))}
            />
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
  const isUser = msg.role === "user";
  return (
    <Box sx={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", px: 1 }}>
      <Paper elevation={0} sx={{
        maxWidth: "min(85%, 720px)", p: 1.5, borderRadius: 2,
        bgcolor: isUser ? "#eaf4ff" : "#f0faf4",
        border: "1px solid", borderColor: isUser ? "#c8def6" : "#c9e8d4",
      }}>
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{msg.content}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5, textAlign: "right" }}>{msg.ts}</Typography>
        {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
      </Paper>
    </Box>
  );
}

const QUICK_COMMANDS = [
  // Row 1 — Patient management
  { label: "建档[姓名]", insert: "建档" },
  { label: "查[姓名]", insert: "查" },
  { label: "删除[姓名]", insert: "删除" },
  { label: "患者列表", insert: "患者列表" },
  // Row 2 — Records
  { label: "补充：...", insert: "补充：" },
  { label: "刚才写错了", insert: "刚才写错了，应该是" },
  { label: "PDF:...", insert: "PDF:" },
  { label: "今天任务", insert: "今天任务" },
];

function ChatSection({ doctorId, onMessageCountChange, externalInput, onExternalInputConsumed }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [recording, setRecording] = useState(false);
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

  const history = useMemo(() => messages.map((m) => ({ role: m.role, content: m.content })), [messages]);

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
    } catch {
      setMediaError("无法访问麦克风，请检查权限");
    }
  }

  function stopRecording() {
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

  async function onSend() {
    const text = input.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setLoading(true);
    try {
      const data = await sendChat({ text, doctor_id: doctorId, history });
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply || t("chat.received"), record: data.record || null, ts: nowTs() }]);
    } catch (error) {
      const isNetworkError = error.message === "Failed to fetch" || error.message === "NetworkError" || error.name === "TypeError";
      const friendlyMsg = isNetworkError
        ? "网络连接失败，请检查网络后重试。"
        : t("chat.requestFailed", { message: error.message });
      setMessages((prev) => [...prev, { role: "assistant", content: friendlyMsg, ts: nowTs() }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Topbar */}
      <Box sx={{ px: 3, py: 1.2, borderBottom: "1px solid #e2e8f0", backgroundColor: "#fff", display: "flex", alignItems: "center" }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "text.secondary", flex: 1 }}>{t("chat.workspaceTitle")}</Typography>
        <Tooltip title="清空对话">
          <IconButton size="small" onClick={() => setClearConfirmOpen(true)} sx={{ color: "text.secondary" }}>
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: 1.4 }}>
        {messages.map((msg, idx) => <MsgBubble key={`${msg.role}-${idx}`} msg={msg} />)}
        {loading && <Box sx={{ px: 2 }}><Typography variant="caption" color="text.secondary">AI 正在回复…</Typography></Box>}
        <div ref={bottomRef} />
      </Box>
      {/* Quick commands panel */}
      <Box sx={{ px: 2, pt: 1, borderTop: "1px solid #e2e8f0", backgroundColor: "#fafbfc" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: commandsShown ? 0.5 : 0 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>常用命令</Typography>
          <IconButton size="small" onClick={toggleCommands} sx={{ color: "text.secondary" }}>
            {commandsShown ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
          </IconButton>
        </Stack>
        {commandsShown && (
          <>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8, fontSize: 11 }}>
              点击插入常用指令（~1ms，无需等待 AI）
            </Typography>
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0.6, mb: 1 }}>
              {QUICK_COMMANDS.map((cmd) => (
                <Chip
                  key={cmd.label}
                  label={cmd.label}
                  size="small"
                  clickable
                  variant="outlined"
                  onClick={() => setInput((prev) => prev ? prev + cmd.insert : cmd.insert)}
                  sx={{ fontSize: 11, justifyContent: "flex-start" }}
                />
              ))}
            </Box>
          </>
        )}
      </Box>

      {/* Input */}
      <Box sx={{ px: 2, py: 1.5, borderTop: "1px solid #e2e8f0", backgroundColor: "#fff" }}>
        {mediaError && (
          <Alert severity="error" onClose={() => setMediaError(null)} sx={{ mb: 1, py: 0 }}>
            {mediaError}
          </Alert>
        )}
        <Stack direction="row" spacing={1} alignItems="flex-end">
          {/* Hidden file input for audio + image uploads */}
          <input ref={fileInputRef} type="file" accept="audio/*,image/*" style={{ display: "none" }} onChange={onFileSelect} />
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

function StatCard({ label, value, color = "primary.main" }) {
  return (
    <Card variant="outlined" sx={{ borderRadius: 2, flex: 1, minWidth: 120 }}>
      <CardContent>
        <Typography variant="h4" sx={{ fontWeight: 800, color }}>{value ?? "—"}</Typography>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
      </CardContent>
    </Card>
  );
}

function HomeSection({ doctorId, navigate }) {
  const [stats, setStats] = useState(null);
  const [pendingTasks, setPendingTasks] = useState([]);
  const [recentRecords, setRecentRecords] = useState([]);
  const [loading, setLoading] = useState(true);

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
    <Box sx={{ p: 3, overflowY: "auto", height: "100%" }}>
      {/* Stats */}
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>总览</Typography>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <StatCard label="患者总数" value={stats?.patients} />
        <StatCard label="待处理任务" value={stats?.pendingTasks} color={stats?.pendingTasks > 0 ? "warning.main" : "success.main"} />
      </Stack>

      {/* Quick actions */}
      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 3 }}>
        <Button size="small" variant="outlined" onClick={() => navigate("/doctor/chat")}>新建对话</Button>
        <Button size="small" variant="outlined" onClick={() => navigate("/doctor/patients")}>查看患者</Button>
        <Button size="small" variant="outlined" onClick={() => navigate("/doctor/tasks")}>查看任务</Button>
      </Stack>

      {/* Pending tasks */}
      {pendingTasks.length > 0 && (
        <>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>待处理任务</Typography>
            <Button size="small" onClick={() => navigate("/doctor/tasks")}>查看全部</Button>
          </Stack>
          <Stack spacing={0.8} sx={{ mb: 3 }}>
            {pendingTasks.map((task) => {
              const isOverdue = task.due_at && new Date(task.due_at) < new Date();
              return (
                <Card key={task.id} variant="outlined" sx={{ borderRadius: 1.5 }}>
                  <CardContent sx={{ py: 1, px: 1.5, "&:last-child": { pb: 1 } }}>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>{task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}</Typography>
                        {task.due_at && (
                          <Typography variant="caption" sx={{ color: isOverdue ? "error.main" : "text.secondary" }}>
                            {isOverdue ? "已逾期 · " : "到期 · "}{task.due_at.slice(0, 10)}
                          </Typography>
                        )}
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>
              );
            })}
          </Stack>
        </>
      )}

      {/* Recent records */}
      {recentRecords.length > 0 && (
        <>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>最近病历</Typography>
            <Button size="small" onClick={() => navigate("/doctor/patients")}>查看患者</Button>
          </Stack>
          <Stack spacing={0.8}>
            {recentRecords.map((r) => (
              <Card key={r.id} variant="outlined" sx={{ borderRadius: 1.5 }}>
                <CardContent sx={{ py: 1, px: 1.5, "&:last-child": { pb: 1 } }}>
                  <Stack direction="row" alignItems="center" spacing={1.5}>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {r.patient_name || "未知患者"}
                        {(Array.isArray(r.tags) ? r.tags : []).slice(0, 2).map((tag, i) => (
                          <Chip key={i} label={tag} size="small" sx={{ ml: 0.5, fontSize: 10, height: 18 }} />
                        ))}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {r.content ? (r.content.length > 40 ? r.content.slice(0, 40) + "…" : r.content) : "无记录"} · {r.created_at?.slice(0, 10)}
                      </Typography>
                    </Box>
                    {r.patient_id && (
                      <IconButton size="small" onClick={() => navigate(`/doctor/patients/${r.patient_id}`)}>
                        <PeopleOutlineIcon fontSize="small" />
                      </IconButton>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Stack>
        </>
      )}
    </Box>
  );
}

// ─── Settings section ────────────────────────────────────────────────────────

function SettingsSection({ doctorId }) {
  const [status, setStatus] = useState(null);       // { has_template, char_count }
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
      setDeleting(false); }
  }

  return (
    <Box sx={{ p: 3, maxWidth: 560 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>设置</Typography>

      {/* Report template */}
      <Card variant="outlined" sx={{ borderRadius: 2, mb: 2 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <UploadFileOutlinedIcon fontSize="small" color="primary" />
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>门诊病历报告模板</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            上传您医院的门诊病历模板（PDF、Word 或图片），AI 将参照模板格式生成报告。
            支持格式：PDF、DOCX、DOC、TXT、JPG、PNG，最大 1 MB。
          </Typography>

          {loading ? <CircularProgress size={18} /> : (
            <>
              {status?.has_template ? (
                <Alert severity="success" sx={{ mb: 1.5 }}>
                  已上传自定义模板（{status.char_count?.toLocaleString()} 字符）
                </Alert>
              ) : (
                <Alert severity="info" sx={{ mb: 1.5 }}>
                  暂未上传模板，将使用国家卫生部2010年标准格式
                </Alert>
              )}
              {msg.text && (
                <Alert severity={msg.type || "info"} sx={{ mb: 1.5 }} onClose={() => setMsg({ type: "", text: "" })}>
                  {msg.text}
                </Alert>
              )}
              <Stack direction="row" spacing={1}>
                <Button
                  variant="contained" size="small"
                  startIcon={uploading ? <CircularProgress size={14} /> : <UploadFileOutlinedIcon />}
                  disabled={uploading || deleting}
                  onClick={() => fileRef.current?.click()}
                >
                  {uploading ? "上传中…" : status?.has_template ? "替换模板" : "上传模板"}
                </Button>
                {status?.has_template && (
                  <Button variant="outlined" color="error" size="small" disabled={deleting || uploading}
                    onClick={handleDelete}>
                    {deleting ? "删除中…" : "删除模板"}
                  </Button>
                )}
              </Stack>
              <input ref={fileRef} type="file" hidden
                accept=".pdf,.docx,.doc,.txt,image/jpeg,image/png,image/webp"
                onChange={handleUpload} />
            </>
          )}
        </CardContent>
      </Card>
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
  // Selected patient name for mobile topbar
  const [selectedPatientName, setSelectedPatientName] = useState("");

  // Onboarding dialog state
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardName, setOnboardName] = useState("");
  const [onboardSaving, setOnboardSaving] = useState(false);

  const activeSection = patientId ? "patients" : (section || "home");

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
    <Box sx={{ display: "flex", height: "100vh", background: "#f8fafb" }}>
      {/* Sidebar — desktop only */}
      {!isMobile && (
        <Box sx={{
          width: 220, flexShrink: 0, borderRight: "1px solid #e2e8f0",
          backgroundColor: "#fff", display: "flex", flexDirection: "column", py: 2, px: 1.5,
        }}>
          {/* Header */}
          <Box sx={{ mb: 3, px: 0.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "primary.main" }}>医生工作台</Typography>
            <Typography variant="caption" color="text.secondary">{doctorName || doctorId}</Typography>
          </Box>

          {/* Nav */}
          <Stack spacing={0.5} sx={{ flex: 1 }}>
            {NAV.map((item) => (
              <NavBtn key={item.key} active={activeSection === item.key} icon={item.icon} onClick={() => handleNav(item.key)} badgeCount={navBadge[item.key] || 0}>
                {item.label}
              </NavBtn>
            ))}
          </Stack>

          {/* Footer */}
          <Button
            startIcon={<LogoutIcon fontSize="small" />}
            onClick={handleLogout}
            size="small"
            sx={{ justifyContent: "flex-start", color: "text.secondary", mt: 1 }}
          >
            退出登录
          </Button>
        </Box>
      )}

      {/* Main content */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", pb: isMobile ? "56px" : 0 }}>
        {/* Topbar — hidden for chat (ChatSection has its own) */}
        {activeSection !== "chat" && (
          <Box sx={{ px: 3, py: 1.5, borderBottom: "1px solid #e2e8f0", backgroundColor: "#fff" }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "text.secondary" }}>
              {activeSection === "home" && "首页"}
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
          <Alert severity="warning" sx={{ mx: 2, mt: 1.5, borderRadius: 1.5 }}
            action={
              <Stack direction="row" spacing={1}>
                <Button size="small" color="success" variant="contained" onClick={handleConfirmPending}>确认保存</Button>
                <Button size="small" color="error" variant="outlined" onClick={handleAbandonPending}>撤销</Button>
              </Stack>
            }
          >
            <AlertTitle>待确认病历草稿</AlertTitle>
            患者：{pendingRecord.patient_name || "未关联"} · {pendingRecord.content_preview}
          </Alert>
        )}

        {/* Section content */}
        <Box sx={{ flex: 1, overflow: "hidden" }}>
          {activeSection === "chat" && (
            <ChatSection
              doctorId={doctorId}
              onMessageCountChange={() => {}}
              externalInput={chatInsertText}
              onExternalInputConsumed={() => setChatInsertText("")}
            />
          )}
          {activeSection === "home" && <HomeSection doctorId={doctorId} navigate={navigate} />}
          {activeSection === "patients" && (
            <PatientsSection
              doctorId={doctorId}
              onNavigateToChat={() => navigate("/doctor/chat")}
              onInsertChatText={(text) => { setChatInsertText(text); navigate("/doctor/chat"); }}
              onPatientSelected={(name) => setSelectedPatientName(name || "")}
            />
          )}
          {activeSection === "tasks" && <TasksSection doctorId={doctorId} />}
          {activeSection === "settings" && <SettingsSection doctorId={doctorId} />}
        </Box>
      </Box>

      {/* Bottom navigation — mobile only */}
      {isMobile && (
        <Box sx={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 10, borderTop: "1px solid #e2e8f0" }}>
          <BottomNavigation
            value={activeSection}
            onChange={(_, val) => handleNav(val)}
            sx={{ height: 56 }}
          >
            {NAV.map((item) => (
              <BottomNavigationAction
                key={item.key}
                label={item.label}
                value={item.key}
                icon={
                  item.key === "tasks" && pendingTaskCount > 0
                    ? <Badge badgeContent={pendingTaskCount} color="error">{item.icon}</Badge>
                    : item.key === "chat" && pendingRecord
                    ? <Badge variant="dot" color="warning">{item.icon}</Badge>
                    : item.icon
                }
                sx={{ minWidth: 0, fontSize: 10 }}
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
