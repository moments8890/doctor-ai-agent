/**
 * FilterBar — horizontal filter/tab selector with two visual variants.
 *
 * Props:
 *  - items: [{ key: string, label: string }]
 *  - active: string (current active key)
 *  - counts: { [key]: number } (optional, appended to label)
 *  - onChange: (key) => void
 *  - variant: "chips" | "tabs" (default: "chips")
 *    - chips: pill buttons, green fill active (for filtering data)
 *    - tabs: underline tabs, green border active (for switching views)
 */
import { Box } from "@mui/material";
import { TYPE } from "../theme";

export default function FilterBar({ items, active, counts = {}, onChange, variant = "chips" }) {
  if (variant === "tabs") {
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
              {tab.label}{count > 0 ? ` ${count}` : ""}
            </Box>
          );
        })}
      </Box>
    );
  }

  // Default: chips variant
  return (
    <Box sx={{ display: "flex", gap: 0.6, px: 1.5, py: 1, overflow: "auto" }}>
      {items.map((chip) => {
        const isActive = active === chip.key;
        const count = counts[chip.key];
        return (
          <Box key={chip.key} onClick={() => onChange(chip.key)}
            sx={{
              fontSize: TYPE.caption.fontSize, px: 1.2, py: 0.5,
              borderRadius: "4px", cursor: "pointer", flexShrink: 0,
              bgcolor: isActive ? "#07C160" : "#fff",
              color: isActive ? "#fff" : "#666",
              fontWeight: isActive ? 600 : 400,
              "&:active": { opacity: 0.7 },
            }}>
            {chip.label}{count != null ? ` (${count})` : ""}
          </Box>
        );
      })}
    </Box>
  );
}
