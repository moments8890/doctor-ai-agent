/**
 * DetailCard — compact key-value card for short-field detail views.
 *
 * Props:
 *  - title: main heading (e.g. "随访 · 王五")
 *  - fields: [{ label, value }] — shown as 2-column grid
 *  - note: optional longer text block (备注, 内容)
 *  - noteLabel: label for note (default "备注")
 *  - children: action buttons or extra content below
 */
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

export default function DetailCard({ title, fields, note, noteLabel = "备注", children }) {
  return (
    <Box sx={{ bgcolor: "#fff", px: 2, py: 1.5, mb: 1 }}>
      {/* Title */}
      {title && (
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: "#1A1A1A", mb: 1 }}>
          {title}
        </Typography>
      )}

      {/* Key-value grid */}
      {fields && fields.length > 0 && (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px", mb: note ? 1 : 0 }}>
          {fields.map((f, i) => (
            <Box key={i} sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flexShrink: 0 }}>
                {f.label}
              </Typography>
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, fontWeight: f.bold ? 600 : 400 }}>
                {f.value || "—"}
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      {/* Note / long text */}
      {note && (
        <Box sx={{ pt: 0.5, borderTop: "0.5px solid #f0f0f0" }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.3 }}>{noteLabel}</Typography>
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
            {note}
          </Typography>
        </Box>
      )}

      {/* Actions */}
      {children && <Box sx={{ mt: 1.5 }}>{children}</Box>}
    </Box>
  );
}
