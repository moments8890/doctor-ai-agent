/**
 * Toast — transient dark overlay message for async completions.
 *
 * Usage:
 *   const [toast, showToast] = useToast();
 *   showToast("已保存");
 *   // ...
 *   <Toast message={toast} />
 *
 * For interactive feedback (actions, dismiss), use MUI Snackbar instead.
 */
import { useState, useRef, useCallback } from "react";
import { Box } from "@mui/material";
import { TYPE, RADIUS } from "../theme";

export default function Toast({ message }) {
  if (!message) return null;
  return (
    <Box sx={{
      position: "fixed", top: "20%", left: "50%", transform: "translateX(-50%)",
      bgcolor: "rgba(0,0,0,0.7)", color: "#fff", px: 3, py: 1.5,
      borderRadius: RADIUS.md, fontSize: TYPE.body.fontSize, zIndex: 9999,
      pointerEvents: "none",
    }}>
      {message}
    </Box>
  );
}

/**
 * useToast — hook for transient toast messages.
 *
 * Usage:
 *   const [toast, showToast] = useToast(2000);
 *   showToast("已保存");
 */
export function useToast(duration = 2000) {
  const [message, setMessage] = useState(null);
  const timerRef = useRef(null);

  const show = useCallback((msg) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setMessage(msg);
    timerRef.current = setTimeout(() => setMessage(null), duration);
  }, [duration]);

  return [message, show];
}
