/**
 * LoadingCenter — centered SpinLoading indicator.
 *
 * Usage:
 *   <LoadingCenter />
 *   <LoadingCenter size="24px" />
 *   <LoadingCenter fullPage />
 */
import { SpinLoading } from "antd-mobile";
import { flex } from "../layouts";

export default function LoadingCenter({ size = "32px", fullPage = false }) {
  return (
    <div
      style={{
        ...flex.center,
        ...(fullPage ? { height: "100%" } : { paddingTop: 48 }),
      }}
    >
      <SpinLoading color="primary" style={{ "--size": size }} />
    </div>
  );
}
