/**
 * @route /doctor/patients, /doctor/patients/:patientId
 *
 * 患者列表面板：支持按姓名搜索、自然语言智能搜索、PDF 导入，以及选中后展示详情。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, InputAdornment,
  Stack, TextField, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import SearchIcon from "@mui/icons-material/Search";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import AskAIBar from "../../components/AskAIBar";
import BarButton from "../../components/BarButton";
import NewItemCard from "../../components/NewItemCard";
import PageSkeleton from "../../components/PageSkeleton";
import ListCard from "../../components/ListCard";
import SectionLabel from "../../components/SectionLabel";
import StatusBadge from "../../components/StatusBadge";
import NameAvatar from "../../components/NameAvatar";
import EmptyState from "../../components/EmptyState";
import SectionLoading from "../../components/SectionLoading";
import PatientDetail, { PatientChatPage } from "./patients/PatientDetail";
import SubpageHeader from "../../components/SubpageHeader";
import RecordEditDialog from "../../components/RecordEditDialog";
import AppButton from "../../components/AppButton";
import { STRUCTURED_FIELD_LABELS } from "./constants";
import InterviewPage from "./InterviewPage";
import SheetDialog from "../../components/SheetDialog";
import PersonAddOutlinedIcon from "@mui/icons-material/PersonAddOutlined";
import { TYPE, ICON, COLOR, RADIUS } from "../../theme";

function groupPatients(list) {
  const groups = {};
  list.forEach((p) => {
    const k = (p.name || "#")[0];
    (groups[k] = groups[k] || []).push(p);
  });
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b, "zh-CN"));
}

function isNLQuery(q) {
  return /[的得了这那哪]{1}|姓|阿姨|叔叔|奶奶|大爷|多岁|中年|老年|男性|女性|上周|本周|最近|昨天/.test(q);
}

import { relativeDate } from "../../utils/time";
const formatPatientTime = relativeDate;

/* Triage badge: urgent → red "紧急", symptom/side_effect → amber "待处理" */
function TriageDot({ triageCategory }) {
  if (!triageCategory) return null;
  let color = null;
  let label = null;
  if (triageCategory === "urgent") { color = COLOR.danger; label = "紧急"; }
  else if (triageCategory === "symptom_report" || triageCategory === "side_effect") { color = COLOR.warning; label = "待处理"; }
  if (!color) return null;
  return (
    <Box component="span" sx={{
      display: "inline-block", fontSize: 10, fontWeight: 600,
      px: 0.5, py: 0.5, borderRadius: RADIUS.sm,
      bgcolor: color, color: COLOR.white, lineHeight: 1.5,
      flexShrink: 0, ml: 0.5,
    }}>
      {label}
    </Box>
  );
}

function PatientRow({ patient, aiTag, onClick }) {
  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;
  const timeStr = formatPatientTime(patient.last_activity_at || patient.updated_at || patient.created_at);
  const baseSub = [
    patient.gender ? ({ male: "男", female: "女" }[patient.gender] || patient.gender) : null,
    age ? `${age}岁` : null,
    patient.chief_complaint || patient.primary_category || `${patient.record_count}份病历`,
  ].filter(Boolean).join(" · ");
  const subtitle = aiTag
    ? (
        <Box component="span">
          {baseSub} · <Box component="span" sx={{ color: COLOR.primary }}>AI: {aiTag}</Box>
        </Box>
      )
    : baseSub;
  const triageCategory = patient.latest_triage_category || patient.triage_category;
  return (
    <ListCard
      avatar={<NameAvatar name={patient.name} size={36} />}
      title={
        <Box component="span" sx={{ display: "inline-flex", alignItems: "center" }}>
          {patient.name}
          <TriageDot triageCategory={triageCategory} />
        </Box>
      }
      subtitle={subtitle}
      right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{timeStr}</Typography>}
      onClick={onClick}
    />
  );
}

