/**
 * ActionRow — unified task/action item row with pending/done states.
 *
 * Replaces: TaskRow, ScheduledRow, SentRow (TaskPage), CompletedRow (ReviewQueuePage),
 *           and TaskChecklist rows (patient TasksTab).
 *
 * Props:
 *   title     — main text
 *   subtitle  — secondary line
 *   right     — right-side text (date, status)
 *   done      — checked state (green check vs empty circle)
 *   edited    — uses warning color for check (modified items)
 *   urgent    — uses warning color for right text
 *   overdue   — uses danger color for right text
 *   icon      — custom left element (overrides checkbox)
 *   badge     — ReactNode rendered between content and right (e.g., StatusBadge)
 *   action    — ReactNode rendered after right (e.g., upload button)
 *   onClick   — row tap handler (adds chevron)
 *   onToggle  — checkbox tap handler (animated complete/uncomplete)
 *
 * @example
 *   <ActionRow title="术后复查CT" subtitle="..." right="2026-03-27" onToggle={...} onClick={...} />
 *   <ActionRow title="三叉神经痛" subtitle="已确认" done right="昨天" onClick={...} />
 *   <ActionRow title="复查血常规" right="04-05" overdue badge={<StatusBadge ... />} action={<AppButton>上传</AppButton>} />
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import { TYPE, COLOR } from "../theme";

export default function ActionRow({ title, subtitle, right, done = false, edited = false, urgent = false, overdue = false, onClick, onToggle, icon, badge, action, sx }) {
  const [toggling, setToggling] = useState(false);

  const handleToggle = (e) => {
    e.stopPropagation();
    if (toggling) return;
    setToggling(true);
    setTimeout(() => {
      onToggle?.();
      setToggling(false);
    }, 500);
  };

  const isChecked = done || toggling;
  const checkColor = isChecked ? (edited ? COLOR.warning : COLOR.primary) : COLOR.border;
  const dimmed = toggling;

  return (
    <Box
      onClick={dimmed ? undefined : onClick}
      sx={{
        display: "flex", alignItems: "center", gap: 1,
        px: 2, py: 1.5,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        cursor: onClick && !dimmed ? "pointer" : "default",
        "&:active": onClick && !dimmed ? { bgcolor: COLOR.surface } : {},
        "&:last-child": { borderBottom: "none" },
        opacity: dimmed ? 0.4 : 1,
        transition: "opacity 0.4s ease",
        ...sx,
      }}
    >
      {/* Left: checkbox or custom icon */}
      {icon || (
        onToggle ? (
          <Box onClick={handleToggle} sx={{ cursor: "pointer", flexShrink: 0, "&:active": { transform: "scale(0.9)" } }}>
            {isChecked
              ? <CheckCircleOutlinedIcon sx={{ fontSize: 20, color: checkColor }} />
              : <RadioButtonUncheckedIcon sx={{ fontSize: 20, color: COLOR.border }} />
            }
          </Box>
        ) : (
          isChecked
            ? <CheckCircleOutlinedIcon sx={{ fontSize: 20, color: checkColor, flexShrink: 0 }} />
            : <RadioButtonUncheckedIcon sx={{ fontSize: 20, color: COLOR.border, flexShrink: 0 }} />
        )
      )}

      {/* Content */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{
          fontSize: TYPE.body.fontSize,
          color: done ? COLOR.text3 : COLOR.text1,
          textDecoration: dimmed ? "line-through" : "none",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          transition: "all 0.3s ease",
        }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography sx={{
            fontSize: TYPE.caption.fontSize, color: done ? COLOR.text4 : COLOR.text3,
            mt: 0.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {subtitle}
          </Typography>
        )}
      </Box>

      {/* Badge (e.g., StatusBadge for urgency) */}
      {badge}

      {/* Right: date/label */}
      {right && (
        <Typography sx={{
          fontSize: TYPE.caption.fontSize,
          color: overdue ? COLOR.danger : urgent ? COLOR.warning : done ? COLOR.primary : COLOR.text4,
          fontWeight: overdue || urgent ? 500 : 400,
          flexShrink: 0, whiteSpace: "nowrap",
        }}>
          {right}
        </Typography>
      )}

      {/* Action (e.g., upload button) */}
      {action}

      {/* Chevron for clickable rows */}
      {onClick && !dimmed && (
        <ChevronRightOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4, flexShrink: 0, ml: -0.5 }} />
      )}
    </Box>
  );
}
