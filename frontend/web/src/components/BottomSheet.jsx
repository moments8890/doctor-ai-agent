/**
 * BottomSheet — swipe-up panel overlay.
 * Slides up from bottom, covers ~85% of screen. Swipe down or tap backdrop to close.
 */
import { useCallback, useRef } from "react";
import { Box, Typography } from "@mui/material";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";

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
    <Box sx={{ position: "fixed", top: 0, left: 0, right: 0,
      bottom: "calc(64px + env(safe-area-inset-bottom))",
      zIndex: 1200, display: "flex", flexDirection: "column" }}>
      {/* Backdrop */}
      <Box onClick={onClose} sx={{ height: "15%", flexShrink: 0, bgcolor: "rgba(0,0,0,0.3)" }} />
      {/* Sheet */}
      <Box ref={sheetRef}
        onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}
        sx={{
          flex: 1, bgcolor: "#fff", borderRadius: "12px 12px 0 0",
          display: "flex", flexDirection: "column",
          boxShadow: "0 -4px 20px rgba(0,0,0,0.12)",
          overflow: "hidden",
        }}>
        {/* Header — only if title provided */}
        {title && (
          <Box sx={{ position: "relative", display: "flex", alignItems: "center", height: 48, px: 1,
            borderBottom: "1px solid #e5e5e5", flexShrink: 0, bgcolor: "#fff" }}>
            <Box onClick={onClose}
              sx={{ display: "flex", alignItems: "center", cursor: "pointer", px: 0.5, py: 1,
                color: "#333", "&:active": { opacity: 0.5 } }}>
              <KeyboardArrowDownIcon sx={{ fontSize: 28 }} />
            </Box>
            <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16 }}>
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
