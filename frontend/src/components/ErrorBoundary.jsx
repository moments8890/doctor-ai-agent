import { Component } from "react";
import { Box, Typography, Button } from "@mui/material";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      const label = this.props.label || "此模块";
      return (
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            gap: 2,
            p: 3,
            color: "#888",
          }}
        >
          <Typography variant="body2">{label}加载失败，请刷新页面重试。</Typography>
          <Button size="small" variant="outlined" onClick={() => this.setState({ hasError: false, error: null })}>
            重试
          </Button>
        </Box>
      );
    }
    return this.props.children;
  }
}
