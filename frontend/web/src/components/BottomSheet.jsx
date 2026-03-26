/**
 * BottomSheet — swipe-up panel overlay.
 * Slides up from bottom, covers ~85% of screen. Swipe down or tap backdrop to close.
 */
import { useCallback, useRef } from "react";
import { Box, Typography } from "@mui/material";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { TYPE, ICON, COLOR } from "../theme";

export default function BottomSheet({ open, onClose, title, right, children }) {
  const startY = useRef(null);
  const sheetRef = useRef(null);

  const handleTouchStart = useCallback((e) => {
    startY.current = e.touches[0].clientY;
  }, []);

  const handleTouchEnd = useCallback((e) => {
    if (startY.current === null) return;
    const dy = e.changedTouches[0].clientY - startY.current;
    startY.current = null;
    if (dy > 80) onClose();
  }, [onClose]);

  if (!open) return null;

  return (
    <Box sx={{ position: "absolute", top: 0, left: 0, right: 0,
      bottom: "calc(64px + env(safe-area-inset-bottom))",
      zIndex: 1200, display: "flex", flexDirection: "column" }}>
      {/* Backdrop */}
      <Box onClick={onClose} sx={{ height: "15%", flexShrink: 0, bgcolor: "rgba(0,0,0,0.3)" }} />
      {/* Sheet */}
      <Box ref={sheetRef}
        onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}
        sx={{
          flex: 1, bgcolor: COLOR.white, borderRadius: "12px 12px 0 0",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}>
        {/* Header — only if title provided */}
        {title && (
          <Box sx={{ position: "relative", display: "flex", alignItems: "center", height: 48, px: 1,
            borderBottom: `1px solid ${COLOR.border}`, flexShrink: 0, bgcolor: COLOR.white }}>
            <Box onClick={onClose}
              sx={{ display: "flex", alignItems: "center", cursor: "pointer", px: 0.5, py: 1,
                color: COLOR.text2, "&:active": { opacity: 0.5 } }}>
              <KeyboardArrowDownIcon sx={{ fontSize: ICON.hero }} />
            </Box>
            <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: TYPE.title.fontSize }}>
              {title}
            </Typography>
            {right ? <Box sx={{ position: "absolute", right: 8 }}>{right}</Box> : <Box sx={{ minWidth: 36 }} />}
          </Box>
        )}
        {/* Content */}
        <Box sx={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}
