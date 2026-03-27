/**
 * @route /doctor/settings
 *
 * 设置面板：医生账户信息编辑、科室专业设置、报告模板管理和退出登录。
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, TextField, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { getDoctorProfile, updateDoctorProfile, getKnowledgeItems, deleteKnowledgeItem } from "../../api";
import SectionLabel from "../../components/SectionLabel";
import AppButton from "../../components/AppButton";
import ConfirmDialog from "../../components/ConfirmDialog";
import PageSkeleton from "../../components/PageSkeleton";
import SheetDialog from "../../components/SheetDialog";
import KnowledgeSubpage from "./subpages/KnowledgeSubpage";
import AboutSubpage from "./subpages/AboutSubpage";
import TemplateSubpage from "./subpages/TemplateSubpage";
import AddKnowledgeSubpage, { KNOWLEDGE_CATEGORIES } from "./subpages/AddKnowledgeSubpage";
import { useDoctorStore } from "../../store/doctorStore";
import { SPECIALTY_OPTIONS } from "./constants";
import { TYPE, ICON } from "../../theme";

function SettingsRow({ icon, label, sublabel, onClick, danger }) {
  return (
    <Box onClick={onClick} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, cursor: onClick ? "pointer" : "default",
      borderBottom: "0.5px solid #f0f0f0", "&:active": onClick ? { bgcolor: "#f9f9f9" } : {} }}>
      <Box sx={{ width: 36, height: 36, borderRadius: "4px", bgcolor: danger ? "#fef2f2" : "#f0faf4",
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5 }}>
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: danger ? "#FA5151" : "#111" }}>{label}</Typography>
        {sublabel && <Typography variant="caption" color="text.secondary">{sublabel}</Typography>}
      </Box>
      {onClick && !danger && <ArrowBackIcon sx={{ fontSize: ICON.sm, color: "#ccc", transform: "rotate(180deg)" }} />}
    </Box>
  );
}

function NameDialog({ open, nameInput, nameSaving, nameError, onChange, onSave, onClose }) {
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="设置昵称"
      subtitle="AI 助手将用此姓名称呼您，例如「好的，张医生」"
      desktopMaxWidth={360}
      footer={
        <Box sx={{ display: "grid", gap: 0.75, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <AppButton variant="secondary" size="md" fullWidth onClick={onClose}>
            取消
          </AppButton>
          <AppButton
            variant="primary"
            size="md"
            fullWidth
            disabled={nameSaving}
            loading={nameSaving}
            loadingLabel="保存中…"
            onClick={onSave}
          >
            保存
          </AppButton>
        </Box>
      }
    >
      <TextField
        fullWidth
        size="small"
        placeholder="请输入您的姓名（如：张伟）"
        value={nameInput}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") onSave(); }}
        autoFocus
        sx={{ mt: 0.5 }}
      />
      {nameError ? (
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#FA5151", mt: 0.75 }}>
          {nameError}
        </Typography>
      ) : null}
    </SheetDialog>
  );
}

function SpecialtyDialog({ open, specialtyInput, specialtySaving, specialtyError, onChange, onSave, onClose }) {
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="科室专业"
      desktopMaxWidth={380}
      footer={
        <Box sx={{ display: "grid", gap: 0.75, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <AppButton variant="secondary" size="md" fullWidth onClick={onClose}>
            取消
          </AppButton>
          <AppButton
            variant="primary"
            size="md"
            fullWidth
            disabled={specialtySaving}
            loading={specialtySaving}
            loadingLabel="保存中…"
            onClick={onSave}
          >
            保存
          </AppButton>
        </Box>
      }
    >
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.8, mt: 0.5, mb: 2 }}>
        {SPECIALTY_OPTIONS.map((s) => (
          <Box
            key={s}
            onClick={() => onChange(s)}
            sx={{
              px: 1.4,
              py: 0.5,
              borderRadius: "999px",
              cursor: "pointer",
              fontSize: TYPE.secondary.fontSize,
              bgcolor: specialtyInput === s ? "#07C160" : "#f2f2f2",
              color: specialtyInput === s ? "#fff" : "#555",
              fontWeight: specialtyInput === s ? 600 : 400,
            }}
          >
            {s}
          </Box>
        ))}
      </Box>
      <TextField
        fullWidth
        size="small"
        placeholder="或直接输入科室名称"
        value={specialtyInput}
        onChange={(e) => onChange(e.target.value)}
      />
      {specialtyError ? (
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#FA5151", mt: 0.75 }}>
          {specialtyError}
        </Typography>
      ) : null}
    </SheetDialog>
  );
}


function KnowledgeDeleteDialog({ open, onClose, onConfirm }) {
  return (
    <ConfirmDialog
      open={open}
      onClose={onClose}
      onCancel={onClose}
      onConfirm={onConfirm}
      title="确认删除"
      message="删除后该知识将不再影响 AI 行为，确定要删除吗？"
      cancelLabel="保留"
      confirmLabel="删除"
      confirmTone="danger"
    />
  );
}

function KnowledgeSubpageWrapper({ doctorId, onBack, isMobile, urlSubId }) {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    getKnowledgeItems(doctorId)
      .then((data) => setItems(Array.isArray(data) ? data : (data.items || [])))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [doctorId]);
  useEffect(() => { load(); }, [load]);

  // URL-driven: "new" subpage for adding
  if (urlSubId === "new" || urlSubId === "add") {
    return <AddKnowledgeSubpage doctorId={doctorId} onBack={() => { navigate("/doctor/settings/knowledge"); load(); }} isMobile={isMobile} />;
  }

  async function handleDelete(itemId) {
    try {
      await deleteKnowledgeItem(doctorId, itemId);
      setItems((prev) => prev.filter((i) => i.id !== itemId));
    } catch {}
  }

  return (
    <KnowledgeSubpage
      items={items}
      categories={KNOWLEDGE_CATEGORIES}
      loading={loading}
      onBack={isMobile ? onBack : undefined}
      onAdd={() => navigate("/doctor/settings/knowledge/new")}
      onDelete={handleDelete}
      onEdit={(id, text) => {
        // TODO: add updateKnowledgeItem API call
        setItems(prev => prev.map(i => i.id === id ? { ...i, text, content: text } : i));
      }}
    />
  );
}


function StubSubpage({ title, onBack, isMobile }) {
  const content = (
    <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Typography color="text.secondary">即将推出</Typography>
    </Box>
  );
  return <PageSkeleton title={title} onBack={isMobile ? onBack : undefined} isMobile={isMobile} listPane={content} />;
}

function AccountBlock({ doctorId, doctorName, specialty, onOpenName, onOpenSpecialty }) {
  return (
    <Box sx={{ bgcolor: "#fff" }}>
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.8, borderBottom: "0.5px solid #f0f0f0" }}>
        <Box sx={{ width: 52, height: 52, borderRadius: "4px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5 }}>
          <Typography sx={{ color: "#fff", fontSize: ICON.xl, fontWeight: 600 }}>{(doctorName || doctorId || "?").slice(-1)}</Typography>
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize }}>{doctorName || doctorId}</Typography>
          <Typography variant="caption" color="text.secondary">{doctorId}</Typography>
        </Box>
      </Box>
      {/* Nickname change disabled during internal testing — name is used for login */}
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "0.5px solid #f0f0f0" }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#111", flex: 1 }}>昵称</Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#999", mr: 0.8 }}>{doctorName || "未设置"}</Typography>
      </Box>
      {/* Specialty change disabled during internal testing — only 神经外科 supported */}
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "0.5px solid #f0f0f0" }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#111", flex: 1 }}>科室专业</Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#999", mr: 0.8 }}>{specialty || "神经外科"}</Typography>
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

