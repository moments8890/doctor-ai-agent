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

export default function FilterBar({ items, active, counts = {}, onChange, dividers = false }) {
  const hasCounts = Object.values(counts).some((v) => v != null);
  return (
    <Box sx={{
      display: "flex",
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      ...(dividers ? { bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}` } : {}),
    }}>
      {items.map((tab, i) => {
        const isActive = active === tab.key;
        const count = counts[tab.key];
        const activeColor = tab.activeColor || COLOR.warning;
        return (
          <Box key={tab.key} sx={{ display: dividers ? "contents" : "flex", flex: dividers ? undefined : 1 }}>
            <Box onClick={() => onChange(tab.key)}
              sx={{
                flex: 1, textAlign: "center", py: dividers ? 1.5 : 1, cursor: "pointer",
                userSelect: "none",
                borderBottom: isActive ? `2px solid ${activeColor}` : "2px solid transparent",
                transition: dividers ? "border-color 0.15s ease" : undefined,
                "&:active": { opacity: dividers ? 0.5 : 0.7 },
              }}>
              {hasCounts && (
                <Typography sx={{
                  fontSize: TYPE.title.fontSize, fontWeight: dividers ? 600 : 700, lineHeight: 1.3,
                  color: isActive ? activeColor : COLOR.text4,
                  transition: dividers ? "color 0.15s ease" : undefined,
                }}>
                  {count ?? 0}
                </Typography>
              )}
              <Typography sx={{
                fontSize: dividers ? TYPE.micro.fontSize : TYPE.caption.fontSize,
                mt: dividers ? 0.5 : 0,
                color: isActive ? (dividers ? COLOR.text2 : COLOR.text1) : COLOR.text4,
                fontWeight: isActive ? (dividers ? 500 : 600) : 400,
              }}>
                {tab.label}
              </Typography>
            </Box>
            {dividers && i < items.length - 1 && (
              <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 1 }} />
            )}
          </Box>
        );
      })}
    </Box>
  );
}
