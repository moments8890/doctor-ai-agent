const runtimeConfig = require("./config.js");

App({
  globalData: {
    apiBase: runtimeConfig.apiBase || "https://doctoragentai.cn",
    accessToken: "",
    doctorId: "",
    doctorName: "",
  },

  onLaunch() {
    // Restore persisted auth so the first page can skip login if token is still valid.
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
