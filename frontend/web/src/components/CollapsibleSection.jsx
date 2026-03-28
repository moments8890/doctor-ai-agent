/**
 * CollapsibleSection — tap header to collapse/expand content.
 * iOS grouped table style: gray sticky header with count + chevron.
 *
 * Supports ref with .open() and .scrollIntoView() for programmatic control
 * (e.g., tapping summary bar stats to jump to a section).
 */
import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

const CollapsibleSection = forwardRef(function CollapsibleSection({ title, count, defaultOpen = true, children }, ref) {
  const [open, setOpen] = useState(defaultOpen);
  const headerRef = useRef(null);

  useImperativeHandle(ref, () => ({
    open() { setOpen(true); },
    scrollIntoView() {
      setOpen(true);
      setTimeout(() => {
        headerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    },
  }));

  return (
    <>
      <Box
        ref={headerRef}
        onClick={() => setOpen(!open)}
        sx={{
          display: "flex", alignItems: "center",
          px: 1.5, py: 1,
          bgcolor: "#f0f0f0",
          borderTop: `0.5px solid ${COLOR.border}`,
          borderBottom: `0.5px solid ${COLOR.border}`,
          cursor: "pointer", userSelect: "none",
          "&:active": { opacity: 0.6 },
        }}
      >
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, fontWeight: 600, letterSpacing: 0.5, flex: 1 }}>
          {title}
        </Typography>
        {count != null && (
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: open ? COLOR.primary : COLOR.text4, fontWeight: 500, mr: 0.5 }}>
            {count}条
          </Typography>
        )}
        <Typography sx={{ fontSize: 12, color: COLOR.text4, lineHeight: 1 }}>
          {open ? "▾" : "▸"}
        </Typography>
      </Box>
      {open && children}
    </>
  );
});

export default CollapsibleSection;
