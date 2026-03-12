/**
 * 患者列表面板：支持按姓名搜索、自然语言智能搜索、PDF 导入，以及选中后展示详情。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert, Box, Button, Chip, CircularProgress, InputAdornment,
  Stack, TextField, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import SearchIcon from "@mui/icons-material/Search";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { getPatients, searchPatients, extractFileForChat } from "../../api";
import PatientAvatar from "./PatientAvatar";
import PatientDetail from "./PatientDetail";

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

function PatientRow({ patient, isSelected, isMobile, onClick }) {
  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;
  const avatarSize = isMobile ? 42 : 38;
  const fontSize = isMobile ? "15px" : "14px";
  return (
    <Box onClick={onClick}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5,
        px: 2, py: 1.2, bgcolor: isSelected ? "#f0faf4" : "#fff",
        cursor: "pointer", userSelect: "none", WebkitUserSelect: "none",
        "&:hover": isMobile ? undefined : { bgcolor: "#f5f5f5" },
        "&:active": { bgcolor: isMobile ? "#f5f5f5" : "#ebebeb" },
      }}>
      <PatientAvatar name={patient.name} size={avatarSize} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontWeight: 500, fontSize }}>{patient.name}</Typography>
        <Typography variant="caption" color="text.secondary">
          {[
            patient.gender ? ({ male: "男", female: "女" }[patient.gender] || patient.gender) : null,
            age ? `${age}岁` : null,
            `${patient.record_count}份病历`,
          ].filter(Boolean).join(" · ")}
        </Typography>
      </Box>
      {isSelected && <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "#07C160", flexShrink: 0 }} />}
    </Box>
  );
}

function ImportCard({ importing, importError, onFileClick, onChatClick }) {
  return (
    <Box sx={{ bgcolor: "#f7f7f7", borderBottom: "1px solid #e5e5e5" }}>
      <Box sx={{ px: 2, py: 0.5 }}>
        <Typography sx={{ fontSize: 11, color: "#aaa", fontWeight: 600, letterSpacing: 0.3 }}>导入患者</Typography>
      </Box>
      <Box onClick={onFileClick}
        sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2, bgcolor: "#fff",
          borderBottom: "1px solid #f2f2f2", cursor: "pointer", userSelect: "none", WebkitUserSelect: "none",
          "&:hover": { bgcolor: "#f5f5f5" }, "&:active": { bgcolor: "#ebebeb" } }}>
        <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#e8f5e9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          {importing ? <CircularProgress size={18} sx={{ color: "#07C160" }} /> : <UploadFileOutlinedIcon sx={{ fontSize: 20, color: "#07C160" }} />}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: 14, fontWeight: 500 }}>{importing ? "解析中…" : "上传 PDF / 图片"}</Typography>
          <Typography sx={{ fontSize: 12, color: "#aaa" }}>出院小结、检验报告、门诊病历</Typography>
        </Box>
        <KeyboardArrowDownIcon sx={{ fontSize: 18, color: "#ccc", transform: "rotate(-90deg)" }} />
      </Box>
      <Box onClick={onChatClick}
        sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.2, bgcolor: "#fff",
          cursor: "pointer", "&:hover": { bgcolor: "#f5f5f5" }, "&:active": { bgcolor: "#ebebeb" } }}>
        <Box sx={{ width: 36, height: 36, borderRadius: "8px", bgcolor: "#e3f2fd", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <ChatOutlinedIcon sx={{ fontSize: 20, color: "#1976d2" }} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: 14, fontWeight: 500 }}>粘贴微信聊天记录</Typography>
          <Typography sx={{ fontSize: 12, color: "#aaa" }}>在聊天框直接粘贴，自动提取创建</Typography>
        </Box>
        <KeyboardArrowDownIcon sx={{ fontSize: 18, color: "#ccc", transform: "rotate(-90deg)" }} />
      </Box>
      {importError && (
        <Box sx={{ px: 2, py: 0.8, bgcolor: "#fff3f3" }}>
          <Typography sx={{ fontSize: 12, color: "#e74c3c" }}>{importError}</Typography>
        </Box>
      )}
    </Box>
  );
}

function SearchBar({ patients, search, nlResults, nlLoading, onChange, onSubmit }) {
  const q = search.trim();
  const showNlBtn = q && isNLQuery(q) && nlResults === null;
  return (
    <Box sx={{ px: 1.5, py: 1, borderBottom: "1px solid #e2e8f0", bgcolor: "#f7f7f7" }}>
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
              <Box onClick={onSubmit} sx={{ fontSize: 11, color: "#07C160", cursor: "pointer", whiteSpace: "nowrap", pr: 0.5 }}>
                智能搜索
              </Box>
            </InputAdornment>
          ) : null,
        }}
        sx={{ "& .MuiOutlinedInput-root": { borderRadius: "20px", bgcolor: "#fff" } }}
      />
      {nlResults !== null && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, pt: 0.5 }}>
          <Typography sx={{ fontSize: 11, color: "#888" }}>智能搜索结果 ({nlResults.length}人)</Typography>
          <Box onClick={() => onChange("")} sx={{ fontSize: 11, color: "#07C160", cursor: "pointer" }}>清除</Box>
        </Box>
      )}
    </Box>
  );
}

function PatientGroupList({ filtered, search, selectedId, isMobile, navigate, onInsertChatText, onNavigateToChat }) {
  if (!filtered.length && search.trim()) {
    return (
      <Box sx={{ p: 2 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          未找到患者「{search.trim()}」
        </Typography>
        <Chip label={`创建 ${search.trim()}`} size="small" clickable color="primary" variant="outlined"
          onClick={() => { onInsertChatText?.(`创建${search.trim()}`); onNavigateToChat?.(); }} />
      </Box>
    );
  }
  if (!filtered.length) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 4, gap: 1 }}>
        <Typography variant="body2" color="text.disabled">暂无患者档案</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
          通过上方方式导入，或在聊天中创建
        </Typography>
      </Box>
    );
  }
  return groupPatients(filtered).map(([letter, group]) => (
    <Box key={letter}>
      <Box sx={{ px: 2, py: 0.5, bgcolor: "#f7f7f7", borderBottom: "1px solid #ebebeb" }}>
        <Typography sx={{ fontSize: 12, color: "#888", fontWeight: 600 }}>{letter}</Typography>
      </Box>
      {group.map((p) => (
        <PatientRow
          key={p.id}
          patient={p}
          isSelected={p.id === selectedId}
          isMobile={isMobile}
          onClick={() => navigate(`/doctor/patients/${p.id}`)}
        />
      ))}
    </Box>
  ));
}

function PatientListPane({ patients, loading, error, search, nlResults, nlLoading, filtered, selectedId, isMobile, importing, importError, importFileRef, navigate, onSearchChange, onSearchSubmit, onNavigateToChat, onInsertChatText, onLoad, onFileInputChange }) {
  return (
    <>
      <SearchBar patients={patients} search={search} nlResults={nlResults} nlLoading={nlLoading} onChange={onSearchChange} onSubmit={onSearchSubmit} />
      {error && <Alert severity="error" action={<Button size="small" onClick={onLoad}>重试</Button>}>{error}</Alert>}
      <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#fff" }}>
        {loading && <Box sx={{ p: 2, textAlign: "center" }}><CircularProgress size={20} /></Box>}
        {!loading && !search.trim() && (
          <ImportCard importing={importing} importError={importError}
            onFileClick={() => importFileRef.current?.click()} onChatClick={() => onNavigateToChat?.()} />
        )}
        <input ref={importFileRef} type="file" hidden accept=".pdf,image/jpeg,image/png,image/webp" onChange={onFileInputChange} />
        {!loading && (
          <PatientGroupList filtered={filtered} search={search} selectedId={selectedId}
            isMobile={isMobile} navigate={navigate}
            onInsertChatText={onInsertChatText} onNavigateToChat={onNavigateToChat} />
        )}
      </Box>
    </>
  );
}

async function extractAndSend({ file, onAutoSendToChat, setImportError }) {
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
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [nlResults, setNlResults] = useState(null);
  const [nlLoading, setNlLoading] = useState(false);
  const importFileRef = useRef(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");

  const selectedPatient = patients.find((p) => p.id === selectedId) || null;
  useEffect(() => { onPatientSelected?.(selectedPatient?.name || ""); }, [selectedPatient?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    setLoading(true); setError("");
    getPatients(doctorId, {}, 200).then((d) => setPatients(d.items || [])).catch((e) => setError(e.message || "加载失败")).finally(() => setLoading(false));
  }, [doctorId]);
  useEffect(() => { load(); }, [load, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSearchChange(val) { setSearch(val); setNlResults(null); }
  function handleSearchSubmit() {
    const q = search.trim(); if (!q || !isNLQuery(q)) return;
    setNlLoading(true);
    searchPatients(doctorId, q).then((d) => setNlResults(d.items || [])).catch(() => setNlResults([])).finally(() => setNlLoading(false));
  }
  async function handleImportFile(e) {
    const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
    setImporting(true); setImportError("");
    try { await extractAndSend({ file, onAutoSendToChat, setImportError }); }
    catch (err) { setImportError(err?.message === "Request timed out" ? "文件较大，解析超时，请尝试上传页数更少的 PDF" : "文件解析失败，请重试"); }
    finally { setImporting(false); }
  }

  const filtered = (() => { const q = search.trim(); if (!q) return patients; if (nlResults !== null) return nlResults; return patients.filter((p) => p.name.includes(q)); })();
  return { patients, setPatients, loading, error, search, nlResults, nlLoading, importing, importError, importFileRef, filtered, selectedPatient, load, handleSearchChange, handleSearchSubmit, handleImportFile };
}

function MobilePatientDetailView({ selectedPatient, doctorId, navigate }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={() => navigate("/doctor/patients")} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>患者</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }} noWrap>{selectedPatient?.name || ""}</Typography>
      </Box>
      <Box sx={{ flex: 1, overflow: "hidden" }}><PatientDetail patient={selectedPatient} doctorId={doctorId} /></Box>
    </Box>
  );
}

export default function PatientsSection({ doctorId, onNavigateToChat, onInsertChatText, onAutoSendToChat, onPatientSelected, refreshKey = 0 }) {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const selectedId = patientId ? Number(patientId) : null;
  const { patients, setPatients, loading, error, search, nlResults, nlLoading, importing, importError, importFileRef, filtered, selectedPatient, load, handleSearchChange, handleSearchSubmit, handleImportFile } = usePatientsState({ doctorId, onPatientSelected, onAutoSendToChat, selectedId, refreshKey });

  const listPaneProps = { patients, loading, error, search, nlResults, nlLoading, filtered, selectedId, isMobile, importing, importError, importFileRef, navigate, onSearchChange: handleSearchChange, onSearchSubmit: handleSearchSubmit, onNavigateToChat, onInsertChatText, onLoad: load, onFileInputChange: handleImportFile };

  if (isMobile && selectedId) return <MobilePatientDetailView selectedPatient={selectedPatient} doctorId={doctorId} navigate={navigate} />;

  if (isMobile) {
    return <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}><PatientListPane {...listPaneProps} /></Box>;
  }

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      <Box sx={{ width: 300, flexShrink: 0, borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column", bgcolor: "#f7f7f7" }}>
        <PatientListPane {...listPaneProps} />
      </Box>
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <PatientDetail patient={selectedPatient} doctorId={doctorId}
          onDeleted={(id) => { setPatients((prev) => prev.filter((p) => p.id !== id)); navigate("/doctor/patients"); }} />
      </Box>
    </Box>
  );
}
