/**
 * PatientOnboarding — single dismissible sheet shown on first login.
 * Scoped to patient_id via localStorage key to handle shared devices.
 */
import { Box, Typography } from "@mui/material";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import NameAvatar from "../../components/NameAvatar";
import IconBadge from "../../components/IconBadge";
import AppButton from "../../components/AppButton";
import { TYPE, COLOR, RADIUS } from "../../theme";

const FEATURES = [
  { icon: ChatOutlinedIcon, bg: COLOR.primary, label: "随时咨询", desc: "AI助手帮你解答健康问题" },
  { icon: DescriptionOutlinedIcon, bg: COLOR.accent, label: "健康档案", desc: "病历和检查结果一目了然" },
  { icon: AssignmentOutlinedIcon, bg: COLOR.warning, label: "任务提醒", desc: "用药和复查不再遗漏" },
];

export default function PatientOnboarding({ doctorName, doctorSpecialty, onDismiss }) {
  return (
    <Box sx={{
      position: "absolute", inset: 0, zIndex: 100, bgcolor: COLOR.white,
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      <Box sx={{
        bgcolor: COLOR.primary, pt: 6, pb: 4, px: 3,
        display: "flex", flexDirection: "column", alignItems: "center",
        background: `linear-gradient(135deg, ${COLOR.primary} 0%, #05a050 100%)`,
      }}>
        <NameAvatar name={doctorName || "医"} size={64} color={COLOR.white} textColor={COLOR.primary} />
        <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.white, mt: 2 }}>
          {doctorName ? `${doctorName}的AI健康助手` : "AI健康助手"}
        </Typography>
        {doctorSpecialty && (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "rgba(255,255,255,0.8)", mt: 0.5 }}>
            {doctorSpecialty}
          </Typography>
        )}
      </Box>

      <Box sx={{ flex: 1, px: 3, py: 3, display: "flex", flexDirection: "column", gap: 2 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text3, textAlign: "center", mb: 1 }}>
          我会帮助{doctorName || "医生"}为你提供更好的随访服务
        </Typography>
        {FEATURES.map(f => (
          <Box key={f.label} sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <IconBadge config={{ icon: f.icon, bg: f.bg }} size={40} solid />
            <Box>
              <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.text1 }}>{f.label}</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>{f.desc}</Typography>
            </Box>
          </Box>
        ))}
      </Box>

      <Box sx={{ px: 3, pb: 4, pt: 1 }}>
        <AppButton variant="primary" size="lg" fullWidth onClick={onDismiss}>
          开始使用
        </AppButton>
      </Box>

      <Typography
        onClick={onDismiss}
        sx={{
          position: "absolute", top: 16, right: 16,
          fontSize: TYPE.secondary.fontSize, color: "rgba(255,255,255,0.7)",
          cursor: "pointer", "&:active": { opacity: 0.5 },
        }}
      >
        跳过
      </Typography>
    </Box>
  );
}
