/**
 * CitationPopover — inline preview of a cited knowledge rule.
 * Shows title, summary, reference count, and a "view full" link.
 * Anchored to the citation text element on click.
 */
import { Box, Popover, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../theme";

export default function CitationPopover({ anchorEl, open, onClose, rule, onViewFull }) {
  if (!rule) return null;
  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{
        paper: {
          sx: {
            mt: 0.5, p: 1.5, maxWidth: 280, borderRadius: RADIUS.md,
            border: `0.5px solid ${COLOR.border}`,
            boxShadow: "0 4px 16px rgba(0,0,0,0.1)",
          },
        },
      }}
    >
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text1, mb: 0.5 }}>
        {rule.title || "知识规则"}
      </Typography>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.5, mb: 1, display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
        {rule.summary || rule.content || ""}
      </Typography>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
          引用 {rule.reference_count || 0} 次
        </Typography>
        <Typography
          onClick={() => { onClose(); onViewFull?.(rule); }}
          sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, cursor: "pointer", fontWeight: 500, "&:active": { opacity: 0.6 } }}
        >
          查看全文 ›
        </Typography>
      </Box>
    </Popover>
  );
}