const URGENCY_COLOR_MAP = {
  "紧急": COLOR.danger,
  "待处理": COLOR.warning,
};

function AIAttentionSection({ attention, navigate }) {
  if (!attention?.patients?.length) return null;
  return (
    <>
      <SectionLabel>AI建议关注</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, mb: 1 }}>
        {attention.patients.map((p, i) => (
          <ListCard
            key={p.patient_id || i}
            avatar={<NameAvatar name={p.patient_name || "?"} size={36} />}
            title={p.patient_name || "患者"}
            subtitle={p.reason}
            onClick={() => p.patient_id ? navigate(`/doctor/patients/${p.patient_id}`) : undefined}
            right={
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <StatusBadge
                  label={p.urgency === "urgent" ? "紧急" : "待处理"}
                  colorMap={URGENCY_COLOR_MAP}
                />
              </Box>
            }
          />
        ))}
      </Box>
    </>
  );
}

function ImportCard({ importing, importError, onFileClick, onChatClick }) {
  return (
    <Box sx={{ bgcolor: COLOR.surface, borderBottom: `1px solid ${COLOR.border}` }}>
      <Box sx={{ px: 2, py: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, fontWeight: 600, letterSpacing: 0.3 }}>导入患者</Typography>
      </Box>
      <Box onClick={onFileClick}
        sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1, bgcolor: COLOR.white,
          borderBottom: `1px solid ${COLOR.borderLight}`, cursor: "pointer", userSelect: "none", WebkitUserSelect: "none",
          "&:hover": { bgcolor: COLOR.surface }, "&:active": { bgcolor: COLOR.surfaceAlt } }}>
        <Box sx={{ width: 36, height: 36, borderRadius: RADIUS.md, bgcolor: COLOR.successLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          {importing ? <CircularProgress size={18} sx={{ color: COLOR.primary }} /> : <UploadFileOutlinedIcon sx={{ fontSize: ICON.lg, color: COLOR.primary }} />}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500 }}>{importing ? "解析中…" : "上传 PDF / 图片"}</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>出院小结、检验报告、门诊病历</Typography>
        </Box>
        <KeyboardArrowDownIcon sx={{ fontSize: ICON.md, color: COLOR.text4, transform: "rotate(-90deg)" }} />
      </Box>
      <Box onClick={onChatClick}
        sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1, bgcolor: COLOR.white,
          cursor: "pointer", "&:hover": { bgcolor: COLOR.surface }, "&:active": { bgcolor: COLOR.surfaceAlt } }}>
        <Box sx={{ width: 36, height: 36, borderRadius: RADIUS.md, bgcolor: COLOR.accentLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <ChatOutlinedIcon sx={{ fontSize: ICON.lg, color: COLOR.accent }} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500 }}>粘贴微信聊天记录</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>在聊天框直接粘贴，自动提取创建</Typography>
        </Box>
        <KeyboardArrowDownIcon sx={{ fontSize: ICON.md, color: COLOR.text4, transform: "rotate(-90deg)" }} />
      </Box>
      {importError && (
        <Box sx={{ px: 2, py: 1, bgcolor: COLOR.dangerLight }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger }}>{importError}</Typography>
        </Box>
      )}
    </Box>
  );
}

