import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from "@mui/material";
import { TYPE } from "../theme";

export default function ImportChoiceDialog({ open, text, onInsert, onImport, onClose }) {
  if (!text) return null;
  const preview = text.length > 200 ? text.slice(0, 200) + "..." : text;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600 }}>已提取文字内容</DialogTitle>
      <DialogContent>
        <Box sx={{ p: 1.5, borderRadius: "4px", bgcolor: "#f0f0f0", mb: 1 }}>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontSize: TYPE.secondary.fontSize, color: "#666", lineHeight: 1.8 }}>
            {preview}
          </Typography>
        </Box>
        <Typography variant="caption" sx={{ color: "#999" }}>
          共提取 {text.length} 字
        </Typography>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button variant="outlined" onClick={() => onInsert(text)} sx={{ borderRadius: "4px" }}>
          放入输入框
        </Button>
        <Button variant="contained" onClick={() => onImport(text)}
          sx={{ borderRadius: "4px", bgcolor: "#07C160", "&:hover": { bgcolor: "#06ad56" } }}>
          导入病历
        </Button>
      </DialogActions>
    </Dialog>
  );
}
