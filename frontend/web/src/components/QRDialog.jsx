import { Box, CircularProgress, Typography } from "@mui/material";
import { QRCodeSVG } from "qrcode.react";
import SheetDialog from "./SheetDialog";
import DialogFooter from "./DialogFooter";
import { TYPE, COLOR, RADIUS } from "../theme";

export default function QRDialog({ open, onClose, title, name, url, loading, error, onRegenerate }) {
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title={title || "二维码"}
      desktopMaxWidth={360}
      footer={
        <DialogFooter showCancel={false} onConfirm={onRegenerate} confirmLabel="重新生成" confirmVariant="secondary" confirmDisabled={loading} />
      }
    >
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 2 }}>
        {loading ? (
          <Box sx={{ py: 4 }}><CircularProgress size={24} /></Box>
        ) : error ? (
          <Typography sx={{ py: 4, fontSize: TYPE.body.fontSize, color: COLOR.danger, textAlign: "center" }}>
            {error}
          </Typography>
        ) : url ? (
          <Box sx={{ p: 2, bgcolor: COLOR.white, borderRadius: RADIUS.md, border: `1px solid ${COLOR.borderLight}` }}>
            <QRCodeSVG value={url} size={200} level="M" />
          </Box>
        ) : null}
        {name && !error && (
          <Typography sx={{ mt: 1.5, fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.text1 }}>
            {name}
          </Typography>
        )}
        {!error && (
          <Typography sx={{ mt: 0.5, fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
            有效期30天
          </Typography>
        )}
      </Box>
    </SheetDialog>
  );
}
