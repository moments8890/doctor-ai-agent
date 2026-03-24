import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.doctorai.app",
  appName: "鲸鱼随行",
  webDir: "dist",
  server: {
    // Use https scheme so cookies and auth headers behave correctly on Android
    androidScheme: "https",
  },
};

export default config;
