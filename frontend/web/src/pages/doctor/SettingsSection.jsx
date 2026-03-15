/**
 * 设置面板：医生账户信息编辑、科室专业设置、报告模板管理和退出登录。
 * 分组菜单结构：个人信息、AI设置、文档管理、系统。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, Dialog, Stack, TextField, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import EventNoteOutlinedIcon from "@mui/icons-material/EventNoteOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { getDoctorProfile, updateDoctorProfile, getTemplateStatus, uploadTemplate, deleteTemplate, getKnowledgeItems, addKnowledgeItem, deleteKnowledgeItem } from "../../api";
import { useDoctorStore } from "../../store/doctorStore";
import { SPECIALTY_OPTIONS } from "./constants";

/* ────────── Shared row component ────────── */

function SettingsRow({ icon, label, sublabel, onClick, danger }) {
  return (
    <Box onClick={onClick} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, cursor: onClick ? "pointer" : "default",
      borderBottom: "0.5px solid #f0f0f0", "&:active": onClick ? { bgcolor: "#f9f9f9" } : {} }}>
      <Box sx={{ width: 36, height: 36, borderRadius: "4px", bgcolor: danger ? "#fef2f2" : "#f0faf4",
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5 }}>
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: 14, color: danger ? "#FA5151" : "#111" }}>{label}</Typography>
        {sublabel && <Typography variant="caption" color="text.secondary">{sublabel}</Typography>}
      </Box>
      {onClick && !danger && <ArrowBackIcon sx={{ fontSize: 16, color: "#ccc", transform: "rotate(180deg)" }} />}
    </Box>
  );
}

/* ────────── Dialogs (unchanged) ────────── */

function NameDialog({ open, isMobile, nameInput, nameSaving, nameError, onChange, onSave, onClose }) {
  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "12px 12px 0 0", width: "100%" } : { borderRadius: 2, minWidth: 300 } }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 0.5, color: "#333" }}>设置昵称</Typography>
        <Typography sx={{ fontSize: 12, color: "#999", mb: 2 }}>AI 助手将用此姓名称呼您，例如「好的，张医生」</Typography>
        <TextField fullWidth size="small" placeholder="请输入您的姓名（如：张伟）"
          value={nameInput} onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSave(); }}
          autoFocus sx={{ mb: nameError ? 0.5 : 2 }} />
        {nameError && <Typography sx={{ fontSize: 12, color: "#FA5151", mb: 1.5 }}>{nameError}</Typography>}
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!nameSaving ? onSave : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#07C160", cursor: nameSaving ? "default" : "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
            {nameSaving ? "保存中…" : "保存"}
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}

function SpecialtyDialog({ open, isMobile, specialtyInput, specialtySaving, specialtyError, onChange, onSave, onClose }) {
  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "12px 12px 0 0", width: "100%" } : { borderRadius: 2, minWidth: 320 } }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 2, color: "#333" }}>科室专业</Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.8, mb: 2 }}>
          {SPECIALTY_OPTIONS.map((s) => (
            <Box key={s} onClick={() => onChange(s)}
              sx={{ px: 1.4, py: 0.4, borderRadius: "4px", cursor: "pointer", fontSize: 13,
                bgcolor: specialtyInput === s ? "#07C160" : "#f2f2f2",
                color: specialtyInput === s ? "#fff" : "#555",
                fontWeight: specialtyInput === s ? 600 : 400 }}>
              {s}
            </Box>
          ))}
        </Box>
        <TextField fullWidth size="small" placeholder="或直接输入科室名称"
          value={specialtyInput} onChange={(e) => onChange(e.target.value)}
          sx={{ mb: specialtyError ? 0.5 : 2 }} />
        {specialtyError && <Typography sx={{ fontSize: 12, color: "#FA5151", mb: 1.5 }}>{specialtyError}</Typography>}
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!specialtySaving ? onSave : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#07C160", cursor: specialtySaving ? "default" : "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
            {specialtySaving ? "保存中…" : "保存"}
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}

const NOTE_STYLE_OPTIONS = ["简洁", "详细", "SOAP", "叙述体"];

