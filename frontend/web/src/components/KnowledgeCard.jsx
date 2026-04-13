/**
 * KnowledgeCard — 3-row card for knowledge base items.
 *
 * Row 1: IconBadge + title + chevron
 * Row 2: Summary/content preview (gray)
 * Row 3: Meta — reference count + source + date
 *
 * @example
 *   <KnowledgeCard
 *     title="术后头痛危险信号"
 *     summary="先排除再出血，再评估颅压"
 *     referenceCount={7}
 *     source="doctor"
 *     date="3月23日"
 *     onClick={...}
 *   />
 */
import { Box, Typography } from "@mui/material";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import IconBadge from "./IconBadge";
import { ICON_BADGES } from "../pages/doctor/constants";
import { TYPE, COLOR } from "../theme";

const SOURCE_LABEL = {
  doctor: "手动",
  agent_auto: "AI生成",
};

function getSourceLabel(source) {
  if (!source) return "";
  if (source.startsWith("upload:")) return source.slice("upload:".length);
  if (source.startsWith("url:")) return "网页导入";
  return SOURCE_LABEL[source] || "";
}

function getSourceBadge(source) {
  if (!source) return ICON_BADGES.kb_doctor;
  if (source.startsWith("upload:")) return ICON_BADGES.kb_upload;
  if (source.startsWith("url:")) return ICON_BADGES.kb_url;
  if (source === "agent_auto") return ICON_BADGES.kb_ai;
  return ICON_BADGES.kb_doctor;
}

export default function KnowledgeCard({ title, summary, referenceCount = 0, source, date, status, onClick, sx }) {
  const badge = getSourceBadge(source);
  const sourceLabel = getSourceLabel(source);

  const metaParts = [];
  if (referenceCount > 0) metaParts.push(`引用${referenceCount}次`);
  if (sourceLabel) metaParts.push(sourceLabel);
  if (date) metaParts.push(date);
  const metaText = metaParts.join(" · ");

  return (
    <Box
      onClick={onClick}
      sx={{
        display: "flex", alignItems: "center", gap: 1,
        px: 2, py: 1.5,
        bgcolor: COLOR.white,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        cursor: onClick ? "pointer" : "default",
        "&:active": onClick ? { bgcolor: COLOR.surface } : {},
        "&:last-child": { borderBottom: "none" },
        ...sx,
      }}
    >
      <IconBadge config={badge} />

      <Box sx={{ flex: 1, minWidth: 0 }}>
        {/* Row 1: Title + status */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Typography sx={{
            fontSize: TYPE.body.fontSize, fontWeight: 500, color: COLOR.text1,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1,
          }}>
            {title}
          </Typography>
          {status && (
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: status.color || COLOR.text4, flexShrink: 0 }}>
              {status.label}
            </Typography>
          )}
        </Box>

        {/* Row 2: Summary */}
        {summary && (
          <Typography sx={{
            fontSize: TYPE.caption.fontSize, color: COLOR.text3,
            mt: 0.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            lineHeight: 1.4,
          }}>
            {summary}
          </Typography>
        )}

        {/* Row 3: Meta */}
        {metaText && (
          <Typography sx={{
            fontSize: TYPE.micro.fontSize, color: COLOR.text4,
            mt: 0.5,
          }}>
            {metaText}
          </Typography>
        )}
      </Box>

      {onClick && (
        <ChevronRightOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4, flexShrink: 0 }} />
      )}
    </Box>
  );
}
