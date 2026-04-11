/**
 * PersonaToast -- shows a non-blocking notification when the AI discovers
 * a new persona preference from doctor edits.
 */
import { useEffect, useState } from "react";
import { Box, Button, Snackbar, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../theme";
import { usePersonaPending } from "../lib/doctorQueries";
import { useAppNavigate } from "../hooks/useAppNavigate";
import { dp } from "../utils/doctorBasePath";
import { useDoctorStore } from "../store/doctorStore";

export default function PersonaToast() {
  const { doctorId } = useDoctorStore();
  const navigate = useAppNavigate();
  const { data } = usePersonaPending();
  const [open, setOpen] = useState(false);
  const [toastItem, setToastItem] = useState(null);

  const storageKey = `persona_toast_seen_count_${doctorId}`;

  useEffect(() => {
    if (!doctorId || !data?.items) return;
    const items = data.items;
    const seenCount = parseInt(localStorage.getItem(storageKey) || "0", 10);
    if (items.length > seenCount) {
      // New items discovered — show the most recent one
      const newItem = items[items.length - 1];
      setToastItem(newItem);
      setOpen(true);
    }
  }, [data, storageKey, doctorId]);

  function handleDismiss() {
    if (data?.items) {
      localStorage.setItem(storageKey, String(data.items.length));
    }
    setOpen(false);
  }

  function handleView() {
    handleDismiss();
    navigate(dp("settings/persona/pending"));
  }

  if (!toastItem) return null;

  return (
    <Snackbar
      open={open}
      autoHideDuration={6000}
      onClose={handleDismiss}
      anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      sx={{ bottom: { xs: 72, sm: 24 } }}
    >
      <Box sx={{
        bgcolor: COLOR.surface,
        borderRadius: RADIUS.md,
        border: `0.5px solid ${COLOR.border}`,
        boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
        px: 2, py: 1.5,
        maxWidth: 360,
        width: "100%",
      }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, mb: 1.25, lineHeight: 1.5 }}>
          AI注意到：{toastItem.summary}
        </Typography>
        <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
          <Button
            size="small"
            onClick={handleDismiss}
            sx={{ color: COLOR.text4, fontSize: TYPE.secondary.fontSize }}
          >
            忽略
          </Button>
          <Button
            size="small"
            variant="contained"
            onClick={handleView}
            sx={{
              bgcolor: COLOR.primary,
              color: COLOR.white,
              fontSize: TYPE.secondary.fontSize,
              "&:hover": { bgcolor: COLOR.primaryHover },
              boxShadow: "none",
            }}
          >
            查看
          </Button>
        </Box>
      </Box>
    </Snackbar>
  );
}
