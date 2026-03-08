Page({
  data: {
    url: "",
    loading: true,
  },

  onLoad() {
    const app = getApp();
    const token = app.globalData.accessToken;
    const doctorId = app.globalData.doctorId;
    const doctorName = app.globalData.doctorName || "";

    if (!token) {
      wx.redirectTo({ url: "/pages/login/login" });
      return;
    }

    // Strip /api (or any path) from apiBase to get the web root.
    const webBase = app.globalData.apiBase.replace(/\/api.*$/, "");
    const qs = [
      "token="     + encodeURIComponent(token),
      "doctor_id=" + encodeURIComponent(doctorId),
      "name="      + encodeURIComponent(doctorName),
    ].join("&");

    this.setData({ url: webBase + "/doctor?" + qs });
  },

  onWebViewLoad() {
    this.setData({ loading: false });
  },

  // Receive postMessages from the web-view.
  onMessage(e) {
    const msgs = e.detail.data || [];
    const last = msgs[msgs.length - 1];
    if (!last) return;

    if (last.action === "logout") {
      this._clearAuth();
      wx.redirectTo({ url: "/pages/login/login" });
    }
  },

  _clearAuth() {
    const app = getApp();
    app.globalData.accessToken = "";
    app.globalData.doctorId    = "";
    app.globalData.doctorName  = "";
    wx.removeStorageSync("token");
    wx.removeStorageSync("doctorId");
    wx.removeStorageSync("doctorName");
  },
});
