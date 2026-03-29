/**
 * TemplateSubpage — report template management, extracted from SettingsPage.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, CircularProgress, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import PageSkeleton from "../../../components/PageSkeleton";
import SectionLabel from "../../../components/SectionLabel";
import AppButton from "../../../components/AppButton";
import ConfirmDialog from "../../../components/ConfirmDialog";
import SheetDialog from "../../../components/SheetDialog";
import { useApi } from "../../../api/ApiContext";
import { TYPE, ICON, COLOR } from "../../../theme";

const STANDARD_TEMPLATE_FIELDS = [
  { key: "department", label: "科别", desc: "就诊科室名称" },
  { key: "chief_complaint", label: "主诉", desc: "患者就诊的主要症状及持续时间" },
  { key: "present_illness", label: "现病史", desc: "症状起病、发展、演变的详细过程" },
  { key: "past_history", label: "既往史", desc: "既往疾病、手术、外伤、输血史等" },
  { key: "allergy_history", label: "过敏史", desc: "药物及其他过敏情况" },
  { key: "personal_history", label: "个人史", desc: "吸烟、饮酒、职业暴露等" },
  { key: "marital_reproductive", label: "婚育史", desc: "婚姻、生育情况" },
  { key: "family_history", label: "家族史", desc: "家族遗传病及相关疾病史" },
  { key: "physical_exam", label: "体格检查", desc: "生命体征及系统体格检查结果" },
  { key: "specialist_exam", label: "专科检查", desc: "专科相关的体格检查结果" },
  { key: "auxiliary_exam", label: "辅助检查", desc: "实验室检查、影像学检查结果" },
  { key: "diagnosis", label: "初步诊断", desc: "根据病史和检查做出的初步判断" },
  { key: "treatment_plan", label: "治疗方案", desc: "药物治疗、手术方案、康复计划等" },
  { key: "orders_followup", label: "医嘱及随访", desc: "出院/门诊医嘱、复查安排、注意事项" },
];

function TemplateStatusCard({ loading, status }) {
  const [previewOpen, setPreviewOpen] = useState(false);

  return (
    <>
      <Box sx={{ bgcolor: "#fff", px: 2, py: 2, mb: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box sx={{ width: 44, height: 44, borderRadius: "10px", bgcolor: COLOR.successLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <UploadFileOutlinedIcon sx={{ color: "#07C160", fontSize: ICON.xl }} />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontWeight: 500, fontSize: TYPE.body.fontSize }}>门诊病历报告模板</Typography>
            {loading ? (
              <Typography variant="caption" color="text.secondary">加载中…</Typography>
            ) : status?.has_template ? (
              <Typography variant="caption" color="text.secondary">
                已上传自定义模板（{status.char_count?.toLocaleString()} 字符）
              </Typography>
            ) : (
              <Typography
                variant="caption"
                onClick={() => setPreviewOpen(true)}
                sx={{ color: "#1B6EF3", cursor: "pointer", "&:active": { opacity: 0.6 } }}
              >
                使用国家卫生部 2010 年标准格式 ›
              </Typography>
            )}
          </Box>
          {status?.has_template && (
            <Box sx={{ px: 1, py: 0.5, borderRadius: "10px", bgcolor: COLOR.successLight }}>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#07C160", fontWeight: 600 }}>已自定义</Typography>
            </Box>
          )}
        </Box>
      </Box>

      <SheetDialog
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        title="门诊病历标准格式"
        subtitle="卫医政发〔2010〕11号《病历书写基本规范》"
        desktopMaxWidth={400}
        mobileMaxHeight="78vh"
        footer={
          <AppButton variant="primary" size="md" fullWidth onClick={() => setPreviewOpen(false)}>
            知道了
          </AppButton>
        }
      >
        <Box sx={{ maxHeight: 400, overflowY: "auto" }}>
          {STANDARD_TEMPLATE_FIELDS.map((f, i) => (
            <Box key={f.key} sx={{ py: 1, borderTop: i > 0 ? "0.5px solid #f0f0f0" : "none" }}>
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#1A1A1A", fontWeight: 500 }}>
                {i + 1}. {f.label}
              </Typography>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999", mt: 0.2 }}>
                {f.desc}
              </Typography>
            </Box>
          ))}
        </Box>
      </SheetDialog>
    </>
  );
}

function TemplateActions({ status, uploading, deleting, fileRef, onDelete }) {
  return (
    <Box sx={{ bgcolor: "#fff" }}>
      <Box onClick={() => fileRef.current?.click()}
        sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5,
          borderBottom: status?.has_template ? "1px solid #f2f2f2" : "none",
          cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}>
        {uploading ? <CircularProgress size={18} sx={{ mr: 1.5, color: "#07C160" }} /> : <Box sx={{ width: 18, mr: 1.5 }} />}
        <Typography sx={{ flex: 1, fontSize: TYPE.action.fontSize, color: uploading ? "#999" : "#07C160", fontWeight: 500 }}>
          {uploading ? "上传中…" : status?.has_template ? "替换模板文件" : "上传模板文件"}
        </Typography>
        <ArrowBackIcon sx={{ fontSize: ICON.sm, color: "#ccc", transform: "rotate(180deg)" }} />
      </Box>
      {status?.has_template && (
        <Box onClick={!deleting ? onDelete : undefined}
          sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, cursor: deleting ? "default" : "pointer", "&:active": { bgcolor: COLOR.surface } }}>
          {deleting ? <CircularProgress size={18} sx={{ mr: 1.5, color: COLOR.danger }} /> : <Box sx={{ width: 18, mr: 1.5 }} />}
          <Typography sx={{ flex: 1, fontSize: TYPE.action.fontSize, color: deleting ? "#999" : COLOR.danger }}>
            {deleting ? "删除中…" : "删除模板，恢复默认"}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

function useTemplateState(doctorId) {
  const { getTemplateStatus, uploadTemplate, deleteTemplate } = useApi();
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

export default function TemplateSubpage({ doctorId, onBack, isMobile = true }) {
  const { status, loading, uploading, deleting, msg, setMsg, fileRef, handleUpload, handleDelete } = useTemplateState(doctorId);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const content = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      <SectionLabel>当前模板</SectionLabel>
      <TemplateStatusCard loading={loading} status={status} />
      <SectionLabel sx={{ pt: 0.5 }}>操作</SectionLabel>
      <TemplateActions status={status} uploading={uploading} deleting={deleting} fileRef={fileRef} onDelete={() => setDeleteConfirmOpen(true)} />
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
  );

  return (
    <>
      <PageSkeleton title="报告模板" onBack={onBack} isMobile={isMobile} listPane={content} />
      <ConfirmDialog
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        onCancel={() => setDeleteConfirmOpen(false)}
        onConfirm={async () => { setDeleteConfirmOpen(false); await handleDelete(); }}
        title="删除模板"
        message="删除后将恢复国家卫生部 2010 年标准格式。"
        cancelLabel="保留"
        confirmLabel="确认删除"
        confirmTone="danger"
        confirmLoading={deleting}
        confirmLoadingLabel="删除中…"
      />
    </>
  );
}
