import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { TYPE, COLOR } from "../theme";

/**
 * Chat bubble for doctor direct-replies shown in the patient chat (主页 tab).
 * Visually similar to AI bubbles but with a green border and doctor name label.
 */
export default function DoctorBubble({ doctorName, content, timestamp }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
      <Box sx={{ maxWidth: "85%", display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
        {/* Doctor name label */}
        <Typography
          sx={{
            fontSize: 12,
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
            bgcolor: "#fff",
            border: `0.5px solid ${COLOR.success}`,
            borderRadius: "8px",
            ...TYPE.body,
            lineHeight: 1.6,
            color: COLOR.text1,
            px: "14px",
            py: "10px",
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
              fontSize: 12,
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