function SearchBar({ patients, search, nlResults, nlLoading, onChange, onSubmit, onSelect, onStartInterview }) {
  return (
    <Box sx={{ px: 1.5, py: 1, borderBottom: `0.5px solid ${COLOR.borderLight}`, bgcolor: COLOR.surfaceAlt }}>
      <Autocomplete
        freeSolo
        options={patients}
        getOptionLabel={(option) => typeof option === "string" ? option : option.name}
        inputValue={search}
        onInputChange={(_, value, reason) => {
          if (reason === "input") onChange(value);
        }}
        onChange={(_, value) => {
          if (value && typeof value !== "string" && value.id) {
            onSelect?.(value);
          }
        }}
        filterOptions={(options, { inputValue }) => {
          const q = inputValue.trim();
          if (!q) return options.slice(0, 8);
          const filtered = options.filter((p) => p.name.includes(q));
          // Add "create new" option
          if (q && !filtered.some((p) => p.name === q)) {
            filtered.push({ _create: true, name: q });
          }
          return filtered.slice(0, 10);
        }}
        renderOption={(props, option) => {
          if (option._create) {
            return (
              <Box component="li" {...props} key="__create__"
                onClick={(e) => { e.stopPropagation(); onStartInterview?.(); }}
                sx={{ color: COLOR.primary, fontWeight: 500, fontSize: TYPE.secondary.fontSize }}>
                + 新建患者「{option.name}」
              </Box>
            );
          }
          const age = option.year_of_birth ? new Date().getFullYear() - option.year_of_birth : null;
          const genderStr = option.gender ? ({ male: "男", female: "女" }[option.gender] || "") : "";
          return (
            <Box component="li" {...props} key={option.id}
              sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.5 }}>
              <NameAvatar name={option.name} size={28} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 500 }} noWrap>
                  {option.name}
                </Typography>
                <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }} noWrap>
                  {[genderStr, age ? `${age}岁` : null].filter(Boolean).join(" · ")}
                </Typography>
              </Box>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
                {formatPatientTime(option.last_activity_at || option.updated_at || "")}
              </Typography>
            </Box>
          );
        }}
        renderInput={(params) => (
          <TextField
            {...params}
            size="small"
            fullWidth
            placeholder={`搜索患者${patients.length > 0 ? ` (共${patients.length}人)` : ""}，或用自然语言描述`}
            onKeyDown={(e) => e.key === "Enter" && onSubmit()}
            InputProps={{
              ...params.InputProps,
              startAdornment: (
                <InputAdornment position="start">
                  {nlLoading ? <CircularProgress size={14} /> : <SearchIcon fontSize="small" />}
                </InputAdornment>
              ),
            }}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.sm, bgcolor: COLOR.white } }}
          />
        )}
        noOptionsText="未找到患者"
        loading={nlLoading}
        sx={{ "& .MuiAutocomplete-listbox": { py: 0.5 } }}
      />
      {nlResults !== null && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, pt: 0.5 }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>智能搜索结果 ({nlResults.length}人)</Typography>
          <Box onClick={() => onChange("")} sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, cursor: "pointer" }}>清除</Box>
        </Box>
      )}
    </Box>
  );
}


