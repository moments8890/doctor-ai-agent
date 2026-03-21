import { useState, useEffect, useRef, useCallback } from "react";
import {
  Box, CircularProgress, Dialog, DialogTitle, IconButton, List, ListItemButton,
  ListItemText, TextField, Typography, useMediaQuery, useTheme,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { searchPatients } from "../../api";
import { TYPE, ICON } from "../../theme";

export default function PatientPickerDialog({ open, onClose, doctorId, onSelect }) {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);

  const doSearch = useCallback((q) => {
    if (!q.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    searchPatients(doctorId, q.trim())
      .then((data) => setResults(data.items || []))
      .catch(() => setResults([]))
      .finally(() => setLoading(false));
  }, [doctorId]);

  useEffect(() => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => doSearch(query), 300);
    return () => clearTimeout(timerRef.current);
  }, [query, doSearch]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
    }
  }, [open]);

  const handleSelect = (patient) => {
    onSelect({ id: patient.id, name: patient.name });
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen={fullScreen}
      fullWidth
      maxWidth="xs"
      PaperProps={{ sx: { borderRadius: fullScreen ? 0 : "4px", display: "flex", flexDirection: "column", maxHeight: "80vh" } }}
    >
      <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pb: 1 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize }}>选择患者</Typography>
        <IconButton size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </DialogTitle>

      <Box sx={{ px: 2, pb: 1.5 }}>
        <TextField
          autoFocus
          fullWidth
          size="small"
          placeholder="输入姓名搜索患者"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          sx={{
            "& .MuiOutlinedInput-root": {
              borderRadius: "4px",
              bgcolor: "#f7f7f7",
              "& fieldset": { borderColor: "#e0e0e0" },
              "&.Mui-focused fieldset": { borderColor: "#07C160" },
            },
          }}
        />
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", px: 1 }}>
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress size={28} sx={{ color: "#07C160" }} />
          </Box>
        ) : results.length > 0 ? (
          <List disablePadding>
            {results.map((p, i) => (
              <ListItemButton
                key={p.id}
                onClick={() => handleSelect(p)}
                sx={{
                  borderRadius: "4px",
                  borderBottom: i < results.length - 1 ? "1px solid #f0f0f0" : "none",
                  "&:hover": { bgcolor: "#f5f5f5" },
                }}
              >
                <ListItemText
                  primary={p.name}
                  secondary={[p.gender, p.age != null && `${p.age}岁`].filter(Boolean).join(" / ") || undefined}
                  primaryTypographyProps={{ fontSize: TYPE.body.fontSize, fontWeight: 500 }}
                  secondaryTypographyProps={{ fontSize: TYPE.caption.fontSize, color: "#999" }}
                />
              </ListItemButton>
            ))}
          </List>
        ) : (
          <Typography sx={{ textAlign: "center", py: 6, color: "#999", fontSize: TYPE.body.fontSize }}>
            输入姓名搜索患者
          </Typography>
        )}
      </Box>
    </Dialog>
  );
}
