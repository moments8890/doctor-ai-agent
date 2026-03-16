/**
 * 设置面板：医生账户信息编辑、科室专业设置、报告模板管理和退出登录。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, Dialog, Stack, TextField, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import LogoutIcon from "@mui/icons-material/Logout";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { getDoctorProfile, updateDoctorProfile, getTemplateStatus, uploadTemplate, deleteTemplate, getKnowledgeItems, deleteKnowledgeItem, addKnowledgeItem } from "../../api";
import { useDoctorStore } from "../../store/doctorStore";
import { SPECIALTY_OPTIONS } from "./constants";

function SettingsRow({ icon, label, sublabel, onClick, danger }) {
  return (
    <Box onClick={onClick} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, cursor: onClick ? "pointer" : "default",
      borderBottom: "0.5px solid #f0f0f0", "&:active": onClick ? { bgcolor: "#f9f9f9" } : {} }}>
      <Box sx={{ width: 36, height: 36, borderRadius: "4px", bgcolor: danger ? "#fef2f2" : "#f0faf4",
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5 }}>
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: 15, color: danger ? "#FA5151" : "#111" }}>{label}</Typography>
        {sublabel && <Typography variant="caption" color="text.secondary">{sublabel}</Typography>}
      </Box>
      {onClick && !danger && <ArrowBackIcon sx={{ fontSize: 16, color: "#ccc", transform: "rotate(180deg)" }} />}
    </Box>
  );
}

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
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!nameSaving ? onSave : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#07C160", cursor: nameSaving ? "default" : "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
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
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!specialtySaving ? onSave : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#07C160", cursor: specialtySaving ? "default" : "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
            {specialtySaving ? "保存中…" : "保存"}
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}

function TemplateStatusCard({ loading, status }) {
  return (
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
  );
}

function TemplateActions({ status, uploading, deleting, fileRef, onDelete }) {
  return (
    <Box sx={{ bgcolor: "#fff" }}>
      <Box onClick={() => fileRef.current?.click()}
        sx={{ display: "flex", alignItems: "center", px: 2, py: 1.6,
          borderBottom: status?.has_template ? "1px solid #f2f2f2" : "none",
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
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>设置</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }}>报告模板</Typography>
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

function KnowledgeSubpage({ doctorId, onBack }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    getKnowledgeItems(doctorId)
      .then((d) => setItems(Array.isArray(d) ? d : (d.items || [])))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [doctorId]);
  useEffect(() => { load(); }, [load]);

  async function handleAdd() {
    const trimmed = newContent.trim();
    if (!trimmed) return;
    setAdding(true); setError("");
    try { await addKnowledgeItem(doctorId, trimmed); setNewContent(""); load(); }
    catch (e) { setError(e.message || "添加失败"); }
    finally { setAdding(false); }
  }
  async function handleDelete(itemId) {
    try { await deleteKnowledgeItem(doctorId, itemId); setItems((prev) => prev.filter((i) => i.id !== itemId)); }
    catch (e) { setError(e.message || "删除失败"); }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>设置</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }}>知识库</Typography>
      </Box>
      <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
        {error && <Alert severity="error" onClose={() => setError("")} sx={{ mb: 1.5 }}>{error}</Alert>}
        <Box sx={{ mb: 2 }}>
          <TextField fullWidth multiline minRows={2} maxRows={4} size="small" placeholder="输入知识条目内容…"
            value={newContent} onChange={(e) => setNewContent(e.target.value)} sx={{ mb: 1 }} />
          <Button variant="contained" size="small" onClick={handleAdd} disabled={adding || !newContent.trim()}
            sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06ad56" } }}>
            {adding ? "添加中…" : "添加"}
          </Button>
        </Box>
        {loading && <Box sx={{ textAlign: "center", py: 3 }}><CircularProgress size={20} /></Box>}
        {!loading && items.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 3 }}>暂无知识条目</Typography>
        )}
        {items.map((item) => (
          <Box key={item.id} sx={{ bgcolor: "#fff", p: 2, borderRadius: 1.5, mb: 1, display: "flex", alignItems: "flex-start", gap: 1 }}>
            <Typography sx={{ flex: 1, fontSize: 13, color: "#333", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
              {item.content}
            </Typography>
            <Box onClick={() => handleDelete(item.id)}
              sx={{ fontSize: 12, color: "#FA5151", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.6 } }}>
              删除
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

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
      <Box sx={{ flex: 1, overflowY: "auto", p: 3, textAlign: "center" }}>
        <Box sx={{ width: 64, height: 64, borderRadius: "16px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", mx: "auto", mb: 2 }}>
          <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: 32 }} />
        </Box>
        <Typography sx={{ fontWeight: 700, fontSize: 18, mb: 0.5 }}>AI 医疗助手</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 3 }}>版本 1.0.0</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
          智能医疗助手为医生提供 AI 辅助病历记录、患者管理和任务跟踪功能，帮助提升诊疗效率。
        </Typography>
      </Box>
    </Box>
  );
}

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

function AccountBlock({ doctorId, doctorName, specialty, onOpenName, onOpenSpecialty }) {
  return (
    <Box sx={{ bgcolor: "#fff" }}>
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.8, borderBottom: "0.5px solid #f0f0f0" }}>
        <Box sx={{ width: 52, height: 52, borderRadius: "4px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5 }}>
          <Typography sx={{ color: "#fff", fontSize: 22, fontWeight: 600 }}>{(doctorName || doctorId || "?").slice(-1)}</Typography>
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600, fontSize: 16 }}>{doctorName || doctorId}</Typography>
          <Typography variant="caption" color="text.secondary">{doctorId}</Typography>
        </Box>
      </Box>
      <Box onClick={onOpenName}
        sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "0.5px solid #f0f0f0", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
        <Typography sx={{ fontSize: 14, color: "#111", flex: 1 }}>昵称</Typography>
        <Typography sx={{ fontSize: 14, color: "#999", mr: 0.8 }}>{doctorName || "未设置"}</Typography>
        <ArrowBackIcon sx={{ fontSize: 16, color: "#ccc", transform: "rotate(180deg)" }} />
      </Box>
      <Box onClick={onOpenSpecialty}
        sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "0.5px solid #f0f0f0", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
        <Typography sx={{ fontSize: 14, color: "#111", flex: 1 }}>科室专业</Typography>
        <Typography sx={{ fontSize: 14, color: "#999", mr: 0.8 }}>{specialty || "未设置"}</Typography>
        <ArrowBackIcon sx={{ fontSize: 16, color: "#ccc", transform: "rotate(180deg)" }} />
      </Box>
    </Box>
  );
}

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

  useEffect(() => { getDoctorProfile(doctorId).then((p) => setSpecialty(p.specialty || "")).catch(() => {}); }, [doctorId]);

  async function handleSaveName() {
    const trimmed = nameInput.trim();
    if (!trimmed) { setNameError("姓名不能为空"); return; }
    setNameSaving(true); setNameError("");
    try { await updateDoctorProfile(doctorId, { name: trimmed }); setAuth(doctorId, trimmed, accessToken); setNameDialogOpen(false); }
    catch (e) { setNameError(e.message || "保存失败"); } finally { setNameSaving(false); }
  }
  async function handleSaveSpecialty() {
    const trimmed = specialtyInput.trim(); setSpecialtySaving(true); setSpecialtyError("");
    try { await updateDoctorProfile(doctorId, { specialty: trimmed || null }); setSpecialty(trimmed); setSpecialtyDialogOpen(false); }
    catch (e) { setSpecialtyError(e.message || "保存失败"); } finally { setSpecialtySaving(false); }
  }

  return { nameDialogOpen, setNameDialogOpen, nameInput, setNameInput, nameSaving, nameError, setNameError, specialty, specialtyDialogOpen, setSpecialtyDialogOpen, specialtyInput, setSpecialtyInput, specialtySaving, specialtyError, handleSaveName, handleSaveSpecialty };
}

export default function SettingsSection({ doctorId, onLogout }) {
  const [subpage, setSubpage] = useState(null);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const { doctorName, setAuth, accessToken } = useDoctorStore();
  const { nameDialogOpen, setNameDialogOpen, nameInput, setNameInput, nameSaving, nameError, setNameError, specialty, specialtyDialogOpen, setSpecialtyDialogOpen, specialtyInput, setSpecialtyInput, specialtySaving, specialtyError, handleSaveName, handleSaveSpecialty } = useSettingsState({ doctorId, doctorName, accessToken, setAuth });

  if (subpage === "template") return <TemplateSubpage doctorId={doctorId} onBack={() => setSubpage(null)} />;
  if (subpage === "knowledge") return <KnowledgeSubpage doctorId={doctorId} onBack={() => setSubpage(null)} />;
  if (subpage === "about") return <AboutSubpage onBack={() => setSubpage(null)} />;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      {isMobile && (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: 48, bgcolor: "#f7f7f7", borderBottom: "0.5px solid #d9d9d9", flexShrink: 0 }}>
          <Typography sx={{ fontWeight: 500, fontSize: 17 }}>设置</Typography>
        </Box>
      )}
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        <Box sx={{ px: 2, pt: 2, pb: 0.6 }}><Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>账户</Typography></Box>
        <AccountBlock doctorId={doctorId} doctorName={doctorName} specialty={specialty}
          onOpenName={() => { setNameInput(doctorName || ""); setNameError(""); setNameDialogOpen(true); }}
          onOpenSpecialty={() => { setSpecialtyInput(specialty || "神经外科"); setSpecialtyError(""); setSpecialtyDialogOpen(true); }} />

        <Box sx={{ px: 2, pt: 2, pb: 0.6 }}><Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>工具</Typography></Box>
        <Box sx={{ bgcolor: "#fff" }}>
          <SettingsRow icon={<UploadFileOutlinedIcon sx={{ color: "#07C160", fontSize: 20 }} />} label="报告模板" sublabel="自定义门诊病历报告格式" onClick={() => setSubpage("template")} />
          <SettingsRow icon={<MenuBookOutlinedIcon sx={{ color: "#5b9bd5", fontSize: 20 }} />} label="知识库" sublabel="管理 AI 助手参考资料" onClick={() => setSubpage("knowledge")} />
        </Box>

        <Box sx={{ px: 2, pt: 2, pb: 0.6 }}><Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>通用</Typography></Box>
        <Box sx={{ bgcolor: "#fff" }}>
          <SettingsRow icon={<InfoOutlinedIcon sx={{ color: "#999", fontSize: 20 }} />} label="关于" sublabel="版本信息" onClick={() => setSubpage("about")} />
        </Box>

        {isMobile && (
          <>
            <Box sx={{ px: 2, pt: 2, pb: 0.6 }}><Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>账户操作</Typography></Box>
            <Box onClick={onLogout} sx={{ bgcolor: "#fff", py: 1.5, textAlign: "center", cursor: "pointer", borderBottom: "0.5px solid #f0f0f0", "&:active": { bgcolor: "#f9f9f9" } }}>
              <Typography sx={{ fontSize: 15, color: "#FA5151" }}>退出登录</Typography>
            </Box>
          </>
        )}
        <Box sx={{ height: 32 }} />
      </Box>
      <NameDialog open={nameDialogOpen} isMobile={isMobile} nameInput={nameInput} nameSaving={nameSaving} nameError={nameError}
        onChange={setNameInput} onSave={handleSaveName} onClose={() => setNameDialogOpen(false)} />
      <SpecialtyDialog open={specialtyDialogOpen} isMobile={isMobile} specialtyInput={specialtyInput} specialtySaving={specialtySaving}
        specialtyError={specialtyError} onChange={setSpecialtyInput} onSave={handleSaveSpecialty} onClose={() => setSpecialtyDialogOpen(false)} />
    </Box>
  );
}