function PatientList({ filtered, search, selectedId, isMobile, navigate, onStartInterview, aiTagMap }) {
  if (!filtered.length && search.trim()) {
    return (
      <Box sx={{ p: 2 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          未找到患者「{search.trim()}」
        </Typography>
        <Chip label={`创建 ${search.trim()}`} size="small" clickable color="primary" variant="outlined"
          onClick={() => onStartInterview?.()} />
      </Box>
    );
  }
  if (!filtered.length) {
    return (
      <EmptyState title="暂无患者档案" subtitle={'点击"新建患者"或在聊天中创建'} />
    );
  }
  return filtered.map((p) => (
    <PatientRow key={p.id} patient={p} isSelected={p.id === selectedId}
      aiTag={aiTagMap?.[p.id]}
      isMobile={isMobile} onClick={() => navigate(`/doctor/patients/${p.id}`)} />
  ));
}

function PatientListPane({ patients, loading, error, search, nlResults, nlLoading, filtered, selectedId, isMobile, importing, importError, importFileRef, navigate, onSearchChange, onSearchSubmit, onStartInterview, onLoad, onFileInputChange, attention, aiTagMap }) {
  return (
    <>
      <SearchBar patients={patients} search={search} nlResults={nlResults} nlLoading={nlLoading} onChange={onSearchChange} onSubmit={onSearchSubmit} onSelect={(patient) => navigate(`/doctor/patients/${patient.id}`)} onStartInterview={onStartInterview} />
      {error && <Alert severity="error" action={<Button size="small" onClick={onLoad}>重试</Button>}>{error}</Alert>}
      <Box sx={{ flex: 1, overflowY: "auto", bgcolor: COLOR.surfaceAlt }}>
        {loading && <SectionLoading py={2} />}
        {!loading && !search.trim() && <NewItemCard title="新建患者" subtitle="添加新的患者档案" onClick={onStartInterview} />}
        <input ref={importFileRef} type="file" hidden accept=".pdf,image/jpeg,image/png,image/webp" onChange={onFileInputChange} />
        {!loading && (
          <SectionLabel sx={{ bgcolor: COLOR.surface, borderTop: `0.5px solid ${COLOR.borderLight}`, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            最近 · {filtered.length}位患者
          </SectionLabel>
        )}
        {!loading && (
          <PatientList filtered={filtered} search={search} selectedId={selectedId}
            isMobile={isMobile} navigate={navigate}
            onStartInterview={onStartInterview} aiTagMap={aiTagMap} />
        )}
      </Box>
    </>
  );
}

async function extractAndSend({ file, extractFileForChat, onAutoSendToChat, setImportError }) {
  const { text } = await extractFileForChat(file);
  if (!text?.trim()) { setImportError("未能从文件中提取到文字，请尝试其他文件"); return; }
  const nameMatch =
    text.match(/(?:患者姓名|病人姓名|姓\s*名)[：:﹕]\s*([^\s\u3000，,（(]{2,6})/) ||
    text.match(/(?:送检者|申请人|患者)[：:﹕]\s*([^\s\u3000，,（(]{2,6})/) ||
    text.match(/(?:报告对象|受检者|体检者)[：:﹕]\s*([^\s\u3000，,（(]{2,6})/);
  const prefix = nameMatch ? `录入患者【${nameMatch[1]}】的病历：\n` : "";
  onAutoSendToChat?.(prefix + text.trim());
}

function usePatientsState({ doctorId, onPatientSelected, onAutoSendToChat, selectedId, refreshKey }) {
  const { getPatients, searchPatients, extractFileForChat, fetchAIAttention } = useApi();
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [nlResults, setNlResults] = useState(null);
  const [nlLoading, setNlLoading] = useState(false);
  const importFileRef = useRef(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");
  const [attention, setAttention] = useState(null);

  const selectedPatient = patients.find((p) => p.id === selectedId) || null;
  useEffect(() => { onPatientSelected?.(selectedPatient?.name || ""); }, [selectedPatient?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    setLoading(true); setError("");
    getPatients(doctorId, {}, 200).then((d) => setPatients(d.items || [])).catch((e) => setError(e.message || "加载失败")).finally(() => setLoading(false));
  }, [doctorId]);
  useEffect(() => { load(); }, [load, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch AI attention data
  useEffect(() => {
    if (!doctorId || typeof fetchAIAttention !== "function") return;
    fetchAIAttention(doctorId)
      .then((d) => setAttention(d))
      .catch(() => {}); // silent fail — attention is non-critical
  }, [doctorId, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build a map of patient_id → short AI reason for inline tags in the patient list
  const aiTagMap = {};
  if (attention?.patients) {
    for (const p of attention.patients) {
      if (p.patient_id) {
        // Use a short label derived from the reason
        aiTagMap[p.patient_id] = p.short_tag || p.reason?.slice(0, 12) || "关注";
      }
    }
  }

  function handleSearchChange(val) { setSearch(val); setNlResults(null); }
  function handleSearchSubmit() {
    const q = search.trim(); if (!q || !isNLQuery(q)) return;
    setNlLoading(true);
    searchPatients(doctorId, q).then((d) => setNlResults(d.items || [])).catch(() => setNlResults([])).finally(() => setNlLoading(false));
  }
  async function handleImportFile(e) {
    const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
    setImporting(true); setImportError("");
    try { await extractAndSend({ file, extractFileForChat, onAutoSendToChat, setImportError }); }
    catch (err) { setImportError(err?.message === "Request timed out" ? "文件较大，解析超时，请尝试上传页数更少的 PDF" : "文件解析失败，请重试"); }
    finally { setImporting(false); }
  }

  const filtered = (() => {
    const q = search.trim();
    const base = !q ? patients : (nlResults !== null ? nlResults : patients.filter((p) => p.name.includes(q)));
    // Sort: patients with pending actions first, then by most recent activity
    return [...base].sort((a, b) => {
      const aHasTag = aiTagMap?.[a.id] ? 1 : 0;
      const bHasTag = aiTagMap?.[b.id] ? 1 : 0;
      if (aHasTag !== bHasTag) return bHasTag - aHasTag; // tagged first
      const aDate = a.last_activity_at || a.created_at || "";
      const bDate = b.last_activity_at || b.created_at || "";
      return bDate.localeCompare(aDate); // most recent first
    });
  })();
  return { patients, setPatients, loading, error, search, nlResults, nlLoading, importing, importError, importFileRef, filtered, selectedPatient, load, handleSearchChange, handleSearchSubmit, handleImportFile, attention, aiTagMap };
}

function MobilePatientDetailView({ selectedPatient, doctorId, navigate, onStartInterview }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <PatientDetail patient={selectedPatient} doctorId={doctorId} onStartInterview={onStartInterview} />
      </Box>
    </Box>
  );
}

const RECORD_FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "family_history", "personal_history", "marital_reproductive",
  "physical_exam", "specialist_exam", "auxiliary_exam",
  "diagnosis", "treatment_plan", "orders_followup",
];

function RecordDetailSubpage({ recordId, doctorId, patientName, onBack, onDeleted }) {
  const api = useApi();
  const { getTaskRecord } = api;
  const [record, setRecord] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);

  const load = useCallback(() => {
    if (!recordId) return;
    setLoading(true);
    getTaskRecord(recordId, doctorId)
      .then(setRecord)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [recordId, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);

  const structured = record?.structured || {};
  const filled = RECORD_FIELD_ORDER.filter((k) => structured[k]);
  const typeLabel = record?.record_type ? ({ visit: "门诊", dictation: "口述", import: "导入", interview_summary: "预问诊", lab: "检验", imaging: "影像", surgery: "手术", referral: "转诊" }[record.record_type] || record.record_type) : "";
  const date = record?.created_at ? record.created_at.slice(0, 10) : "";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title={`${patientName} · ${typeLabel || "病历"}`} onBack={onBack}
      />
      <Box sx={{ flex: 1, overflow: "auto" }}>
        {loading && <SectionLoading />}
        {!loading && !record && (
          <Box sx={{ py: 6, textAlign: "center" }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>病历不存在</Typography>
          </Box>
        )}
        {!loading && record && (
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
            {/* Header */}
            <Box sx={{ px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>{typeLabel}</Typography>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{date}</Typography>
              </Box>
              {record.content && !filled.length && (
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, mt: 0.5, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                  {record.content}
                </Typography>
              )}
            </Box>
            {/* Structured fields */}
            {filled.map((key) => (
              <Box key={key} sx={{ display: "flex", gap: 1.5, px: 2, py: 1, borderBottom: `0.5px solid ${COLOR.borderLight}`, "&:last-child": { borderBottom: "none" } }}>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, fontWeight: 500, flexShrink: 0, minWidth: 56 }}>
                  {STRUCTURED_FIELD_LABELS[key]}
                </Typography>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                  {structured[key]}
                </Typography>
              </Box>
            ))}
          </Box>
        )}
        {record && (
          <Box sx={{ px: 2, pt: 1.5, pb: "calc(12px + env(safe-area-inset-bottom))", bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}` }}>
            <AppButton variant="secondary" size="md" fullWidth onClick={() => setEditOpen(true)}>编辑病历</AppButton>
          </Box>
        )}
      </Box>
      <RecordEditDialog open={editOpen} record={record} doctorId={doctorId}
        onClose={() => setEditOpen(false)}
        onUpdated={(updated) => { setRecord({ ...record, ...updated }); setEditOpen(false); }}
        onDeleted={() => { setEditOpen(false); onDeleted?.(); }} />
    </Box>
  );
}

export default function PatientsPage({ doctorId, onNavigateToChat, onInsertChatText, onAutoSendToChat, onPatientSelected, refreshKey = 0, triggerInterview, onTriggerInterviewConsumed, chatInterviewSessionId, onChatInterviewSessionConsumed, chatInterviewPrePopulated }) {
  const { patientId } = useParams();
  const navigate = useAppNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const selectedId = patientId ? Number(patientId) : null;
  const { patients, setPatients, loading, error, search, nlResults, nlLoading, importing, importError, importFileRef, filtered, selectedPatient, load, handleSearchChange, handleSearchSubmit, handleImportFile, attention, aiTagMap } = usePatientsState({ doctorId, onPatientSelected, onAutoSendToChat, selectedId, refreshKey });

  const [interviewActive, setInterviewActive] = useState(patientId === "new");

  // URL-driven: /doctor/patients/new opens interview
  useEffect(() => {
    if (patientId === "new") setInterviewActive(true);
  }, [patientId]);

  // URL-driven: ?action=new opens patient picker (from home page shortcut)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") === "new" && !interviewActive) {
      setShowPatientPicker(true);
      // Clean URL
      params.delete("action");
      const clean = params.toString();
      window.history.replaceState({}, "", window.location.pathname + (clean ? "?" + clean : ""));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // When triggerInterview is set from chat section, activate interview mode
  useEffect(() => {
    if (triggerInterview) {
      setInterviewActive(true);
      onTriggerInterviewConsumed?.();
    }
  }, [triggerInterview]); // eslint-disable-line react-hooks/exhaustive-deps

  const [triggerExport, setTriggerExport] = useState(false);

  const [interviewPatient, setInterviewPatient] = useState(null);
  const [showPatientPicker, setShowPatientPicker] = useState(false);

  function handleStartInterview(patientOrEvent) {
    // Called from buttons with no arg (event), or with explicit patient object
    const patient = (patientOrEvent && patientOrEvent.id && patientOrEvent.name) ? patientOrEvent : selectedPatient;
    if (patient) {
      // Patient already known — skip picker
      setInterviewPatient(patient);
      setInterviewActive(true);
      navigate("/doctor/patients/new");
    } else {
      // No patient context — show picker
      setShowPatientPicker(true);
    }
  }

  function handlePickPatient(patient) {
    setShowPatientPicker(false);
    setInterviewPatient(patient || null);
    setInterviewActive(true);
    navigate("/doctor/patients/new");
  }

  const listPaneProps = { patients, loading, error, search, nlResults, nlLoading, filtered, selectedId, isMobile, importing, importError, importFileRef, navigate, onSearchChange: handleSearchChange, onSearchSubmit: handleSearchSubmit, onStartInterview: handleStartInterview, onLoad: load, onFileInputChange: handleImportFile, attention, aiTagMap };

  // Detect ?view=chat for dedicated chat subpage
  const viewParam = new URLSearchParams(window.location.search).get("view");

  // Mobile subpage override: interview, chat, or patient detail
  const mobileSubpage = isMobile && interviewActive ? (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surface }}>
      <InterviewPage doctorId={doctorId}
        sessionId={chatInterviewSessionId}
        patientContext={interviewPatient}
        prePopulated={chatInterviewPrePopulated}
        onComplete={() => { setInterviewActive(false); setInterviewPatient(null); onChatInterviewSessionConsumed?.(); load(); }}
        onCancel={() => { setInterviewActive(false); setInterviewPatient(null); onChatInterviewSessionConsumed?.(); navigate(-1); }} />
    </Box>
  ) : isMobile && selectedId && viewParam === "record" ? (
    <RecordDetailSubpage
      recordId={Number(new URLSearchParams(window.location.search).get("record"))}
      doctorId={doctorId}
      patientName={selectedPatient?.name || ""}
      onBack={() => navigate(`/doctor/patients/${selectedId}`, { replace: true })}
      onDeleted={() => { load(); navigate(`/doctor/patients/${selectedId}`, { replace: true }); }}
    />
  ) : selectedId && viewParam === "chat" ? (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt, overflow: "hidden" }}>
      <SubpageHeader title={`${selectedPatient?.name || ""} · 消息`} onBack={() => navigate(-1)} sx={{ flexShrink: 0 }} />
      <Box sx={{ flex: 1, overflow: "auto" }}>
        <PatientChatPage patientId={selectedId} doctorId={doctorId} bubbleView patientName={selectedPatient?.name} />
      </Box>
    </Box>
  ) : isMobile && selectedId ? (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surface }}>
      <SubpageHeader title={selectedPatient?.name || ""} onBack={() => navigate("/doctor/patients")} />
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <PatientDetail patient={selectedPatient} doctorId={doctorId} onStartInterview={handleStartInterview}
          triggerExport={triggerExport} onTriggerExportConsumed={() => setTriggerExport(false)} />
      </Box>
    </Box>
  ) : null;

  const detailContent = interviewActive ? (
    <InterviewPage doctorId={doctorId}
      sessionId={chatInterviewSessionId}
      prePopulated={chatInterviewPrePopulated}
      onComplete={() => { setInterviewActive(false); onChatInterviewSessionConsumed?.(); load(); }}
      onCancel={() => { setInterviewActive(false); onChatInterviewSessionConsumed?.(); navigate(-1); }} />
  ) : (
    <PatientDetail patient={selectedPatient} doctorId={doctorId}
      onDeleted={(id) => { setPatients((prev) => prev.filter((p) => p.id !== id)); navigate("/doctor/patients"); }}
      onStartInterview={handleStartInterview}
      triggerExport={triggerExport} onTriggerExportConsumed={() => setTriggerExport(false)} />
  );

  return (
    <>
      <PageSkeleton
        title="患者"
        isMobile={isMobile}
        mobileView={mobileSubpage}
        listPane={<PatientListPane {...listPaneProps} />}
        detailPane={selectedPatient || interviewActive ? detailContent : null}
      />
      {/* Patient picker sheet — shown when starting interview without a patient */}
      <SheetDialog open={showPatientPicker} onClose={() => setShowPatientPicker(false)} title="选择患者">
        <NewItemCard title="新建患者" subtitle="在对话中输入患者信息" onClick={() => handlePickPatient(null)} />
        {patients.map((p) => {
          const genderZh = p.gender === "male" ? "男" : p.gender === "female" ? "女" : p.gender || "";
          return (
            <ListCard
              key={p.id}
              avatar={<NameAvatar name={p.name} size={36} />}
              title={p.name}
              subtitle={[genderZh, p.age ? `${p.age}岁` : null].filter(Boolean).join(" · ") || ""}
              chevron
              onClick={() => handlePickPatient(p)}
              sx={{ borderBottom: `1px solid ${COLOR.borderLight}` }}
            />
          );
        })}
        {patients.length === 0 && (
          <Typography sx={{ px: 2, py: 3, color: COLOR.text4, fontSize: TYPE.secondary.fontSize, textAlign: "center" }}>
            暂无患者记录
          </Typography>
        )}
      </SheetDialog>
    </>
  );
}
