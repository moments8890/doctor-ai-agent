import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import NameAvatar from "./NameAvatar";
import { TYPE, COLOR } from "../theme";

/**
 * Chat bubble for doctor direct-replies shown in the patient chat (主页 tab).
 * Shows doctor's first-character avatar, name label, and green-bordered message.
 */
export default function DoctorBubble({ doctorName, content, timestamp }) {
  return (
    <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1 }}>
      <NameAvatar name={doctorName || "医"} size={32} />
      <Box sx={{ maxWidth: "75%", display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
        {/* Doctor name label */}
        <Typography
          sx={{
            fontSize: TYPE.caption.fontSize,
            fontWeight: 500,
            color: COLOR.success,
            mb: "2px",
          }}
        >
          {doctorName}
        </Typography>

        {/* Message bubble */}
        <Box
          sx={{
            bgcolor: COLOR.white,
            border: `0.5px solid ${COLOR.success}`,
            borderRadius: "4px 4px 4px 0",
            ...TYPE.body,
            lineHeight: 1.7,
            color: COLOR.text1,
            px: "12px",
            py: "8px",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {content}
        </Box>

        {/* Timestamp */}
        {timestamp && (
          <Typography
            sx={{
              fontSize: TYPE.caption.fontSize,
              color: COLOR.text4,
              mt: "2px",
            }}
          >
            {timestamp}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
