import { Box, Slide, Typography } from "@mui/material";
import CameraAltOutlinedIcon from "@mui/icons-material/CameraAltOutlined";
import PhotoLibraryOutlinedIcon from "@mui/icons-material/PhotoLibraryOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PersonSearchOutlinedIcon from "@mui/icons-material/PersonSearchOutlined";
import { TYPE, ICON, COLOR, RADIUS } from "../theme";

const actions = [
  { key: "camera", label: "拍照", Icon: CameraAltOutlinedIcon, color: COLOR.primary },
  { key: "gallery", label: "相册", Icon: PhotoLibraryOutlinedIcon, color: COLOR.recordBlue },
  { key: "file", label: "文档", Icon: DescriptionOutlinedIcon, color: COLOR.orange },
];

export default function ActionPanel({ open, onClose, onAction }) {
  if (!open) return null;

  return (
    <Box
      sx={{ position: "absolute", inset: 0, zIndex: 1300 }}
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
            bgcolor: COLOR.white,
            borderRadius: `${RADIUS.lg} ${RADIUS.lg} 0 0`,
            pb: 2.5,
          }}
        >
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
              gap: 1.5,
              p: 2,
              justifyItems: "center",
              "@media (max-width: 359.95px)": {
                gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
              },
            }}
          >
            {actions.map(({ key, label, Icon, color }) => (
              <Box
                key={key}
                onClick={() => onAction(key)}
                sx={{ display: "flex", flexDirection: "column", alignItems: "center", cursor: "pointer", width: "100%" }}
              >
                <Box
                  sx={{
                    width: 56,
                    height: 56,
                    borderRadius: RADIUS.sm,
                    bgcolor: color,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    "@media (max-width: 359.95px)": {
                      width: 52,
                      height: 52,
                    },
                  }}
                >
                  <Icon sx={{ color: COLOR.white, fontSize: ICON.hero }} />
                </Box>
                <Typography sx={{ mt: 0.75, fontSize: TYPE.caption.fontSize, color: COLOR.text3, textAlign: "center", lineHeight: 1.3, whiteSpace: "normal", wordBreak: "break-word", maxWidth: 72 }}>
                  {label}
                </Typography>
              </Box>
            ))}
          </Box>
        </Box>
      </Slide>
    </Box>
  );
}
