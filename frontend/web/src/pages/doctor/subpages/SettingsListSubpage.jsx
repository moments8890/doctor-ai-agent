/**
 * SettingsListSubpage — shared presentational settings menu.
 *
 * Displays doctor avatar + account info, tool navigation rows (template,
 * knowledge), general section (about), and logout button.
 * Used by both real SettingsPage (API data) and MockPages (static data).
 *
 * @see /debug/doctor-pages → 设置
 */
import { Box, CircularProgress, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import PolicyOutlinedIcon from "@mui/icons-material/PolicyOutlined";
import PageSkeleton from "../../../components/PageSkeleton";
import SectionLabel from "../../../components/SectionLabel";
import { TYPE, ICON, COLOR } from "../../../theme";

/* ── SettingsRow — icon-adorned navigation row ── */

function SettingsRow({ icon, label, sublabel, onClick, danger }) {
  return (
    <Box onClick={onClick} sx={{
      display: "flex", alignItems: "center", px: 2, py: 1.5,
      cursor: onClick ? "pointer" : "default",
      borderBottom: "0.5px solid #f0f0f0",
      "&:active": onClick ? { bgcolor: "#f9f9f9" } : {},
    }}>
      <Box sx={{
        width: 36, height: 36, borderRadius: "4px",
        bgcolor: danger ? "#fef2f2" : "#f0faf4",
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0, mr: 1.5,
      }}>
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

/* ── AccountBlock — doctor avatar + name + info ── */

function AccountBlock({ doctorId, doctorName, specialty, clinicName, bio, onClinicTap, onBioTap }) {
  return (
    <Box sx={{ bgcolor: "#fff" }}>
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.8, borderBottom: "0.5px solid #f0f0f0" }}>
        <Box sx={{
          width: 52, height: 52, borderRadius: "4px", bgcolor: COLOR.primary,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, mr: 1.5,
        }}>
          <Typography sx={{ color: "#fff", fontSize: ICON.xl, fontWeight: 600 }}>
            {(doctorName || doctorId || "?").slice(-1)}
          </Typography>
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize }}>{doctorName || doctorId}</Typography>
          <Typography variant="caption" color="text.secondary">{doctorId}</Typography>
        </Box>
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "0.5px solid #f0f0f0" }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#111", flex: 1 }}>昵称</Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#999", mr: 0.8 }}>{doctorName || "未设置"}</Typography>
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "0.5px solid #f0f0f0" }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#111", flex: 1 }}>科室专业</Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#999", mr: 0.8 }}>{specialty || "未设置"}</Typography>
      </Box>
      <Box onClick={onClinicTap} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "0.5px solid #f0f0f0", cursor: onClinicTap ? "pointer" : "default", "&:active": onClinicTap ? { bgcolor: "#f9f9f9" } : {} }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#111", flex: 1 }}>诊所/医院</Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#999", mr: 0.8 }}>{clinicName || "未设置"}</Typography>
      </Box>
      <Box onClick={onBioTap} sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderTop: "0.5px solid #f0f0f0", cursor: onBioTap ? "pointer" : "default", "&:active": onBioTap ? { bgcolor: "#f9f9f9" } : {} }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#111", flex: 1 }}>简介</Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#999", mr: 0.8 }} noWrap>{bio || "未设置"}</Typography>
      </Box>
    </Box>
  );
}

/* ── BulkExportRow — shows spinner + progress while generating ── */

function BulkExportRow({ status, progress, onClick }) {
  const generating = status === "generating";
  const failed = status === "failed";

  const sublabel = generating ? progress
    : failed ? progress || "导出失败"
    : "下载所有患者病历 (ZIP)";

  return (
    <Box onClick={generating ? undefined : onClick} sx={{
      display: "flex", alignItems: "center", px: 2, py: 1.5,
      cursor: generating ? "default" : "pointer",
      borderBottom: "0.5px solid #f0f0f0",
      "&:active": generating ? {} : { bgcolor: "#f9f9f9" },
      opacity: generating ? 0.75 : 1,
    }}>
      <Box sx={{
        width: 36, height: 36, borderRadius: "4px",
        bgcolor: failed ? "#fef2f2" : "#f0f0fa",
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0, mr: 1.5,
      }}>
        {generating
          ? <CircularProgress size={18} sx={{ color: "#7b61ff" }} />
          : <FileDownloadOutlinedIcon sx={{ color: failed ? "#FA5151" : "#7b61ff", fontSize: ICON.lg }} />
        }
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: failed ? "#FA5151" : "#111" }}>导出全部数据</Typography>
        <Typography variant="caption" color="text.secondary">{sublabel}</Typography>
      </Box>
      {!generating && !failed && <ArrowBackIcon sx={{ fontSize: ICON.sm, color: "#ccc", transform: "rotate(180deg)" }} />}
    </Box>
  );
}

/* ── Main ── */

export default function SettingsListSubpage({
  doctorId,
  doctorName,
  specialty,
  clinicName,
  bio,
  onClinicTap,
  onBioTap,
  onTemplate,
  onKnowledge,
  onQRCode,
  onBulkExport,
  bulkExportStatus = "idle",
  bulkExportProgress = "",
  onAbout,
  onPrivacy,
  onLogout,
  isMobile = true,
  children,
}) {
  const content = (
    <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
      <SectionLabel>账户</SectionLabel>
      <AccountBlock doctorId={doctorId} doctorName={doctorName} specialty={specialty} clinicName={clinicName} bio={bio} onClinicTap={onClinicTap} onBioTap={onBioTap} />

      <SectionLabel>工具</SectionLabel>
      <Box sx={{ bgcolor: "#fff" }}>
        <SettingsRow icon={<UploadFileOutlinedIcon sx={{ color: COLOR.primary, fontSize: ICON.lg }} />}
          label="报告模板" sublabel="自定义门诊病历报告格式" onClick={onTemplate} />
        <SettingsRow icon={<MenuBookOutlinedIcon sx={{ color: "#5b9bd5", fontSize: ICON.lg }} />}
          label="知识库" sublabel="管理 AI 助手参考资料" onClick={onKnowledge} />
        <SettingsRow icon={<QrCode2OutlinedIcon sx={{ color: "#e8833a", fontSize: ICON.lg }} />}
          label="我的二维码" sublabel="扫码登录其他设备" onClick={onQRCode} />
        <BulkExportRow status={bulkExportStatus} progress={bulkExportProgress} onClick={onBulkExport} />
      </Box>

      <SectionLabel>通用</SectionLabel>
      <Box sx={{ bgcolor: "#fff" }}>
        <SettingsRow icon={<InfoOutlinedIcon sx={{ color: "#999", fontSize: ICON.lg }} />}
          label="关于" sublabel="版本信息" onClick={onAbout} />
        <SettingsRow icon={<PolicyOutlinedIcon sx={{ color: "#999", fontSize: ICON.lg }} />}
          label="隐私政策" sublabel="数据使用与保护" onClick={onPrivacy} />
      </Box>

      {onLogout && (
        <>
          <SectionLabel>账户操作</SectionLabel>
          <Box onClick={onLogout} sx={{
            bgcolor: "#fff", py: 1.5, textAlign: "center", cursor: "pointer",
            borderBottom: "0.5px solid #f0f0f0", "&:active": { bgcolor: "#f9f9f9" },
          }}>
            <Typography sx={{ fontSize: TYPE.action.fontSize, color: "#FA5151" }}>退出登录</Typography>
          </Box>
        </>
      )}
      <Box sx={{ height: 32 }} />
      {children}
    </Box>
  );

  return content;
}
