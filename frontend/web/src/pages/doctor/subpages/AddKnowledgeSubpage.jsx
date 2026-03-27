/**
 * AddKnowledgeSubpage — add knowledge item form, extracted from SettingsPage.
 */
import { useState } from "react";
import { Alert, Box, TextField, Typography } from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import PageSkeleton from "../../../components/PageSkeleton";
import BarButton from "../../../components/BarButton";
import AppButton from "../../../components/AppButton";
import SheetDialog from "../../../components/SheetDialog";
import { addKnowledgeItem } from "../../../api";
import { TYPE } from "../../../theme";

export const KNOWLEDGE_CATEGORIES = [
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

export default function AddKnowledgeSubpage({ doctorId, onBack, isMobile, categories = KNOWLEDGE_CATEGORIES }) {
  const [category, setCategory] = useState("interview_guide");
  const [content, setContent] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);

  const cats = categories;
  const catDef = cats.find((c) => c.key === category) || cats[0];

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

  const formContent = (
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
            {cats.map((c) => {
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
  );

  return (
    <>
      <PageSkeleton
        title="添加知识"
        onBack={isMobile ? onBack : undefined}
        headerRight={<BarButton onClick={handleAdd} loading={adding} disabled={!content.trim()}>添加</BarButton>}
        isMobile={isMobile}
        listPane={formContent}
      />
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
    </>
  );
}
