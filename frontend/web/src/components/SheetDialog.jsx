import { Box, Dialog, Typography } from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { TYPE, COLOR, RADIUS } from "../theme";

export default function SheetDialog({
  open,
  onClose,
  title,
  subtitle,
  right,
  children,
  footer,
  maxWidth = "xs",
  desktopMinWidth = 320,
  desktopMaxWidth = 420,
  mobileMaxHeight = "80vh",
  showHandle = true,
  paperSx,
  headerSx,
  contentSx,
  footerSx,
}) {
  // Use the real browser viewport here instead of app theme breakpoints.
  // The app theme forces `sm` to a huge value so mobile layouts render inside
  // the desktop phone frame, but sheet positioning should still center in that frame.
  const isMobile = useMediaQuery("(max-width:520px)");

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth={isMobile ? false : maxWidth}
      PaperProps={{
        sx: isMobile
          ? {
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              m: 0,
              borderRadius: `${RADIUS.lg} ${RADIUS.lg} 0 0`,
              width: "100%",
              maxHeight: mobileMaxHeight,
              ...paperSx,
            }
          : {
              borderRadius: 2,
              minWidth: desktopMinWidth,
              maxWidth: desktopMaxWidth,
              width: "100%",
              ...paperSx,
            },
      }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : undefined}
    >
      <Box sx={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        {isMobile && showHandle ? (
          <Box sx={{ display: "flex", justifyContent: "center", pt: 1, pb: 0.5 }}>
            <Box sx={{ width: 36, height: 4, borderRadius: 2, bgcolor: COLOR.border }} />
          </Box>
        ) : null}

        {(title || subtitle || right) ? (
          <Box sx={{ px: 2.5, pt: isMobile ? 1 : 2.5, pb: 1.5, position: "relative", ...headerSx }}>
            {title ? (
              <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize, color: COLOR.text1, textAlign: "center" }}>
                {title}
              </Typography>
            ) : null}
            {subtitle ? (
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, textAlign: "center", mt: 0.3 }}>
                {subtitle}
              </Typography>
            ) : null}
            {right ? <Box sx={{ position: "absolute", right: 20, top: isMobile ? 10 : 18 }}>{right}</Box> : null}
          </Box>
        ) : null}

        <Box sx={{ px: 2.5, pb: footer ? 1 : (isMobile ? 3.5 : 2.5), overflowY: "auto", minHeight: 0, ...contentSx }}>
          {children}
        </Box>

        {footer ? (
          <Box sx={{ px: 2.5, pb: isMobile ? 3.5 : 2.5, pt: 1, ...footerSx }}>
            {footer}
          </Box>
        ) : null}
      </Box>
    </Dialog>
  );
}
