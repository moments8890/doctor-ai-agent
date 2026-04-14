import { Box, Dialog, SwipeableDrawer, Typography } from "@mui/material";
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
  mobileMaxHeight = "80vh",
  showHandle = true,
  paperSx,
  headerSx,
  contentSx,
  footerSx,
}) {
  // Real viewport check — SwipeableDrawer on actual mobile, Dialog on desktop frame.
  const isMobile = useMediaQuery("(max-width:520px)");

  const sheetContent = (
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
  );

  if (isMobile) {
    return (
      <SwipeableDrawer
        anchor="bottom"
        open={open}
        onClose={onClose}
        onOpen={() => {}}
        disableSwipeToOpen
        PaperProps={{
          sx: {
            borderRadius: `${RADIUS.lg} ${RADIUS.lg} 0 0`,
            maxHeight: mobileMaxHeight,
            ...paperSx,
          },
        }}
      >
        {sheetContent}
      </SwipeableDrawer>
    );
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth={maxWidth}
      disablePortal
      PaperProps={{
        sx: {
          borderRadius: RADIUS.lg,
          width: "100%",
          ...paperSx,
        },
      }}
      sx={{
        position: "absolute",
        "& .MuiBackdrop-root": { position: "absolute" },
      }}
    >
      {sheetContent}
    </Dialog>
  );
}
