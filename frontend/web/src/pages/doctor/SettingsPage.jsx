/**
 * @route /doctor/settings
 *
 * 设置面板：医生账户信息编辑、科室专业设置、报告模板管理和退出登录。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert, Box, CircularProgress, Stack, TextField, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import SubpageHeader from "../../components/SubpageHeader";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { getDoctorProfile, updateDoctorProfile, getTemplateStatus, uploadTemplate, deleteTemplate, getKnowledgeItems, deleteKnowledgeItem, addKnowledgeItem } from "../../api";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import EmptyState from "../../components/EmptyState";
import SectionLabel from "../../components/SectionLabel";
import BarButton from "../../components/BarButton";
import DetailCard from "../../components/DetailCard";
import AppButton from "../../components/AppButton";
import ConfirmDialog from "../../components/ConfirmDialog";
import PageSkeleton from "../../components/PageSkeleton";
import SheetDialog from "../../components/SheetDialog";
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
      <Box sx={{ bgcolor: "#fff", px: 2, py: 2, mb: 0.8 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box sx={{ width: 44, height: 44, borderRadius: "10px", bgcolor: "#e8f5e9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
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
            <Box sx={{ px: 1, py: 0.3, borderRadius: "10px", bgcolor: "#e8f5e9" }}>
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
        sx={{ display: "flex", alignItems: "center", px: 2, py: 1.6,
          borderBottom: status?.has_template ? "1px solid #f2f2f2" : "none",
          cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
        {uploading ? <CircularProgress size={18} sx={{ mr: 1.5, color: "#07C160" }} /> : <Box sx={{ width: 18, mr: 1.5 }} />}
        <Typography sx={{ flex: 1, fontSize: TYPE.action.fontSize, color: uploading ? "#999" : "#07C160", fontWeight: 500 }}>
          {uploading ? "上传中…" : status?.has_template ? "替换模板文件" : "上传模板文件"}
        </Typography>
        <ArrowBackIcon sx={{ fontSize: ICON.sm, color: "#ccc", transform: "rotate(180deg)" }} />
      </Box>
      {status?.has_template && (
        <Box onClick={!deleting ? onDelete : undefined}
          sx={{ display: "flex", alignItems: "center", px: 2, py: 1.6, cursor: deleting ? "default" : "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
          {deleting ? <CircularProgress size={18} sx={{ mr: 1.5, color: "#FA5151" }} /> : <Box sx={{ width: 18, mr: 1.5 }} />}
          <Typography sx={{ flex: 1, fontSize: TYPE.action.fontSize, color: deleting ? "#999" : "#FA5151" }}>
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

function TemplateSubpage({ doctorId, onBack, isMobile }) {
  const { status, loading, uploading, deleting, msg, setMsg, fileRef, handleUpload, handleDelete } = useTemplateState(doctorId);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title="报告模板" onBack={isMobile ? onBack : undefined} />
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
    </Box>
  );
}

const KNOWLEDGE_CATEGORIES = [
  {
    key: "interview_guide", label: "问诊指导",
    placeholder: "描述问诊时的追问策略，例如：遇到头痛患者，先问发作方式……",
    examples: [
      "头痛问诊要点：先问发作方式（突发/渐进），突发性头痛需立即追问是否为雷击样头痛（seconds to peak），同时询问恶心呕吐、视物模糊、意识改变等伴随症状",
      "肢体无力问诊流程：首先区分急性（<24h）还是慢性，急性起病优先考虑卒中——追问发病具体时间、是否伴言语障碍或面部不对称、既往房颤/高血压病史",
    ],
  },
  {
    key: "diagnosis_rule", label: "诊断规则",
    placeholder: "描述症状组合与诊断的对应关系，例如：出现A+B+C时考虑X……",
    examples: [
      "头痛+恶心呕吐+视乳头水肿三联征→高度怀疑颅内高压，需紧急行头颅CT排除占位性病变，老年患者同时需排除慢性硬膜下血肿",
      "突发剧烈头痛（雷击样）+颈项强直+Kernig征阳性→首先考虑蛛网膜下腔出血（SAH），立即CT平扫，阴性不排除需腰穿",
    ],
  },
  {
    key: "red_flag", label: "危险信号",
    placeholder: "描述需要紧急处理的临床场景，例如：出现某症状时立即……",
    examples: [
      "雷击样头痛（数秒内达峰值）→无论其他症状如何，必须立即排除SAH，不能等待，先CT后腰穿，时间窗至关重要",
      "进行性双下肢无力+鞍区感觉减退+大小便功能障碍→马尾综合征，24小时内手术减压，延迟可导致永久性神经损害",
    ],
  },
  {
    key: "treatment_protocol", label: "治疗方案",
    placeholder: "描述特定疾病的治疗方案或用药原则，例如：某病的标准处理流程……",
    examples: [
      "脑膜瘤术后标准方案：地塞米松10mg术中→术后4mg q6h×3天→逐渐减量，抗癫痫预防用药至少1周，Simpson分级决定是否需辅助放疗",
      "颅内高压急性期处理：甘露醇125ml快速静滴q6-8h，注意监测电解质和肾功能，持续>72h需考虑手术减压或脑室外引流",
    ],
  },
  {
    key: "custom", label: "自定义",
    placeholder: "任何您希望AI了解的临床经验或工作习惯",
    examples: [
      "我对65岁以上患者倾向保守治疗方案，除非有明确手术指征且全身状况允许，需综合评估心肺功能和家属意愿",
      "本院MRI预约通常需3个工作日，急诊MRI需神经外科主任签字审批。CT当天可出结果，建议紧急情况优先用CT筛查",
    ],
  },
];

function AddKnowledgeSubpage({ doctorId, onBack, isMobile }) {
  const [category, setCategory] = useState("interview_guide");
  const [content, setContent] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);

  const catDef = KNOWLEDGE_CATEGORIES.find((c) => c.key === category) || KNOWLEDGE_CATEGORIES[0];

  async function handleAdd() {
    const trimmed = content.trim();
    if (!trimmed) return;
    setAdding(true); setError("");
    try {
      await addKnowledgeItem(doctorId, trimmed, category);
      onBack();
    } catch (e) {
      setError(e.message || "添加失败");
    } finally {
      setAdding(false);
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title="添加知识" onBack={isMobile ? onBack : undefined}
        right={<BarButton onClick={handleAdd} loading={adding} disabled={!content.trim()}>添加</BarButton>}
      />
      <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
        {error && <Alert severity="error" onClose={() => setError("")} sx={{ mb: 1.5 }}>{error}</Alert>}

        {/* Category selector */}
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: "#1A1A1A" }}>类别</Typography>
            <HelpOutlineIcon
              onClick={() => setHelpOpen(true)}
              sx={{ fontSize: TYPE.title.fontSize, color: "#999", ml: 0.5, cursor: "pointer" }}
            />
          </Box>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            {KNOWLEDGE_CATEGORIES.map((c) => {
              const isActive = category === c.key;
              return (
                <Box
                  key={c.key}
                  component="button"
                  onClick={() => setCategory(c.key)}
                  sx={{
                    display: "inline-flex", alignItems: "center", px: 1.5, py: 0.6,
                    border: "none", borderRadius: "4px", cursor: "pointer",
                    fontSize: TYPE.secondary.fontSize, fontFamily: "inherit", whiteSpace: "nowrap",
                    backgroundColor: isActive ? "#07C160" : "#fff",
                    color: isActive ? "#fff" : "#333",
                    boxShadow: isActive ? "none" : "0 1px 2px rgba(0,0,0,0.08)",
                    transition: "background-color 0.15s, color 0.15s",
                    "&:active": { opacity: 0.7 },
                  }}
                >
                  {c.label}
                </Box>
              );
            })}
          </Box>
        </Box>

        {/* Content input */}
        <Box sx={{ mb: 2 }}>
          <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: "#1A1A1A", mb: 1 }}>内容</Typography>
          <TextField
            fullWidth
            multiline
            minRows={4}
            maxRows={8}
            size="small"
            placeholder={catDef.placeholder}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: "6px" } }}
          />
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999", mt: 0.5 }}>
            用自然语言描述，AI会在相关场景中参考
          </Typography>
        </Box>

      </Box>

      <SheetDialog
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title={`${catDef.label} · 示例`}
        desktopMaxWidth={360}
        mobileMaxHeight="76vh"
        footer={
          <AppButton variant="primary" size="md" fullWidth onClick={() => setHelpOpen(false)}>
            知道了
          </AppButton>
        }
      >
        {catDef.examples.map((ex, i) => (
          <Box key={i} sx={{ bgcolor: "#f7f7f7", borderRadius: "4px", p: 1.5, mb: i < catDef.examples.length - 1 ? 1 : 0 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#333", lineHeight: 1.6 }}>{ex}</Typography>
          </Box>
        ))}
      </SheetDialog>
    </Box>
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
    />
  );
}


function AboutSubpage({ onBack, isMobile }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title="关于" onBack={isMobile ? onBack : undefined} />
      <Box sx={{ flex: 1, overflowY: "auto", p: 3, textAlign: "center" }}>
        <Box sx={{ width: 64, height: 64, borderRadius: "16px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", mx: "auto", mb: 2 }}>
          <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: ICON.display }} />
        </Box>
        <Typography sx={{ fontWeight: 700, fontSize: TYPE.title.fontSize, mb: 0.5 }}>AI 医疗助手</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 3 }}>版本 1.0.0</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
          智能医疗助手为医生提供 AI 辅助病历记录、患者管理和任务跟踪功能，帮助提升诊疗效率。
        </Typography>
      </Box>
    </Box>
  );
}

function StubSubpage({ title, onBack, isMobile }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title={title} onBack={isMobile ? onBack : undefined} />
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
