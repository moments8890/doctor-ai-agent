/**
 * HelpTip — question mark icon button + snackbar tooltip.
 *
 * Usage:
 *   <HelpTip message="解释文字" />
 *
 * Pass as `headerRight` to PageSkeleton or `right` to SubpageHeader.
 */
import { useState } from "react";
import { IconButton, Snackbar } from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import { COLOR, ICON } from "../theme";

export default function HelpTip({ message }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <IconButton size="small" onClick={() => setOpen(true)} sx={{ color: COLOR.text4 }}>
        <HelpOutlineIcon sx={{ fontSize: ICON.md }} />
      </IconButton>
      <Snackbar
        open={open}
        autoHideDuration={4000}
        onClose={() => setOpen(false)}
        message={message}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
        sx={{ top: { xs: 56 } }}
      />
    </>
  );
}
