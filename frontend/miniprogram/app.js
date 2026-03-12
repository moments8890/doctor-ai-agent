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
  },
});
