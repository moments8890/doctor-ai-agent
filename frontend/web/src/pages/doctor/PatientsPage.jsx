/**
 * @route /doctor/patients, /doctor/patients/:patientId
 *
 * 患者列表面板：支持按姓名搜索、自然语言智能搜索、PDF 导入，以及选中后展示详情。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Alert, Box, Button, Chip, CircularProgress, InputAdornment,
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
import PatientAvatar from "../../components/PatientAvatar";
import PatientDetail from "./patients/PatientDetail";
import SubpageHeader from "../../components/SubpageHeader";
import InterviewPage from "./InterviewPage";
import { TYPE, ICON, COLOR } from "../../theme";

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

function formatPatientTime(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (dt.getTime() === today.getTime()) return `今天 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (dt.getTime() === yesterday.getTime()) return "昨天";
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

/* Triage dot: urgent → red, symptom_report/side_effect → amber, others → hidden */
function TriageDot({ triageCategory }) {
  if (!triageCategory) return null;
  let color = null;
  if (triageCategory === "urgent") color = COLOR.danger;
  else if (triageCategory === "symptom_report" || triageCategory === "side_effect") color = COLOR.warning;
  if (!color) return null;
  return (
    <Box component="span" sx={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", bgcolor: color, flexShrink: 0, ml: 0.5 }} />
  );
}

function PatientRow({ patient, aiTag, onClick }) {
  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;
  const timeStr = formatPatientTime(patient.updated_at || patient.created_at);
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
      avatar={<PatientAvatar name={patient.name} size={36} />}
      title={
        <Box component="span" sx={{ display: "inline-flex", alignItems: "center" }}>
          {patient.name}
          <TriageDot triageCategory={triageCategory} />
        </Box>
      }
      subtitle={subtitle}
      right={<Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>{timeStr}</Typography>}
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
            avatar={<PatientAvatar name={p.patient_name || "?"} size={36} />}
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
    <Box sx={{ bgcolor: "#f7f7f7", borderBottom: "1px solid #e5e5e5" }}>
      <Box sx={{ px: 2, py: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#aaa", fontWeight: 600, letterSpacing: 0.3 }}>导入患者</Typography>
      </Box>
      <Box onClick={onFileClick}
        sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2, bgcolor: "#fff",
          borderBottom: "1px solid #f2f2f2", cursor: "pointer", userSelect: "none", WebkitUserSelect: "none",
          "&:hover": { bgcolor: "#f5f5f5" }, "&:active": { bgcolor: "#ebebeb" } }}>
        <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#e8f5e9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          {importing ? <CircularProgress size={18} sx={{ color: "#07C160" }} /> : <UploadFileOutlinedIcon sx={{ fontSize: ICON.lg, color: "#07C160" }} />}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500 }}>{importing ? "解析中…" : "上传 PDF / 图片"}</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#aaa" }}>出院小结、检验报告、门诊病历</Typography>
        </Box>
        <KeyboardArrowDownIcon sx={{ fontSize: ICON.md, color: "#ccc", transform: "rotate(-90deg)" }} />
      </Box>
      <Box onClick={onChatClick}
        sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2, bgcolor: "#fff",
          cursor: "pointer", "&:hover": { bgcolor: "#f5f5f5" }, "&:active": { bgcolor: "#ebebeb" } }}>
        <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#e3f2fd", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <ChatOutlinedIcon sx={{ fontSize: ICON.lg, color: "#1976d2" }} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500 }}>粘贴微信聊天记录</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#aaa" }}>在聊天框直接粘贴，自动提取创建</Typography>
        </Box>
        <KeyboardArrowDownIcon sx={{ fontSize: ICON.md, color: "#ccc", transform: "rotate(-90deg)" }} />
      </Box>
      {importError && (
        <Box sx={{ px: 2, py: 0.8, bgcolor: "#fff3f3" }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#FA5151" }}>{importError}</Typography>
        </Box>
      )}
    </Box>
  );
}

