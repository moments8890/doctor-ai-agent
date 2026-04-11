/**
 * @route /doctor/settings
 *
 * 设置面板：医生账户信息编辑、科室专业设置、报告模板管理和退出登录。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useKnowledgeItems } from "../../lib/doctorQueries";
import { QK } from "../../lib/queryKeys";
import {
  Box, CircularProgress, TextField, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useApi } from "../../api/ApiContext";
import { startBulkExport, getBulkExportStatus, downloadBulkExport } from "../../api";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import AppButton from "../../components/AppButton";
import ConfirmDialog from "../../components/ConfirmDialog";
import PageSkeleton from "../../components/PageSkeleton";
import SheetDialog from "../../components/SheetDialog";
import DialogFooter from "../../components/DialogFooter";
import SubpageHeader from "../../components/SubpageHeader";
import { QRCodeSVG } from "qrcode.react";
import KnowledgeSubpage from "./subpages/KnowledgeSubpage";
import KnowledgeDetailSubpage from "./subpages/KnowledgeDetailSubpage";
import AboutSubpage from "./subpages/AboutSubpage";
import PrivacySubpage from "../../pages/PrivacyPage";
import TemplateSubpage from "./subpages/TemplateSubpage";
import PersonaSubpage from "./subpages/PersonaSubpage";
import AddKnowledgeSubpage from "./subpages/AddKnowledgeSubpage";
import { useDoctorStore } from "../../store/doctorStore";
import SettingsListSubpage from "./subpages/SettingsListSubpage";
import { SPECIALTY_OPTIONS, setOnboardingState } from "./constants";
import { TYPE, ICON, COLOR, RADIUS } from "../../theme";
import { dp } from "../../utils/doctorBasePath";

function NameDialog({ open, nameInput, nameSaving, nameError, onChange, onSave, onClose }) {
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="设置昵称"
      subtitle="AI 助手将用此姓名称呼您，例如「好的，张医生」"
      desktopMaxWidth={360}
      footer={<DialogFooter onCancel={onClose} onConfirm={onSave} confirmLabel="保存" confirmLoading={nameSaving} confirmLoadingLabel="保存中…" confirmDisabled={nameSaving} />}
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
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger, mt: 1 }}>
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
      footer={<DialogFooter onCancel={onClose} onConfirm={onSave} confirmLabel="保存" confirmLoading={specialtySaving} confirmLoadingLabel="保存中…" confirmDisabled={specialtySaving} />}
    >
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 0.5, mb: 2 }}>
        {SPECIALTY_OPTIONS.map((s) => (
          <Box
            key={s}
            onClick={() => onChange(s)}
            sx={{
              px: 1.5,
              py: 0.5,
              borderRadius: "999px",
              cursor: "pointer",
              fontSize: TYPE.secondary.fontSize,
              bgcolor: specialtyInput === s ? COLOR.primary : COLOR.surface,
              color: specialtyInput === s ? COLOR.white : COLOR.text3,
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
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger, mt: 1 }}>
          {specialtyError}
        </Typography>
      ) : null}
    </SheetDialog>
  );
}


function KnowledgeSubpageWrapper({ doctorId, onBack, isMobile, urlSubId }) {
  const navigate = useAppNavigate();
  const api = useApi();
  const queryClient = useQueryClient();
  const { deleteKnowledgeItem } = api;
  const [stats, setStats] = useState(null);

  // React Query-backed knowledge list (shared cache)
  const { data: kData, isLoading: loading, refetch: refetchItems } = useKnowledgeItems();
  const items = kData ? (Array.isArray(kData) ? kData : (kData.items || [])) : [];
  const persona = kData && !Array.isArray(kData) ? kData.persona : null;

  const load = useCallback(() => {
    refetchItems();
  }, [refetchItems]);

  // Fetch stats (not cached — less critical)
  useEffect(() => {
    if (!doctorId) return;
    (api.fetchKnowledgeStats || (() => Promise.resolve(null)))(doctorId)
      .then((data) => setStats(data?.stats || null))
      .catch(() => null);
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // URL-driven: detail view for specific knowledge item
  if (urlSubId && urlSubId !== "new" && urlSubId !== "add") {
    // "persona" route uses the current doctor's persona ID (not a hardcoded number)
    const resolvedItemId = urlSubId === "persona" ? persona?.id : parseInt(urlSubId);
    if (urlSubId === "persona" && !resolvedItemId && !loading) {
      // Persona not yet created — go back
      navigate(-1);
      return null;
    }
    return (
      <KnowledgeDetailSubpage
        doctorId={doctorId}
        itemId={resolvedItemId}
        isPersona={urlSubId === "persona"}
        onBack={onBack}
        onDelete={async (id) => { await deleteKnowledgeItem(doctorId, id); navigate(-1); load(); }}
        isMobile={isMobile}
      />
    );
  }

  // URL-driven: "new" subpage for adding
  if (urlSubId === "new" || urlSubId === "add") {
    return <AddKnowledgeSubpage doctorId={doctorId} onBack={() => { navigate(-1); load(); }} isMobile={isMobile} />;
  }

  async function handleDelete(itemId) {
    try {
      await deleteKnowledgeItem(doctorId, itemId);
      queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
    } catch {}
  }

  return (
    <KnowledgeSubpage
      items={items}
      stats={stats}
      loading={loading}
      onBack={isMobile ? onBack : undefined}
      onAdd={() => navigate(dp("settings/knowledge/new"))}
      onDelete={handleDelete}
      onItemClick={(id) => navigate(`${dp("settings/knowledge")}/${id}`)}
      persona={persona}
      onPersonaClick={() => navigate(`${dp("settings/knowledge")}/persona`)}
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


function useSettingsState({ doctorId, doctorName, accessToken, setAuth }) {
  const { getDoctorProfile, updateDoctorProfile } = useApi();
  const queryClient = useQueryClient();
  const [nameDialogOpen, setNameDialogOpen] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [nameSaving, setNameSaving] = useState(false);
  const [nameError, setNameError] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [specialtyDialogOpen, setSpecialtyDialogOpen] = useState(false);
  const [specialtyInput, setSpecialtyInput] = useState("");
  const [specialtySaving, setSpecialtySaving] = useState(false);
  const [specialtyError, setSpecialtyError] = useState("");
  const [clinicName, setClinicName] = useState("");
  const [bio, setBio] = useState("");

  useEffect(() => { getDoctorProfile(doctorId).then((p) => { setSpecialty(p.specialty || ""); setClinicName(p.clinic_name || ""); setBio(p.bio || ""); }).catch(() => {}); }, [doctorId]);

  async function handleSaveName() {
    const trimmed = nameInput.trim();
    if (!trimmed) { setNameError("姓名不能为空"); return; }
    setNameSaving(true); setNameError("");
    try { await updateDoctorProfile(doctorId, { name: trimmed }); queryClient.invalidateQueries({ queryKey: QK.doctorProfile(doctorId) }); setAuth(doctorId, trimmed, accessToken); setNameDialogOpen(false); }
    catch (e) { setNameError(e.message || "保存失败"); } finally { setNameSaving(false); }
  }
  async function handleSaveSpecialty() {
    const trimmed = specialtyInput.trim(); setSpecialtySaving(true); setSpecialtyError("");
    try { await updateDoctorProfile(doctorId, { specialty: trimmed || null }); queryClient.invalidateQueries({ queryKey: QK.doctorProfile(doctorId) }); setSpecialty(trimmed); setSpecialtyDialogOpen(false); }
    catch (e) { setSpecialtyError(e.message || "保存失败"); } finally { setSpecialtySaving(false); }
  }

  // Clinic name
  const [clinicDialogOpen, setClinicDialogOpen] = useState(false);
  const [clinicInput, setClinicInput] = useState("");
  const [clinicSaving, setClinicSaving] = useState(false);
  async function handleSaveClinic() {
    const trimmed = clinicInput.trim(); setClinicSaving(true);
    try { await updateDoctorProfile(doctorId, { clinic_name: trimmed || null }); queryClient.invalidateQueries({ queryKey: QK.doctorProfile(doctorId) }); setClinicName(trimmed); setClinicDialogOpen(false); }
    catch {} finally { setClinicSaving(false); }
  }

  // Bio
  const [bioDialogOpen, setBioDialogOpen] = useState(false);
  const [bioInput, setBioInput] = useState("");
  const [bioSaving, setBioSaving] = useState(false);
  async function handleSaveBio() {
    const trimmed = bioInput.trim(); setBioSaving(true);
    try { await updateDoctorProfile(doctorId, { bio: trimmed || null }); queryClient.invalidateQueries({ queryKey: QK.doctorProfile(doctorId) }); setBio(trimmed); setBioDialogOpen(false); }
    catch {} finally { setBioSaving(false); }
  }

  return { nameDialogOpen, setNameDialogOpen, nameInput, setNameInput, nameSaving, nameError, setNameError, specialty, specialtyDialogOpen, setSpecialtyDialogOpen, specialtyInput, setSpecialtyInput, specialtySaving, specialtyError, handleSaveName, handleSaveSpecialty, clinicName, setClinicName, bio, setBio, clinicDialogOpen, setClinicDialogOpen, clinicInput, setClinicInput, clinicSaving, handleSaveClinic, bioDialogOpen, setBioDialogOpen, bioInput, setBioInput, bioSaving, handleSaveBio };
}

export default function SettingsPage({ doctorId, onLogout, urlSubpage, urlSubId }) {
  const navigate = useAppNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const { doctorName, setAuth, accessToken } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();
  const { nameDialogOpen, setNameDialogOpen, nameInput, setNameInput, nameSaving, nameError, setNameError, specialty, specialtyDialogOpen, setSpecialtyDialogOpen, specialtyInput, setSpecialtyInput, specialtySaving, specialtyError, handleSaveName, handleSaveSpecialty, clinicName, setClinicName, bio, setBio, clinicDialogOpen, setClinicDialogOpen, clinicInput, setClinicInput, clinicSaving, handleSaveClinic, bioDialogOpen, setBioDialogOpen, bioInput, setBioInput, bioSaving, handleSaveBio } = useSettingsState({ doctorId, doctorName, accessToken, setAuth });

  const [qrUrl, setQrUrl] = useState("");
  const [qrError, setQrError] = useState("");
  const [qrLoading, setQrLoading] = useState(false);
  const [qrPatientName, setQrPatientName] = useState("");
  const [qrPreviewPath, setQrPreviewPath] = useState("");
  const [qrCopied, setQrCopied] = useState(false);

  async function handleGenerateQR() {
    const patientName = qrPatientName.trim();
    if (!patientName) return;
    setQrLoading(true);
    setQrError("");
    setQrCopied(false);
    try {
      const createEntry = api.createOnboardingPatientEntry || (() => Promise.reject(new Error("缺少预问诊入口接口")));
      const data = await createEntry(doctorId, { patientName });
      queryClient.invalidateQueries({ queryKey: QK.patients(doctorId) });
      setQrUrl(data.portal_url || "");
      const previewParams = new URLSearchParams({
        patient_token: data.portal_token || "",
        patient_name: data.patient_name || patientName,
      });
      setQrPreviewPath(`/doctor/preview/${data.patient_id}?${previewParams.toString()}`);
      setOnboardingState(doctorId, {
        lastPreviewPatientId: data.patient_id,
        lastPreviewPatientName: data.patient_name || patientName,
        lastPreviewToken: data.portal_token || "",
      });
    }
    catch (e) { setQrUrl(""); setQrError(e.message || "生成失败"); }
    finally { setQrLoading(false); }
  }

  async function handleCopyQRLink() {
    if (!qrUrl) return;
    try {
      await navigator.clipboard.writeText(qrUrl);
      setQrCopied(true);
      setTimeout(() => setQrCopied(false), 1800);
    } catch {
      setQrCopied(false);
    }
  }

  /* ── Bulk export ── */
  const BULK_EXPORT_LS_KEY = "bulk_export_task_id";
  const [bulkExportTaskId, setBulkExportTaskId] = useState(() => localStorage.getItem(BULK_EXPORT_LS_KEY) || null);
  const [bulkExportStatus, setBulkExportStatus] = useState("idle"); // idle | generating | ready | failed
  const [bulkExportProgress, setBulkExportProgress] = useState("");
  const [bulkExportConfirmOpen, setBulkExportConfirmOpen] = useState(false);
  const bulkPollRef = useRef(null);

  // Start export after confirm
  async function handleStartBulkExport() {
    setBulkExportConfirmOpen(false);
    setBulkExportStatus("generating");
    setBulkExportProgress("正在准备…");
    try {
      const data = await startBulkExport(doctorId);
      const taskId = data.task_id;
      setBulkExportTaskId(taskId);
      localStorage.setItem(BULK_EXPORT_LS_KEY, taskId);
    } catch (e) {
      setBulkExportStatus("failed");
      setBulkExportProgress(e.message || "启动失败");
      setTimeout(() => { setBulkExportStatus("idle"); setBulkExportProgress(""); }, 3000);
    }
  }

  // Poll while generating
  useEffect(() => {
    if (bulkExportStatus !== "generating" && !bulkExportTaskId) return;

    // On mount: if we have a saved taskId but status is idle, kick off polling
    if (bulkExportTaskId && bulkExportStatus === "idle") {
      setBulkExportStatus("generating");
      setBulkExportProgress("正在恢复状态…");
    }

    if (!bulkExportTaskId) return;

    let cancelled = false;

    async function poll() {
      try {
        const data = await getBulkExportStatus(bulkExportTaskId, doctorId);
        if (cancelled) return;

        if (data.status === "ready" || data.status === "completed") {
          setBulkExportStatus("ready");
          setBulkExportProgress("下载中…");
          try {
            await downloadBulkExport(bulkExportTaskId, doctorId);
          } catch {
            // download trigger may fail silently — file still available
          }
          setBulkExportTaskId(null);
          localStorage.removeItem(BULK_EXPORT_LS_KEY);
          setBulkExportStatus("idle");
          setBulkExportProgress("");
        } else if (data.status === "failed" || data.status === "error") {
          setBulkExportStatus("failed");
          setBulkExportProgress(data.error || "导出失败");
          setBulkExportTaskId(null);
          localStorage.removeItem(BULK_EXPORT_LS_KEY);
          setTimeout(() => { if (!cancelled) { setBulkExportStatus("idle"); setBulkExportProgress(""); } }, 4000);
        } else {
          // still generating
          const done = data.processed ?? data.done ?? 0;
          const total = data.total ?? 0;
          setBulkExportProgress(total > 0 ? `${done}/${total} 患者已处理` : "正在生成…");
        }
      } catch (e) {
        if (!cancelled) {
          // 404 = task not found (stale or wrong doctor) — clear and reset
          if (e.message && (e.message.includes("404") || e.message.includes("not found") || e.message.includes("Not Found"))) {
            setBulkExportTaskId(null);
            localStorage.removeItem(BULK_EXPORT_LS_KEY);
            setBulkExportStatus("idle");
            setBulkExportProgress("");
          } else {
            setBulkExportProgress("轮询出错，重试中…");
          }
        }
      }
    }

    poll(); // initial check
    bulkPollRef.current = setInterval(poll, 3000);

    return () => {
      cancelled = true;
      if (bulkPollRef.current) clearInterval(bulkPollRef.current);
    };
  }, [bulkExportTaskId, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleBulkExportClick() {
    if (bulkExportStatus === "generating") return; // already running
    setBulkExportConfirmOpen(true);
  }

  // URL-driven subpage (survives refresh)
  const subpage = urlSubpage || null;
  const goSub = (sub) => navigate(`${dp("settings")}/${sub}`);
  const goBack = () => navigate(-1);

  // QR subpage — full-page view, auto-generate on mount
  if (subpage === "qr") {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <SubpageHeader title="患者预问诊码" onBack={goBack} />
        <Box sx={{ flex: 1, overflowY: "auto", bgcolor: COLOR.surfaceAlt, px: 2, py: 2 }}>
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, p: 1.5 }}>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
              为患者生成专属入口
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.5, lineHeight: 1.6 }}>
              先建档，再生成可分享的预问诊链接。患者扫码后将直接进入 AI 预问诊。
            </Typography>
            <TextField
              fullWidth
              size="small"
              placeholder="请输入患者姓名，例如：李阿姨"
              value={qrPatientName}
              onChange={(e) => setQrPatientName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleGenerateQR(); }}
              sx={{ mt: 1.5 }}
            />
            <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "1fr", mt: 1.5 }}>
              <AppButton
                variant="primary"
                size="md"
                fullWidth
                disabled={!qrPatientName.trim() || qrLoading}
                loading={qrLoading}
                loadingLabel="生成中…"
                onClick={handleGenerateQR}
              >
                生成入口
              </AppButton>
            </Box>
          </Box>

          {qrError ? (
            <Box sx={{ mt: 1.5, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, p: 1.5 }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.danger }}>
                {qrError}
              </Typography>
            </Box>
          ) : null}

          {qrUrl && (
            <Box sx={{ mt: 1.5, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, p: 2, textAlign: "center" }}>
              <Box sx={{ display: "inline-flex", p: 2.5, bgcolor: COLOR.white, borderRadius: RADIUS.lg, border: `0.5px solid ${COLOR.border}` }}>
                <QRCodeSVG value={qrUrl} size={220} level="M" />
              </Box>
              <Typography sx={{ mt: 1.5, fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.text1 }}>
                {qrPatientName.trim()}
              </Typography>
              <Typography sx={{ mt: 0.5, fontSize: TYPE.caption.fontSize, color: COLOR.text4, lineHeight: 1.6 }}>
                患者扫码后将进入 AI 预问诊，确认提交后自动创建审核任务。
              </Typography>
              <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(2, minmax(0, 1fr))", mt: 1.5 }}>
                <AppButton variant="secondary" size="md" fullWidth onClick={handleCopyQRLink}>
                  {qrCopied ? "已复制" : "复制"}
                </AppButton>
                <AppButton
                  variant="primary"
                  size="md"
                  fullWidth
                  disabled={!qrPreviewPath}
                  onClick={() => qrPreviewPath && navigate(qrPreviewPath)}
                >
                  预览
                </AppButton>
              </Box>
            </Box>
          )}
        </Box>
      </Box>
    );
  }

  // Mobile subpage override
  const mobileSubpage = isMobile && subpage === "persona" ? (
    <PersonaSubpage doctorId={doctorId} onBack={goBack} isMobile />
  ) : isMobile && subpage === "template" ? (
    <TemplateSubpage doctorId={doctorId} onBack={goBack} isMobile />
  ) : isMobile && subpage === "knowledge" ? (
    <KnowledgeSubpageWrapper doctorId={doctorId} onBack={goBack} isMobile urlSubId={urlSubId} />
  ) : isMobile && subpage === "about" ? (
    <AboutSubpage onBack={goBack} isMobile />
  ) : isMobile && subpage === "privacy" ? (
    <PrivacySubpage onBack={goBack} />
  ) : null;

  const listPane = (
    <SettingsListSubpage
      doctorId={doctorId}
      doctorName={doctorName}
      specialty={specialty}
      clinicName={clinicName}
      bio={bio}
      onClinicTap={() => { setClinicInput(clinicName); setClinicDialogOpen(true); }}
      onBioTap={() => { setBioInput(bio); setBioDialogOpen(true); }}
      onTemplate={() => goSub("template")}
      onKnowledge={() => goSub("knowledge")}
      onQRCode={() => goSub("qr")}
      onBulkExport={handleBulkExportClick}
      bulkExportStatus={bulkExportStatus}
      bulkExportProgress={bulkExportProgress}
      onAbout={() => goSub("about")}
      onPrivacy={() => goSub("privacy")}
      onLogout={isMobile ? onLogout : undefined}
      isMobile={isMobile}
    >
      <NameDialog open={nameDialogOpen} nameInput={nameInput} nameSaving={nameSaving} nameError={nameError}
        onChange={setNameInput} onSave={handleSaveName} onClose={() => setNameDialogOpen(false)} />
      <SpecialtyDialog open={specialtyDialogOpen} specialtyInput={specialtyInput} specialtySaving={specialtySaving}
        specialtyError={specialtyError} onChange={setSpecialtyInput} onSave={handleSaveSpecialty} onClose={() => setSpecialtyDialogOpen(false)} />
      <SheetDialog open={clinicDialogOpen} onClose={() => setClinicDialogOpen(false)} title="诊所/医院"
        footer={<AppButton variant="primary" size="md" fullWidth loading={clinicSaving} onClick={handleSaveClinic}>保存</AppButton>}>
        <Box sx={{ px: 0.5 }}>
          <TextField value={clinicInput} onChange={e => setClinicInput(e.target.value)} placeholder="例如：北京协和医院"
            fullWidth size="small" autoFocus />
        </Box>
      </SheetDialog>
      <SheetDialog open={bioDialogOpen} onClose={() => setBioDialogOpen(false)} title="简介"
        footer={<AppButton variant="primary" size="md" fullWidth loading={bioSaving} onClick={handleSaveBio}>保存</AppButton>}>
        <Box sx={{ px: 0.5 }}>
          <TextField value={bioInput} onChange={e => setBioInput(e.target.value)} placeholder="介绍您的专长和经验"
            fullWidth size="small" multiline minRows={3} autoFocus />
        </Box>
      </SheetDialog>
      <ConfirmDialog
        open={bulkExportConfirmOpen}
        onClose={() => setBulkExportConfirmOpen(false)}
        onCancel={() => setBulkExportConfirmOpen(false)}
        onConfirm={handleStartBulkExport}
        title="导出全部数据"
        message="将导出所有患者病历为ZIP文件，可能需要几分钟"
        cancelLabel="取消"
        confirmLabel="开始导出"
      />
    </SettingsListSubpage>
  );

  const detailContent = subpage === "persona" ? (
    <PersonaSubpage doctorId={doctorId} onBack={goBack} />
  ) : subpage === "template" ? (
    <TemplateSubpage doctorId={doctorId} onBack={goBack} />
  ) : subpage === "knowledge" ? (
    <KnowledgeSubpageWrapper doctorId={doctorId} onBack={goBack} isMobile />
  ) : subpage === "about" ? (
    <AboutSubpage onBack={goBack} />
  ) : subpage === "privacy" ? (
    <PrivacySubpage onBack={goBack} />
  ) : null;

  return (
    <PageSkeleton
      title="设置"
      onBack={isMobile ? () => navigate(-1) : undefined}
      isMobile={isMobile}
      mobileView={mobileSubpage}
      listPane={listPane}
      detailPane={detailContent}
    />
  );
}
