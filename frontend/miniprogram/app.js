const runtimeConfig = require("./config.js");

// Resolve {webBase, apiBase} at runtime.
//
// webBase  = WebView <web-view src="..."> URL (the SPA host)
// apiBase  = wx.request URL prefix (the API host)
//
// Production nginx serves SPA at app.* and API at api.* — they are different
// subdomains. Today's miniapp conflates them via a bare-domain fallback;
// this resolver makes the split explicit.
//
// 正式版 (envVersion === "release") returns the same prod URLs the miniapp
// currently uses for real users. No behavior change for production.
function resolveBases() {
  // Devtools preview on a developer laptop: respect explicit config.js.
  // LAN dev (e.g. 192.168.x.x:5173) uses Vite's /api proxy so SPA host and
  // API host are the same — single base is correct here.
  try {
    if (wx.getSystemInfoSync().platform === "devtools" && runtimeConfig.apiBase) {
      return { webBase: runtimeConfig.apiBase, apiBase: runtimeConfig.apiBase };
    }
  } catch (_) { /* fall through */ }

  try {
    const env = wx.getAccountInfoSync().miniProgram.envVersion;
    if (env === "release") {
      return {
        webBase: "https://app.doctoragentai.cn",
        apiBase: "https://api.doctoragentai.cn",
      };
    }
    // develop / trial — only WeChat-listed members can reach this slot.
    return {
      webBase: "https://app.stg.doctoragentai.cn",
      apiBase: "https://api.stg.doctoragentai.cn",
    };
  } catch (_) { /* very old WeChat — ultimate fallback */ }

  return {
    webBase: "https://app.doctoragentai.cn",
    apiBase: "https://api.doctoragentai.cn",
  };
}

const bases = resolveBases();

App({
  globalData: {
    webBase: bases.webBase,
    apiBase: bases.apiBase,
    accessToken: "",
    doctorId: "",
    doctorName: "",
  },

  onLaunch() {
    this.globalData.accessToken = wx.getStorageSync("token") || "";
    this.globalData.doctorId   = wx.getStorageSync("doctorId") || "";
    this.globalData.doctorName = wx.getStorageSync("doctorName") || "";

    const updateManager = wx.getUpdateManager();
    updateManager.onUpdateReady(() => {
      wx.showModal({
        title: '更新提示',
        content: '新版本已准备好，是否重启应用？',
        success: (res) => { if (res.confirm) updateManager.applyUpdate(); },
      });
    });
    updateManager.onUpdateFailed(() => {
      console.warn('miniapp update failed');
    });
  },
});
