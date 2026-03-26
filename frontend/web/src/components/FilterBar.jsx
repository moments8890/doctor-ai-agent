/**
 * FilterBar — horizontal filter/tab selector.
 *
 * Active: green text + green underline.
 * Inactive: gray text + transparent underline.
 *
 * Props:
 *  - items: [{ key: string, label: string }]
 *  - active: string (current active key)
 *  - counts: { [key]: number } (optional, appended to label)
 *  - onChange: (key) => void
 */
import { Box } from "@mui/material";
import { TYPE } from "../theme";

export default function FilterBar({ items, active, counts = {}, onChange }) {
  return (
    <Box sx={{ display: "flex", gap: 0, px: 2, borderBottom: "0.5px solid #f0f0f0" }}>
      {items.map((tab) => {
        const isActive = active === tab.key;
        const count = counts[tab.key];
        return (
          <Box key={tab.key} onClick={() => onChange(tab.key)}
            sx={{
              px: 1.5, py: 1, cursor: "pointer",
              fontSize: TYPE.secondary.fontSize,
              color: isActive ? "#07C160" : "#999",
              fontWeight: isActive ? 600 : 400,
              borderBottom: isActive ? "2px solid #07C160" : "2px solid transparent",
              flexShrink: 0,
              "&:active": { opacity: 0.7 },
            }}>
            {tab.label}{count > 0 ? ` ${count}` : count === 0 ? ` (${count})` : ""}
          </Box>
        );
      })}
    </Box>
  );
}
