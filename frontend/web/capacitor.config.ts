import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.doctorai.app",
  appName: "医生助手",
  webDir: "dist",
  server: {
    // Use https scheme so cookies and auth headers behave correctly on Android
    androidScheme: "https",
  },
};

export default config;
