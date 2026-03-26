import { Box, Typography } from "@mui/material";
import { TYPE } from "../../../theme";

const CARD_STYLES = {
  urgent: { bg: "#FEF0EE", dot: "#E8533F" },
  ai_discovery: { bg: "#E8F0FE", dot: "#1B6EF3" },
  pattern: { bg: "#E8F5E9", dot: "#07C160" },
};

function CompactCard({ card, style, onAction }) {
  return (
    <Box
      onClick={() => onAction(card.type, card)}
      sx={{
        bgcolor: "#fff",
        borderRadius: "4px",
        p: 1.5,
        mb: 0.8,
        display: "flex",
        alignItems: "center",
        cursor: "pointer",
      }}
    >
      {/* Icon */}
      <Box
        sx={{
          width: 40,
          height: 40,
          borderRadius: "4px",
          bgcolor: style.bg,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          mr: 1.5,
        }}
      >
        <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: style.dot }} />
      </Box>

      {/* Text */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: "#111" }} noWrap>
          {card.title}
        </Typography>
        {card.context && (
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999", mt: 0.2 }} noWrap>
            {card.context}
          </Typography>
        )}
      </Box>

      {/* Chevron */}
      <Typography sx={{ fontSize: TYPE.title.fontSize, color: "#ccc", flexShrink: 0, ml: 1 }}>
        ›
      </Typography>
    </Box>
  );
}

function ExpandedReviewCard({ card, style, onAction }) {
  const items = card.items || [];
  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: "4px", p: 1.5, mb: 0.8 }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
        <Box
          sx={{
            width: 40,
            height: 40,
            borderRadius: "4px",
            bgcolor: style.bg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            mr: 1.5,
          }}
        >
          <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: style.dot }} />
        </Box>
        <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: "#111" }}>
          {card.title}
        </Typography>
      </Box>

      {/* Sub-items */}
      {items.map((item, i) => (
        <Box
          key={i}
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            pl: 6.5,
            py: 1,
            ...(i < items.length - 1 && { borderBottom: "0.5px solid #f0f0f0" }),
          }}
        >
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#333" }} noWrap>
              {item.patient_name}
              {item.chief_complaint && (
                <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: "#999", ml: 0.5 }}>
                  {item.chief_complaint}
                </Typography>
              )}
            </Typography>
          </Box>
          <Box
            onClick={(e) => {
              e.stopPropagation();
              onAction("review", item);
            }}
            sx={{
              bgcolor: "#07C160",
              color: "#fff",
              fontSize: TYPE.caption.fontSize,
              fontWeight: 500,
              px: 1.5,
              py: 0.4,
              borderRadius: "4px",
              cursor: "pointer",
              flexShrink: 0,
              ml: 1,
            }}
          >
            审核
          </Box>
        </Box>
      ))}
    </Box>
  );
}

export default function BriefingCard({ card, onAction }) {
  const style = CARD_STYLES[card.type] || CARD_STYLES.ai_discovery;

  return <CompactCard card={card} style={style} onAction={onAction} />;
}