export default function SettingsPage({ doctorId, onLogout, urlSubpage, urlSubId }) {
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const { doctorName, setAuth, accessToken } = useDoctorStore();
  const { nameDialogOpen, setNameDialogOpen, nameInput, setNameInput, nameSaving, nameError, setNameError, specialty, specialtyDialogOpen, setSpecialtyDialogOpen, specialtyInput, setSpecialtyInput, specialtySaving, specialtyError, handleSaveName, handleSaveSpecialty } = useSettingsState({ doctorId, doctorName, accessToken, setAuth });

  // URL-driven subpage (survives refresh)
  const subpage = urlSubpage || null;
  const goSub = (sub) => navigate(`/doctor/settings/${sub}`);
  const goBack = () => navigate("/doctor/settings");

  // Mobile subpage override
  const mobileSubpage = isMobile && subpage === "template" ? (
    <TemplateSubpage doctorId={doctorId} onBack={goBack} isMobile />
  ) : isMobile && subpage === "knowledge" ? (
    <KnowledgeSubpageWrapper doctorId={doctorId} onBack={goBack} isMobile urlSubId={urlSubId} />
  ) : isMobile && subpage === "about" ? (
    <AboutSubpage onBack={goBack} isMobile />
  ) : null;

  const listPane = (
    <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
      <SectionLabel>账户</SectionLabel>
      <AccountBlock doctorId={doctorId} doctorName={doctorName} specialty={specialty}
        onOpenName={() => { setNameInput(doctorName || ""); setNameError(""); setNameDialogOpen(true); }}
        onOpenSpecialty={() => { setSpecialtyInput(specialty || "神经外科"); setSpecialtyError(""); setSpecialtyDialogOpen(true); }} />

      <SectionLabel>工具</SectionLabel>
      <Box sx={{ bgcolor: "#fff" }}>
        <SettingsRow icon={<UploadFileOutlinedIcon sx={{ color: "#07C160", fontSize: ICON.lg }} />} label="报告模板" sublabel="自定义门诊病历报告格式" onClick={() => goSub("template")} />
        <SettingsRow icon={<MenuBookOutlinedIcon sx={{ color: "#5b9bd5", fontSize: ICON.lg }} />} label="知识库" sublabel="管理 AI 助手参考资料" onClick={() => goSub("knowledge")} />
      </Box>

      <SectionLabel>通用</SectionLabel>
      <Box sx={{ bgcolor: "#fff" }}>
        <SettingsRow icon={<InfoOutlinedIcon sx={{ color: "#999", fontSize: ICON.lg }} />} label="关于" sublabel="版本信息" onClick={() => goSub("about")} />
      </Box>

      {isMobile && (
        <>
          <SectionLabel>账户操作</SectionLabel>
          <Box onClick={onLogout} sx={{ bgcolor: "#fff", py: 1.5, textAlign: "center", cursor: "pointer", borderBottom: "0.5px solid #f0f0f0", "&:active": { bgcolor: "#f9f9f9" } }}>
            <Typography sx={{ fontSize: TYPE.action.fontSize, color: "#FA5151" }}>退出登录</Typography>
          </Box>
        </>
      )}
      <Box sx={{ height: 32 }} />
      <NameDialog open={nameDialogOpen} nameInput={nameInput} nameSaving={nameSaving} nameError={nameError}
        onChange={setNameInput} onSave={handleSaveName} onClose={() => setNameDialogOpen(false)} />
      <SpecialtyDialog open={specialtyDialogOpen} specialtyInput={specialtyInput} specialtySaving={specialtySaving}
        specialtyError={specialtyError} onChange={setSpecialtyInput} onSave={handleSaveSpecialty} onClose={() => setSpecialtyDialogOpen(false)} />
    </Box>
  );

  const detailContent = subpage === "template" ? (
    <TemplateSubpage doctorId={doctorId} onBack={goBack} />
  ) : subpage === "knowledge" ? (
    <KnowledgeSubpageWrapper doctorId={doctorId} onBack={goBack} isMobile />
  ) : subpage === "about" ? (
    <AboutSubpage onBack={goBack} />
  ) : null;

  return (
    <PageSkeleton
      title="设置"
      isMobile={isMobile}
      mobileView={mobileSubpage}
      listPane={listPane}
      detailPane={detailContent}
    />
  );
}