function SimpleTextDialog({ open, isMobile, title, hint, value, saving, error, quickPicks, onChange, onSave, onClose }) {
  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "12px 12px 0 0", width: "100%" } : { borderRadius: 2, minWidth: 320 } }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 0.5, color: "#333" }}>{title}</Typography>
        {hint && <Typography sx={{ fontSize: 12, color: "#999", mb: 2 }}>{hint}</Typography>}
        {quickPicks && quickPicks.length > 0 && (
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.8, mb: 2 }}>
            {quickPicks.map((s) => (
              <Box key={s} onClick={() => onChange(s)}
                sx={{ px: 1.4, py: 0.4, borderRadius: "4px", cursor: "pointer", fontSize: 13,
                  bgcolor: value === s ? "#07C160" : "#f2f2f2",
                  color: value === s ? "#fff" : "#555",
                  fontWeight: value === s ? 600 : 400 }}>
                {s}
              </Box>
            ))}
          </Box>
        )}
        <TextField fullWidth size="small" placeholder={hint || ""}
          value={value} onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSave(); }}
          autoFocus sx={{ mb: error ? 0.5 : 2 }} />
        {error && <Typography sx={{ fontSize: 12, color: "#FA5151", mb: 1.5 }}>{error}</Typography>}
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!saving ? onSave : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#07C160", cursor: saving ? "default" : "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
            {saving ? "保存中…" : "保存"}
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}

/* ────────── Template subpage components (unchanged) ────────── */

