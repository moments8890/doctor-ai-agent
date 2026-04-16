// frontend/web/src/components/ReleaseNotesDialog.jsx
//
// "What's new" rich-card modal. Uses SheetDialog (bottom sheet on mobile).

import { Box, Typography } from "@mui/material";
import SheetDialog from "./SheetDialog";
import DialogFooter from "./DialogFooter";
import { TYPE, COLOR, RADIUS } from "../theme";

function FeatureCard({ icon: Icon, title, description }) {
  return (
    <Box
      sx={{
        display: "flex",
        gap: 1.5,
        p: 1.5,
        bgcolor: COLOR.surfaceAlt,
        borderRadius: RADIUS.md,
      }}
    >
      <Box
        sx={{
          width: 40,
          height: 40,
          borderRadius: RADIUS.sm,
          bgcolor: COLOR.primaryLight,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon sx={{ fontSize: 20, color: COLOR.primary }} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ ...TYPE.heading, mb: 0.25 }}>{title}</Typography>
        <Typography sx={{ ...TYPE.secondary, color: COLOR.text3 }}>
          {description}
        </Typography>
      </Box>
    </Box>
  );
}

export default function ReleaseNotesDialog({ open, release, onDismiss }) {
  if (!release) return null;

  return (
    <SheetDialog
      open={open}
      onClose={onDismiss}
      title={release.title}
      footer={
        <DialogFooter
          showCancel={false}
          confirmLabel="知道了"
          onConfirm={onDismiss}
        />
      }
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, py: 1 }}>
        {release.features.map((f, i) => (
          <FeatureCard key={i} {...f} />
        ))}
      </Box>
    </SheetDialog>
  );
}
