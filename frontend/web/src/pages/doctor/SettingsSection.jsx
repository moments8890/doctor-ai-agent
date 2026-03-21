/**
 * 设置面板：医生账户信息编辑、科室专业设置、报告模板管理和退出登录。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert, Box, Button, CircularProgress, Dialog, Stack, TextField, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import LogoutIcon from "@mui/icons-material/Logout";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import SubpageHeader from "./SubpageHeader";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { getDoctorProfile, updateDoctorProfile, getTemplateStatus, uploadTemplate, deleteTemplate, getKnowledgeItems, deleteKnowledgeItem, addKnowledgeItem } from "../../api";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import AddIcon from "@mui/icons-material/Add";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import EmptyState from "../../components/EmptyState";
import SectionLabel from "../../components/SectionLabel";
import BarButton from "../../components/BarButton";
import DetailCard from "../../components/DetailCard";
import AskAIBar from "../../components/AskAIBar";
import PageSkeleton from "../../components/PageSkeleton";
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

function NameDialog({ open, isMobile, nameInput, nameSaving, nameError, onChange, onSave, onClose }) {
  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "12px 12px 0 0", width: "100%" } : { borderRadius: 2, minWidth: 300 } }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, mb: 0.5, color: "#333" }}>设置昵称</Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999", mb: 2 }}>AI 助手将用此姓名称呼您，例如「好的，张医生」</Typography>
        <TextField fullWidth size="small" placeholder="请输入您的姓名（如：张伟）"
          value={nameInput} onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSave(); }}
          autoFocus sx={{ mb: nameError ? 0.5 : 2 }} />
        {nameError && <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#FA5151", mb: 1.5 }}>{nameError}</Typography>}
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: TYPE.body.fontSize, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!nameSaving ? onSave : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#07C160", cursor: nameSaving ? "default" : "pointer", fontSize: TYPE.heading.fontSize, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
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
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, mb: 2, color: "#333" }}>科室专业</Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.8, mb: 2 }}>
          {SPECIALTY_OPTIONS.map((s) => (
            <Box key={s} onClick={() => onChange(s)}
              sx={{ px: 1.4, py: 0.4, borderRadius: "4px", cursor: "pointer", fontSize: TYPE.secondary.fontSize,
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
        {specialtyError && <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#FA5151", mb: 1.5 }}>{specialtyError}</Typography>}
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: TYPE.body.fontSize, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={!specialtySaving ? onSave : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#07C160", cursor: specialtySaving ? "default" : "pointer", fontSize: TYPE.heading.fontSize, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
            {specialtySaving ? "保存中…" : "保存"}
          </Box>
        </Box>
      </Box>
    </Dialog>
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
  const showDefault = !loading && !status?.has_template;

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

      {/* Standard template preview dialog */}
      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)}
        PaperProps={{ sx: { borderRadius: "6px", maxWidth: 400, mx: 2 } }}>
        <Box sx={{ p: 2.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, color: "#1A1A1A", mb: 0.5 }}>
            门诊病历标准格式
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999", mb: 2 }}>
            卫医政发〔2010〕11号《病历书写基本规范》
          </Typography>
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
          <Box sx={{ mt: 2, textAlign: "center" }}>
            <Box onClick={() => setPreviewOpen(false)}
              sx={{ fontSize: TYPE.body.fontSize, color: "#1B6EF3", cursor: "pointer", py: 0.5, "&:active": { opacity: 0.6 } }}>
              知道了
            </Box>
          </Box>
        </Box>
      </Dialog>
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

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title="报告模板" onBack={isMobile ? onBack : undefined} />
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        <SectionLabel>当前模板</SectionLabel>
        <TemplateStatusCard loading={loading} status={status} />
        <SectionLabel sx={{ pt: 0.5 }}>操作</SectionLabel>
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

      {/* Help dialog with examples */}
      <Dialog
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        PaperProps={{ sx: { borderRadius: "6px", minWidth: 280, maxWidth: 340 } }}
      >
        <Box sx={{ p: 2.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, color: "#1A1A1A", mb: 1.5 }}>
            {catDef.label} — 示例
          </Typography>
          {catDef.examples.map((ex, i) => (
            <Box key={i} sx={{ bgcolor: "#f7f7f7", borderRadius: "4px", p: 1.5, mb: 1 }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#333", lineHeight: 1.6 }}>{ex}</Typography>
            </Box>
          ))}
          <Button
            fullWidth
            size="small"
            onClick={() => setHelpOpen(false)}
            sx={{ mt: 1, color: "#1B6EF3", textTransform: "none" }}
          >
            知道了
          </Button>
        </Box>
      </Dialog>
    </Box>
  );
}

