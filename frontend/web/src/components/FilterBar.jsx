/**
 * FilterBar — horizontal filter/tab selector.
 *
 * Count on top (large, bold), label below, amber active bar.
 * Follows the WeChat-style tab pattern used in review queue.
 *
 * Props:
 *  - items: [{ key: string, label: string }]
 *  - active: string (current active key)
 *  - counts: { [key]: number } (optional, shown above label when present)
 *  - onChange: (key) => void
 */
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

export default function FilterBar({ items, active, counts = {}, onChange }) {
  const hasCounts = Object.values(counts).some((v) => v != null);
  return (
    <Box sx={{ display: "flex", borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
      {items.map((tab) => {
        const isActive = active === tab.key;
        const count = counts[tab.key];
        return (
          <Box key={tab.key} onClick={() => onChange(tab.key)}
            sx={{
              flex: 1, textAlign: "center", py: 1, cursor: "pointer",
              borderBottom: isActive ? `3px solid ${COLOR.warning}` : "3px solid transparent",
              "&:active": { opacity: 0.7 },
            }}>
            {hasCounts && (
              <Typography sx={{
                fontSize: TYPE.title.fontSize, fontWeight: 700, lineHeight: 1.3,
                color: isActive ? COLOR.warning : COLOR.text4,
              }}>
                {count ?? 0}
              </Typography>
            )}
            <Typography sx={{
              fontSize: TYPE.caption.fontSize,
              color: isActive ? COLOR.text1 : COLOR.text4,
              fontWeight: isActive ? 600 : 400,
            }}>
              {tab.label}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}
