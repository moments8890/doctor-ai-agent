import { Box, Slide, Typography } from "@mui/material";
import CameraAltOutlinedIcon from "@mui/icons-material/CameraAltOutlined";
import PhotoLibraryOutlinedIcon from "@mui/icons-material/PhotoLibraryOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PersonSearchOutlinedIcon from "@mui/icons-material/PersonSearchOutlined";
import { TYPE, ICON } from "../theme";

const actions = [
  { key: "camera", label: "拍照", Icon: CameraAltOutlinedIcon, color: "#07C160" },
  { key: "gallery", label: "相册", Icon: PhotoLibraryOutlinedIcon, color: "#5b9bd5" },
  { key: "file", label: "文档", Icon: DescriptionOutlinedIcon, color: "#e8833a" },
  { key: "patient", label: "患者档案", Icon: PersonSearchOutlinedIcon, color: "#9b59b6" },
];

export default function ActionPanel({ open, onClose, onAction }) {
  if (!open) return null;

  return (
    <Box
      sx={{ position: "fixed", inset: 0, zIndex: 1300 }}
      onClick={onClose}
    >
      <Box sx={{ position: "absolute", inset: 0, bgcolor: "rgba(0,0,0,0.3)" }} />
      <Slide direction="up" in={open} mountOnEnter unmountOnExit>
        <Box
          onClick={(e) => e.stopPropagation()}
          sx={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            bgcolor: "#fff",
            borderRadius: "12px 12px 0 0",
            pb: 3,
          }}
        >
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "24px",
              p: 2,
              justifyItems: "center",
            }}
          >
            {actions.map(({ key, label, Icon, color }) => (
              <Box
                key={key}
                onClick={() => onAction(key)}
                sx={{ display: "flex", flexDirection: "column", alignItems: "center", cursor: "pointer" }}
              >
                <Box
                  sx={{
                    width: 56,
                    height: 56,
                    borderRadius: "4px",
                    bgcolor: color,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Icon sx={{ color: "#fff", fontSize: ICON.hero }} />
                </Box>
                <Typography sx={{ mt: 0.5, fontSize: TYPE.caption.fontSize, color: "#666" }}>{label}</Typography>
              </Box>
            ))}
          </Box>
        </Box>
      </Slide>
    </Box>
  );
}