function KnowledgeSubpage({ doctorId, onBack, isMobile }) {
  const [items, setItems] = useState([]);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedCat, setExpandedCat] = useState(null);
  const [subpage, setSubpage] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      getKnowledgeItems(doctorId),
      Promise.resolve({ cases: [] }),
    ]).then(([kData, cData]) => {
      setItems(Array.isArray(kData) ? kData : (kData.items || []));
      setCases(Array.isArray(cData) ? cData : (cData.cases || []));
    }).catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [doctorId]);
  useEffect(() => { load(); }, [load]);

  const grouped = useMemo(() => {
    const groups = {};
    KNOWLEDGE_CATEGORIES.forEach((c) => { groups[c.key] = []; });
    items.forEach((item) => {
      const cat = item.category || "custom";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(item);
    });
    return groups;
  }, [items]);

  const [deleteConfirm, setDeleteConfirm] = useState(null); // itemId to confirm

  async function handleDelete(itemId) {
    setDeleteConfirm(null);
    try {
      await deleteKnowledgeItem(doctorId, itemId);
      setItems((prev) => prev.filter((i) => i.id !== itemId));
      // If deleting from detail view, go back to list
      if (subpage?.knowledgeItem?.id === itemId) setSubpage(null);
    } catch (e) {
      setError(e.message || "删除失败");
    }
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  }

  function sourceBadge(source) {
    const isAuto = source === "agent_auto" || source === "AI学习";
    return (
      <Box sx={{
        display: "inline-flex", px: 0.8, py: 0.2, borderRadius: "4px", fontSize: TYPE.micro.fontSize, fontWeight: 500, flexShrink: 0,
        bgcolor: isAuto ? "#E8F5E9" : "#E8F0FE",
        color: isAuto ? "#07C160" : "#1B6EF3",
      }}>
        {isAuto ? "AI学习" : "医生"}
      </Box>
    );
  }

  // Subpage routing
  if (subpage === "add") {
    return <AddKnowledgeSubpage doctorId={doctorId} onBack={() => { setSubpage(null); load(); }} isMobile={isMobile} />;
  }
  if (subpage && subpage.knowledgeItem) {
    const ki = subpage.knowledgeItem;
    const catLabel = KNOWLEDGE_CATEGORIES.find((c) => c.key === ki.category)?.label || "自定义";
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
        <SubpageHeader title="知识详情" onBack={isMobile ? () => setSubpage(null) : undefined}
          right={<BarButton onClick={() => setDeleteConfirm(ki.id)} color="#FA5151">删除</BarButton>}
        />
        <Box sx={{ flex: 1, overflowY: "auto" }}>
          <DetailCard
            title={catLabel}
            fields={[
              { label: "来源", value: ki.source === "agent_auto" || ki.source === "AI学习" ? "AI学习" : "医生" },
              { label: "添加时间", value: formatDate(ki.created_at) },
              { label: "AI引用", value: `${ki.reference_count || 0}次` },
            ]}
            note={ki.text || ki.content}
            noteLabel="内容"
          />
        </Box>

        <Dialog open={deleteConfirm != null} onClose={() => setDeleteConfirm(null)}
          PaperProps={{ sx: { borderRadius: "6px", minWidth: 280 } }}>
          <Box sx={{ p: 2.5 }}>
            <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, color: "#1A1A1A", mb: 1 }}>确认删除</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#666", mb: 2 }}>删除后该知识将不再影响AI行为，确定要删除吗？</Typography>
            <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1 }}>
              <Button size="small" onClick={() => setDeleteConfirm(null)} sx={{ color: "#666" }}>取消</Button>
              <Button size="small" onClick={() => handleDelete(deleteConfirm)}
                sx={{ color: "#E8533F", fontWeight: 600 }}>删除</Button>
            </Box>
          </Box>
        </Dialog>
      </Box>
    );
  }
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader
        title="知识库"
        onBack={isMobile ? onBack : undefined}
        right={
          <BarButton onClick={() => setSubpage("add")}>添加</BarButton>
        }
      />
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {error && <Alert severity="error" onClose={() => setError("")} sx={{ mx: 2, mt: 1.5 }}>{error}</Alert>}

        {loading && <Box sx={{ textAlign: "center", py: 4 }}><CircularProgress size={20} /></Box>}

        {!loading && (
          <>
            {/* Summary line */}
            <Box sx={{ px: 2, py: 1.5 }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>
                共 {items.length} 条知识{cases.length > 0 ? ` · ${cases.length} 个病例` : ""}
              </Typography>
            </Box>

            {/* Category accordions */}
            <Box sx={{ bgcolor: "#fff", borderTop: "0.5px solid #E5E5E5", borderBottom: "0.5px solid #E5E5E5" }}>
              {KNOWLEDGE_CATEGORIES.map((cat, catIdx) => {
                const catItems = grouped[cat.key] || [];
                const isExpanded = expandedCat === cat.key;
                return (
                  <Box key={cat.key}>
                    {/* Category header row */}
                    <Box
                      role="button"
                      tabIndex={0}
                      onClick={() => setExpandedCat(isExpanded ? null : cat.key)}
                      onKeyDown={(e) => { if (e.key === "Enter") setExpandedCat(isExpanded ? null : cat.key); }}
                      sx={{
                        display: "flex", alignItems: "center", px: 2, py: 1.5,
                        cursor: "pointer", userSelect: "none", WebkitTapHighlightColor: "transparent",
                        borderTop: catIdx > 0 ? "0.5px solid #f0f0f0" : "none",
                        "&:active": { bgcolor: "#f9f9f9" },
                      }}
                    >
                      <Box sx={{ flex: 1 }}>
                        <Typography component="span" sx={{ fontSize: TYPE.body.fontSize, color: "#1A1A1A", fontWeight: 500 }}>
                          {cat.label}
                        </Typography>
                        <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: "#999", ml: 0.8 }}>
                          ({catItems.length})
                        </Typography>
                      </Box>
                      {isExpanded
                        ? <ExpandMoreIcon sx={{ fontSize: ICON.lg, color: "#999" }} />
                        : <ChevronRightIcon sx={{ fontSize: ICON.lg, color: "#ccc" }} />
                      }
                    </Box>

                    {/* Expanded items */}
                    {isExpanded && catItems.length > 0 && catItems.map((item) => (
                      <Box
                        key={item.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => setSubpage({ knowledgeItem: item })}
                        sx={{
                          display: "flex", alignItems: "center", px: 2, py: 1.2, pl: 3,
                          borderTop: "0.5px solid #f0f0f0",
                          bgcolor: "#fafafa",
                          cursor: "pointer", userSelect: "none",
                          "&:active": { bgcolor: "#f0f0f0" },
                        }}
                      >
                        <Box sx={{ flex: 1, minWidth: 0, mr: 1 }}>
                          <Typography
                            sx={{
                              fontSize: TYPE.secondary.fontSize, color: "#333", lineHeight: 1.5,
                              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            }}
                          >
                            {item.text || item.content}
                          </Typography>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, mt: 0.3 }}>
                            {sourceBadge(item.source)}
                            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }}>
                              {formatDate(item.created_at)}
                            </Typography>
                            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }}>
                              · AI引用 {item.reference_count || 0}次
                            </Typography>
                          </Box>
                        </Box>
                        <ChevronRightIcon sx={{ fontSize: ICON.lg, color: "#ccc", flexShrink: 0 }} />
                      </Box>
                    ))}
                    {isExpanded && catItems.length === 0 && (
                      <Box sx={{ px: 3, py: 1.5, borderTop: "0.5px solid #f0f0f0", bgcolor: "#fafafa" }}>
                        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>暂无条目</Typography>
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Box>

            {/* Case library section */}
            {cases.length > 0 && (
              <>
                <SectionLabel>病例库</SectionLabel>
                <Box sx={{ bgcolor: "#fff", borderTop: "0.5px solid #E5E5E5", borderBottom: "0.5px solid #E5E5E5" }}>
                  {cases.map((c, i) => (
                    <Box
                      key={c.id}
                      onClick={() => setSubpage({ caseId: c.id })}
                      sx={{
                        display: "flex", alignItems: "center", px: 2, py: 1.5,
                        cursor: "pointer",
                        borderTop: i > 0 ? "0.5px solid #f0f0f0" : "none",
                        "&:active": { bgcolor: "#f9f9f9" },
                      }}
                    >
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#1A1A1A", fontWeight: 500, mb: 0.3 }}>
                          {c.chief_complaint || "未知主诉"}{c.final_diagnosis ? ` → ${c.final_diagnosis}` : ""}
                        </Typography>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                          {c.confidence_status === "confirmed" && (
                            <Box sx={{
                              display: "inline-flex", px: 0.8, py: 0.2, borderRadius: "4px", fontSize: TYPE.micro.fontSize,
                              fontWeight: 500, bgcolor: "#E8F5E9", color: "#07C160",
                            }}>
                              已确认
                            </Box>
                          )}
                          {c.reference_count != null && (
                            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }}>
                              AI引用 {c.reference_count}次
                            </Typography>
                          )}
                        </Box>
                      </Box>
                      <ChevronRightIcon sx={{ fontSize: ICON.lg, color: "#ccc", flexShrink: 0 }} />
                    </Box>
                  ))}
                </Box>
              </>
            )}

            {/* Empty state */}
            {items.length === 0 && cases.length === 0 && (
              <EmptyState
                icon={<MenuBookOutlinedIcon />}
                title="暂无知识条目"
                subtitle="点击右上角「添加」开始构建您的知识库"
              />
            )}

            <Box sx={{ height: 24 }} />
          </>
        )}
      </Box>

      {/* Delete confirmation dialog */}
      <Dialog open={deleteConfirm != null} onClose={() => setDeleteConfirm(null)}
        PaperProps={{ sx: { borderRadius: "6px", minWidth: 280 } }}>
        <Box sx={{ p: 2.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, color: "#1A1A1A", mb: 1 }}>确认删除</Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#666", mb: 2 }}>删除后该知识将不再影响AI行为，确定要删除吗？</Typography>
          <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1 }}>
            <Button size="small" onClick={() => setDeleteConfirm(null)} sx={{ color: "#666" }}>取消</Button>
            <Button size="small" onClick={() => handleDelete(deleteConfirm)}
              sx={{ color: "#E8533F", fontWeight: 600 }}>删除</Button>
          </Box>
        </Box>
      </Dialog>
    </Box>
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

export default function SettingsSection({ doctorId, onLogout, urlSubpage, urlSubId }) {
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
    <KnowledgeSubpage doctorId={doctorId} onBack={goBack} isMobile />
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
      <NameDialog open={nameDialogOpen} isMobile={isMobile} nameInput={nameInput} nameSaving={nameSaving} nameError={nameError}
        onChange={setNameInput} onSave={handleSaveName} onClose={() => setNameDialogOpen(false)} />
      <SpecialtyDialog open={specialtyDialogOpen} isMobile={isMobile} specialtyInput={specialtyInput} specialtySaving={specialtySaving}
        specialtyError={specialtyError} onChange={setSpecialtyInput} onSave={handleSaveSpecialty} onClose={() => setSpecialtyDialogOpen(false)} />
    </Box>
  );

  const detailContent = subpage === "template" ? (
    <TemplateSubpage doctorId={doctorId} onBack={goBack} />
  ) : subpage === "knowledge" ? (
    <KnowledgeSubpage doctorId={doctorId} onBack={goBack} />
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