function SearchBar({ patients, search, nlResults, nlLoading, onChange, onSubmit }) {
  const q = search.trim();
  const showNlBtn = q && isNLQuery(q) && nlResults === null;
  return (
    <Box sx={{ px: 1.5, py: 1, borderBottom: "0.5px solid #f0f0f0", bgcolor: "#ededed" }}>
      <TextField
        size="small" fullWidth
        placeholder={`搜索患者${patients.length > 0 ? ` (共${patients.length}人)` : ""}，或用自然语言描述`}
        value={search}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSubmit()}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              {nlLoading ? <CircularProgress size={14} /> : <SearchIcon fontSize="small" />}
            </InputAdornment>
          ),
          endAdornment: showNlBtn ? (
            <InputAdornment position="end">
              <Box onClick={onSubmit} sx={{ fontSize: TYPE.micro.fontSize, color: "#07C160", cursor: "pointer", whiteSpace: "nowrap", pr: 0.5 }}>
                智能搜索
              </Box>
            </InputAdornment>
          ) : null,
        }}
        sx={{ "& .MuiOutlinedInput-root": { borderRadius: "4px", bgcolor: "#fff" } }}
      />
      {nlResults !== null && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, pt: 0.5 }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#888" }}>智能搜索结果 ({nlResults.length}人)</Typography>
          <Box onClick={() => onChange("")} sx={{ fontSize: TYPE.micro.fontSize, color: "#07C160", cursor: "pointer" }}>清除</Box>
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
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 4, gap: 1 }}>
        <Typography variant="body2" color="text.disabled">暂无患者档案</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
          点击"新建患者"或在聊天中创建
        </Typography>
      </Box>
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
      <SearchBar patients={patients} search={search} nlResults={nlResults} nlLoading={nlLoading} onChange={onSearchChange} onSubmit={onSearchSubmit} />
      {error && <Alert severity="error" action={<Button size="small" onClick={onLoad}>重试</Button>}>{error}</Alert>}
      <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
        {loading && <Box sx={{ p: 2, textAlign: "center" }}><CircularProgress size={20} /></Box>}
        {!loading && !search.trim() && <AIAttentionSection attention={attention} navigate={navigate} />}
        {!loading && !search.trim() && <NewItemCard title="新建患者" subtitle="添加新的患者档案" onClick={onStartInterview} />}
        <input ref={importFileRef} type="file" hidden accept=".pdf,image/jpeg,image/png,image/webp" onChange={onFileInputChange} />
        {!loading && (
          <SectionLabel sx={{ bgcolor: "#f7f7f7", borderTop: "0.5px solid #f0f0f0", borderBottom: "0.5px solid #f0f0f0" }}>
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

  const filtered = (() => { const q = search.trim(); if (!q) return patients; if (nlResults !== null) return nlResults; return patients.filter((p) => p.name.includes(q)); })();
  return { patients, setPatients, loading, error, search, nlResults, nlLoading, importing, importError, importFileRef, filtered, selectedPatient, load, handleSearchChange, handleSearchSubmit, handleImportFile, attention, aiTagMap };
}

function MobilePatientDetailView({ selectedPatient, doctorId, navigate, onStartInterview }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <PatientDetail patient={selectedPatient} doctorId={doctorId} onStartInterview={onStartInterview} />
      </Box>
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

  // When triggerInterview is set from chat section, activate interview mode
  useEffect(() => {
    if (triggerInterview) {
      setInterviewActive(true);
      onTriggerInterviewConsumed?.();
    }
  }, [triggerInterview]); // eslint-disable-line react-hooks/exhaustive-deps

  const [triggerExport, setTriggerExport] = useState(false);

  const [interviewPatient, setInterviewPatient] = useState(null);

  function handleStartInterview(patientOrEvent) {
    // Called from buttons with no arg (event), or with explicit patient object
    const patient = (patientOrEvent && patientOrEvent.id && patientOrEvent.name) ? patientOrEvent : selectedPatient;
    setInterviewPatient(patient || null);
    setInterviewActive(true);
    navigate("/doctor/patients/new");
  }

  const listPaneProps = { patients, loading, error, search, nlResults, nlLoading, filtered, selectedId, isMobile, importing, importError, importFileRef, navigate, onSearchChange: handleSearchChange, onSearchSubmit: handleSearchSubmit, onStartInterview: handleStartInterview, onLoad: load, onFileInputChange: handleImportFile, attention, aiTagMap };

  // Mobile subpage override: interview or patient detail
  const mobileSubpage = isMobile && interviewActive ? (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <InterviewPage doctorId={doctorId}
        sessionId={chatInterviewSessionId}
        patientContext={interviewPatient}
        prePopulated={chatInterviewPrePopulated}
        onComplete={() => { setInterviewActive(false); setInterviewPatient(null); onChatInterviewSessionConsumed?.(); load(); }}
        onCancel={() => { setInterviewActive(false); setInterviewPatient(null); onChatInterviewSessionConsumed?.(); navigate(-1); }} />
    </Box>
  ) : isMobile && selectedId ? (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title={selectedPatient?.name || ""} onBack={() => navigate(-1)}
        right={
          <BarButton onClick={handleStartInterview}>门诊</BarButton>
        }
      />
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
    <PageSkeleton
      title="患者"
      isMobile={isMobile}
      mobileView={mobileSubpage}
      listPane={<PatientListPane {...listPaneProps} />}
      detailPane={selectedPatient || interviewActive ? detailContent : null}
    />
  );
}
