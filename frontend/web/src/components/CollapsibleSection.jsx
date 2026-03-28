/**
 * CollapsibleSection — tap header to collapse/expand content.
 * WeChat-style: SectionLabel with chevron indicator.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { TYPE, COLOR } from "../theme";

export default function CollapsibleSection({ title, count, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <>
      <Box
        onClick={() => setOpen(!open)}
        sx={{
          display: "flex", alignItems: "center",
          px: 1.5, pt: 1, pb: 1,
          cursor: "pointer", userSelect: "none",
          "&:active": { opacity: 0.6 },
        }}
      >
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, fontWeight: 600, letterSpacing: 0.5, flex: 1 }}>
          {title}
          {count != null && <Box component="span" sx={{ color: COLOR.text4, fontWeight: 400 }}> {count}</Box>}
        </Typography>
        <ExpandMoreIcon sx={{
          fontSize: 16, color: COLOR.text4,
          transition: "transform 0.2s ease",
          transform: open ? "rotate(0deg)" : "rotate(-90deg)",
        }} />
      </Box>
      {open && children}
    </>
  );
}
