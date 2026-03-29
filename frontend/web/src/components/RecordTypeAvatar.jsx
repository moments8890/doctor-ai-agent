/**
 * RecordTypeAvatar — colored icon for record type, shared by doctor and patient views.
 */
import { Box } from "@mui/material";
import { COLOR, RADIUS } from "../theme";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import FileUploadOutlinedIcon from "@mui/icons-material/FileUploadOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";

const CONFIG = {
  visit:              { color: COLOR.primary, Icon: DescriptionOutlinedIcon },
  dictation:          { color: COLOR.recordDoc, Icon: MicNoneOutlinedIcon },
  import:             { color: COLOR.recordDoc, Icon: FileUploadOutlinedIcon },
  lab:                { color: COLOR.accent, Icon: BiotechOutlinedIcon },
  imaging:            { color: COLOR.accent, Icon: MonitorHeartOutlinedIcon },
  surgery:            { color: COLOR.danger, Icon: LocalHospitalOutlinedIcon },
  interview_summary:  { color: COLOR.primary, Icon: ChatOutlinedIcon },
};

const FALLBACK = { color: "#999", Icon: DescriptionOutlinedIcon };

export default function RecordTypeAvatar({ type, size = 36 }) {
  const { color, Icon } = CONFIG[type] || FALLBACK;
  return (
    <Box sx={{
      width: size, height: size, borderRadius: RADIUS.sm,
      bgcolor: color + "1a",
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
    }}>
      <Icon sx={{ fontSize: size * 0.5, color }} />
    </Box>
  );
}