function TemplateStatusCard({ loading, status }) {
  return (
    <Box sx={{ bgcolor: "#fff", px: 2, py: 2, mb: 0.8 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
        <Box sx={{ width: 44, height: 44, borderRadius: "4px", bgcolor: "#e8f5e9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
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
          <Box sx={{ px: 1, py: 0.3, borderRadius: "4px", bgcolor: "#e8f5e9" }}>
            <Typography sx={{ fontSize: 11, color: "#07C160", fontWeight: 600 }}>已自定义</Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}

function TemplateActions({ status, uploading, deleting, fileRef, onDelete }) {
  return (
    <Box sx={{ bgcolor: "#fff" }}>
      <Box onClick={() => fileRef.current?.click()}
        sx={{ display: "flex", alignItems: "center", px: 2, py: 1.6,
          borderBottom: status?.has_template ? "0.5px solid #f0f0f0" : "none",
          cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
        {uploading ? <CircularProgress size={18} sx={{ mr: 1.5, color: "#07C160" }} /> : <Box sx={{ width: 18, mr: 1.5 }} />}
        <Typography sx={{ flex: 1, fontSize: 15, color: uploading ? "#999" : "#07C160", fontWeight: 500 }}>
          {uploading ? "上传中…" : status?.has_template ? "替换模板文件" : "上传模板文件"}
        </Typography>
        <ArrowBackIcon sx={{ fontSize: 16, color: "#ccc", transform: "rotate(180deg)" }} />
      </Box>
      {status?.has_template && (
        <Box onClick={!deleting ? onDelete : undefined}
          sx={{ display: "flex", alignItems: "center", px: 2, py: 1.6, cursor: deleting ? "default" : "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
          {deleting ? <CircularProgress size={18} sx={{ mr: 1.5, color: "#FA5151" }} /> : <Box sx={{ width: 18, mr: 1.5 }} />}
          <Typography sx={{ flex: 1, fontSize: 15, color: deleting ? "#999" : "#FA5151" }}>
            {deleting ? "删除中…" : "删除模板，恢复默认"}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

function useTemplateState(doctorId) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [msg, setMsg] = useState({ type: "", text: "" });
  const fileRef = useRef(null);

  const loadStatus = useCallback(() => {
    setLoading(true);
    getTemplateStatus(doctorId).then(setStatus).catch(() => setStatus(null)).finally(() => setLoading(false));
  }, [doctorId]);
  useEffect(() => { loadStatus(); }, [loadStatus]);

  async function handleUpload(e) {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true); setMsg({ type: "", text: "" });
    try { await uploadTemplate(doctorId, file); setMsg({ type: "success", text: `模板已上传（${file.name}）` }); loadStatus(); }
    catch (err) { setMsg({ type: "error", text: err.message || "上传失败" }); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  async function handleDelete() {
    setDeleting(true); setMsg({ type: "", text: "" });
    try { await deleteTemplate(doctorId); setMsg({ type: "success", text: "模板已删除，将使用默认格式" }); loadStatus(); }
    catch (err) { setMsg({ type: "error", text: err.message || "删除失败" }); }
    finally { setDeleting(false); }
  }

  return { status, loading, uploading, deleting, msg, setMsg, fileRef, handleUpload, handleDelete };
}

function TemplateSubpage({ doctorId, onBack }) {
  const { status, loading, uploading, deleting, msg, setMsg, fileRef, handleUpload, handleDelete } = useTemplateState(doctorId);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#f7f7f7", borderBottom: "0.5px solid #d9d9d9", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>设置</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 500, fontSize: 17, mr: 5 }}>报告模板</Typography>
      </Box>
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        <Box sx={{ px: 2, pt: 2, pb: 0.6 }}>
          <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>当前模板</Typography>
        </Box>
        <TemplateStatusCard loading={loading} status={status} />
        <Box sx={{ px: 2, pb: 0.6 }}>
          <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>操作</Typography>
        </Box>
        <TemplateActions status={status} uploading={uploading} deleting={deleting} fileRef={fileRef} onDelete={handleDelete} />
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

/* ────────── Knowledge subpage ────────── */

function KnowledgeSubpage({ doctorId, onBack }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    getKnowledgeItems(doctorId)
      .then((d) => setItems(Array.isArray(d) ? d : (d.items || [])))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [doctorId]);

  async function handleAdd() {
    if (!newContent.trim()) return;
    setAdding(true);
    try {
      const item = await addKnowledgeItem(doctorId, newContent.trim());
      setItems((prev) => [item, ...prev]);
      setNewContent("");
    } catch {}
    finally { setAdding(false); }
  }

  async function handleDelete(itemId) {
    try {
      await deleteKnowledgeItem(doctorId, itemId);
      setItems((prev) => prev.filter((i) => i.id !== itemId));
    } catch {}
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>设置</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }}>知识库管理</Typography>
      </Box>
      <Box sx={{ p: 2, bgcolor: "#fff", mb: 0.8 }}>
        <TextField fullWidth size="small" multiline minRows={2}
          placeholder="输入医学知识条目（如：高血压患者优先使用ARB类降压药）"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)} />
        <Box onClick={!adding ? handleAdd : undefined}
          sx={{ mt: 1, py: 0.8, borderRadius: 1.5,
            bgcolor: newContent.trim() ? "#07C160" : "#e0e0e0",
            textAlign: "center", color: "#fff", fontSize: 14,
            fontWeight: 600, cursor: newContent.trim() ? "pointer" : "default" }}>
          {adding ? "添加中…" : "添加知识"}
        </Box>
      </Box>
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress size={24} sx={{ color: "#07C160" }} />
          </Box>
        ) : items.length === 0 ? (
          <Box sx={{ py: 6, textAlign: "center" }}>
            <Typography color="text.secondary">暂无知识条目</Typography>
          </Box>
        ) : (
          items.map((item) => (
            <Box key={item.id} sx={{ bgcolor: "#fff", px: 2, py: 1.5, mb: 0.5 }}>
              <Typography sx={{ fontSize: 14, color: "#333", mb: 0.5 }}>{item.content}</Typography>
              <Box sx={{ display: "flex", justifyContent: "space-between" }}>
                <Typography variant="caption" color="text.secondary">
                  {item.created_at?.slice(0, 10)}
                </Typography>
                <Typography onClick={() => handleDelete(item.id)}
                  sx={{ fontSize: 12, color: "#e74c3c", cursor: "pointer" }}>
                  删除
                </Typography>
              </Box>
            </Box>
          ))
        )}
      </Box>
    </Box>
  );
}

/* ────────── Stub subpage ────────── */

function StubSubpage({ title, onBack }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>设置</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }}>{title}</Typography>
      </Box>
      <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Typography color="text.secondary">即将推出</Typography>
      </Box>
    </Box>
  );
}

/* ────────── About subpage ────────── */

function AboutSubpage({ onBack }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>设置</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }}>关于</Typography>
      </Box>
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", pt: 6 }}>
        <LocalHospitalOutlinedIcon sx={{ fontSize: 48, color: "#07C160", mb: 1.5 }} />
        <Typography sx={{ fontWeight: 700, fontSize: 18, mb: 0.5 }}>AI 医生助手</Typography>
        <Typography variant="caption" color="text.secondary">版本 1.0.0 (MVP)</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
          &copy; 2024-2026 Doctor AI Agent
        </Typography>
      </Box>
    </Box>
  );
}

/* ────────── Profile card ────────── */

function ProfileCard({ doctorId, doctorName, specialty }) {
  return (
    <Box sx={{ bgcolor: "#07C160", borderRadius: "0 0 16px 16px", px: 2.5, pt: 3, pb: 2.5, mb: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        <Box sx={{ width: 60, height: 60, borderRadius: "50%", bgcolor: "rgba(255,255,255,0.25)",
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: 30 }} />
        </Box>
        <Box>
          <Typography sx={{ fontWeight: 700, fontSize: 20, color: "#fff" }}>
            {doctorName || "未设置"}
          </Typography>
          <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.8)" }}>
            {specialty || "未设置科室"} · {doctorId}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}

/* ────────── Settings groups configuration ────────── */

const SETTINGS_ICON_MAP = {
  name: <PersonOutlineIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  specialty: <MedicalServicesOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  visitScenario: <EventNoteOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  noteStyle: <DescriptionOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  aiSettings: <SmartToyOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  knowledge: <MenuBookOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  template: <UploadFileOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  notifications: <NotificationsNoneOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  general: <SettingsOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
  about: <InfoOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />,
};

const SETTINGS_GROUPS = [
  {
    title: "个人信息",
    items: [
      { key: "name", label: "昵称", sublabel: (s) => s.doctorName || "未设置" },
      { key: "specialty", label: "科室专业", sublabel: (s) => s.specialty || "未设置" },
      { key: "visitScenario", label: "诊疗场景", sublabel: (s) => s.visitScenario || "未设置" },
      { key: "noteStyle", label: "病历风格", sublabel: (s) => s.noteStyle || "未设置" },
    ],
  },
  {
    title: "AI 设置",
    items: [
      { key: "aiSettings", label: "AI助手设置", sublabel: () => "模型与行为配置" },
      { key: "knowledge", label: "知识库管理", sublabel: () => "自定义医学知识" },
    ],
  },
  {
    title: "文档管理",
    items: [
      { key: "template", label: "报告模板", sublabel: () => "自定义门诊病历报告格式" },
    ],
  },
  {
    title: "系统",
    items: [
      { key: "notifications", label: "通知设置", sublabel: () => "任务提醒方式" },
      { key: "general", label: "通用设置", sublabel: () => "语言、主题" },
      { key: "about", label: "关于", sublabel: () => "版本信息" },
    ],
  },
];

/* ────────── Settings state hook (unchanged logic) ────────── */

function useSettingsState({ doctorId, doctorName, accessToken, setAuth }) {
  const [nameDialogOpen, setNameDialogOpen] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [nameSaving, setNameSaving] = useState(false);
  const [nameError, setNameError] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [specialtyDialogOpen, setSpecialtyDialogOpen] = useState(false);
  const [specialtyInput, setSpecialtyInput] = useState("");
  const [specialtySaving, setSpecialtySaving] = useState(false);
  const [specialtyError, setSpecialtyError] = useState("");
  const [visitScenario, setVisitScenario] = useState("");
  const [visitScenarioDialogOpen, setVisitScenarioDialogOpen] = useState(false);
  const [visitScenarioInput, setVisitScenarioInput] = useState("");
  const [visitScenarioSaving, setVisitScenarioSaving] = useState(false);
  const [visitScenarioError, setVisitScenarioError] = useState("");
  const [noteStyle, setNoteStyle] = useState("");
  const [noteStyleDialogOpen, setNoteStyleDialogOpen] = useState(false);
  const [noteStyleInput, setNoteStyleInput] = useState("");
  const [noteStyleSaving, setNoteStyleSaving] = useState(false);
  const [noteStyleError, setNoteStyleError] = useState("");

  useEffect(() => {
    getDoctorProfile(doctorId).then((p) => {
      setSpecialty(p.specialty || "");
      setVisitScenario(p.visit_scenario || "");
      setNoteStyle(p.note_style || "");
    }).catch(() => {});
  }, [doctorId]);

  async function handleSaveName() {
    const trimmed = nameInput.trim();
    if (!trimmed) { setNameError("姓名不能为空"); return; }
    setNameSaving(true); setNameError("");
    try { await updateDoctorProfile(doctorId, { name: trimmed }); setAuth(doctorId, trimmed, accessToken); setNameDialogOpen(false); }
    catch (e) { setNameError(e.message || "保存失败"); } finally { setNameSaving(false); }
  }
  async function handleSaveSpecialty() {
    const trimmed = specialtyInput.trim(); setSpecialtySaving(true); setSpecialtyError("");
    try { await updateDoctorProfile(doctorId, { name: doctorName, specialty: trimmed || null }); setSpecialty(trimmed); setSpecialtyDialogOpen(false); }
    catch (e) { setSpecialtyError(e.message || "保存失败"); } finally { setSpecialtySaving(false); }
  }
  async function handleSaveVisitScenario() {
    const trimmed = visitScenarioInput.trim(); setVisitScenarioSaving(true); setVisitScenarioError("");
    try { await updateDoctorProfile(doctorId, { name: doctorName, visit_scenario: trimmed || null }); setVisitScenario(trimmed); setVisitScenarioDialogOpen(false); }
    catch (e) { setVisitScenarioError(e.message || "保存失败"); } finally { setVisitScenarioSaving(false); }
  }
  async function handleSaveNoteStyle() {
    const trimmed = noteStyleInput.trim(); setNoteStyleSaving(true); setNoteStyleError("");
    try { await updateDoctorProfile(doctorId, { name: doctorName, note_style: trimmed || null }); setNoteStyle(trimmed); setNoteStyleDialogOpen(false); }
    catch (e) { setNoteStyleError(e.message || "保存失败"); } finally { setNoteStyleSaving(false); }
  }

  return {
    nameDialogOpen, setNameDialogOpen, nameInput, setNameInput, nameSaving, nameError, setNameError,
    specialty, specialtyDialogOpen, setSpecialtyDialogOpen, specialtyInput, setSpecialtyInput, specialtySaving, specialtyError,
    visitScenario, visitScenarioDialogOpen, setVisitScenarioDialogOpen, visitScenarioInput, setVisitScenarioInput, visitScenarioSaving, visitScenarioError,
    noteStyle, noteStyleDialogOpen, setNoteStyleDialogOpen, noteStyleInput, setNoteStyleInput, noteStyleSaving, noteStyleError,
    handleSaveName, handleSaveSpecialty, handleSaveVisitScenario, handleSaveNoteStyle,
  };
}

/* ────────── Main component ────────── */

export default function SettingsSection({ doctorId, onLogout }) {
  const [subpage, setSubpage] = useState(null);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const { doctorName, setAuth, accessToken } = useDoctorStore();
  const {
    nameDialogOpen, setNameDialogOpen, nameInput, setNameInput, nameSaving, nameError, setNameError,
    specialty, specialtyDialogOpen, setSpecialtyDialogOpen, specialtyInput, setSpecialtyInput, specialtySaving, specialtyError,
    visitScenario, visitScenarioDialogOpen, setVisitScenarioDialogOpen, visitScenarioInput, setVisitScenarioInput, visitScenarioSaving, visitScenarioError,
    noteStyle, noteStyleDialogOpen, setNoteStyleDialogOpen, noteStyleInput, setNoteStyleInput, noteStyleSaving, noteStyleError,
    handleSaveName, handleSaveSpecialty, handleSaveVisitScenario, handleSaveNoteStyle,
  } = useSettingsState({ doctorId, doctorName, accessToken, setAuth });

  const goBack = () => setSubpage(null);

  /* Subpage routing */
  if (subpage === "template") return <TemplateSubpage doctorId={doctorId} onBack={goBack} />;
  if (subpage === "knowledge") return <KnowledgeSubpage doctorId={doctorId} onBack={goBack} />;
  if (subpage === "aiSettings") return <StubSubpage title="AI助手设置" onBack={goBack} />;
  if (subpage === "notifications") return <StubSubpage title="通知设置" onBack={goBack} />;
  if (subpage === "general") return <StubSubpage title="通用设置" onBack={goBack} />;
  if (subpage === "about") return <AboutSubpage onBack={goBack} />;

  /* Settings state for sublabel rendering */
  const settingsState = { doctorName, specialty, visitScenario, noteStyle };

  /* Navigation handler for menu items */
  function handleSettingsNav(key) {
    switch (key) {
      case "name":
        setNameInput(doctorName || ""); setNameError(""); setNameDialogOpen(true);
        break;
      case "specialty":
        setSpecialtyInput(specialty || "神经外科"); setSpecialtyDialogOpen(true);
        break;
      case "visitScenario":
        setVisitScenarioInput(visitScenario || ""); setVisitScenarioDialogOpen(true);
        break;
      case "noteStyle":
        setNoteStyleInput(noteStyle || ""); setNoteStyleDialogOpen(true);
        break;
      case "template":
      case "knowledge":
      case "aiSettings":
      case "notifications":
      case "general":
      case "about":
        setSubpage(key);
        break;
      default:
        break;
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      {isMobile && (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: 48, bgcolor: "#f7f7f7", borderBottom: "0.5px solid #d9d9d9", flexShrink: 0 }}>
          <Typography sx={{ fontWeight: 500, fontSize: 17 }}>设置</Typography>
        </Box>
      )}
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {/* Profile card */}
        <ProfileCard doctorId={doctorId} doctorName={doctorName} specialty={specialty} />

        {/* Grouped menu sections */}
        {SETTINGS_GROUPS.map((group) => (
          <Box key={group.title}>
            <Box sx={{ px: 2, pt: 2, pb: 0.6 }}>
              <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>{group.title}</Typography>
            </Box>
            <Box sx={{ bgcolor: "#fff" }}>
              {group.items.map((item) => (
                <SettingsRow
                  key={item.key}
                  icon={SETTINGS_ICON_MAP[item.key]}
                  label={item.label}
                  sublabel={item.sublabel(settingsState)}
                  onClick={() => handleSettingsNav(item.key)}
                />
              ))}
            </Box>
          </Box>
        ))}

        {/* Logout button (always visible) */}
        <Box sx={{ px: 2, mt: 2, mb: 4 }}>
          <Box onClick={onLogout}
            sx={{ py: 1.3, borderRadius: 2, bgcolor: "#fff", textAlign: "center", color: "#e74c3c", fontSize: 16,
              fontWeight: 600, cursor: "pointer", "&:active": { bgcolor: "#fef2f2" } }}>
            退出登录
          </Box>
        </Box>

        <Box sx={{ height: 32 }} />
      </Box>

      {/* Dialogs */}
      <NameDialog open={nameDialogOpen} isMobile={isMobile} nameInput={nameInput} nameSaving={nameSaving} nameError={nameError}
        onChange={setNameInput} onSave={handleSaveName} onClose={() => setNameDialogOpen(false)} />
      <SpecialtyDialog open={specialtyDialogOpen} isMobile={isMobile} specialtyInput={specialtyInput} specialtySaving={specialtySaving}
        specialtyError={specialtyError} onChange={setSpecialtyInput} onSave={handleSaveSpecialty} onClose={() => setSpecialtyDialogOpen(false)} />
      <SimpleTextDialog open={visitScenarioDialogOpen} isMobile={isMobile} title="常见诊疗场景"
        hint="AI 将根据此设置优化病历结构化，例如「脑出血术后复查」「高血压随访」"
        value={visitScenarioInput} saving={visitScenarioSaving} error={visitScenarioError}
        onChange={setVisitScenarioInput} onSave={handleSaveVisitScenario} onClose={() => setVisitScenarioDialogOpen(false)} />
      <SimpleTextDialog open={noteStyleDialogOpen} isMobile={isMobile} title="病历风格"
        hint="AI 生成病历时将参照此风格偏好"
        value={noteStyleInput} saving={noteStyleSaving} error={noteStyleError}
        quickPicks={NOTE_STYLE_OPTIONS}
        onChange={setNoteStyleInput} onSave={handleSaveNoteStyle} onClose={() => setNoteStyleDialogOpen(false)} />
    </Box>
  );
}
