import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.doctorai.app",
  appName: "鲸鱼随行",
  webDir: "dist",
  server: {
    // Android uses https://localhost so cookies/auth headers behave like on
    // the real web. iOS keeps the default capacitor://localhost — the iOS
    // hostname-rewrite path requires WKAppBoundDomains in Info.plist which
    // we don't ship; the backend allowlist explicitly includes
    // capacitor://localhost (see src/app_middleware.py setup_cors).
    androidScheme: "https",
  },
};

export default config;
