const { authMe } = require("../../utils/api");

Page({
  data: {
    url: "",
    loading: true,
  },

  async onLoad() {
    const app = getApp();
    const token = app.globalData.accessToken;

    // Fast path: existing token — verify it's still valid.
    if (token) {
      try {
        const me = await authMe();
        if (me && me.doctor_id) {
          wx.redirectTo({ url: "/pages/doctor/doctor" });
          return;
        }
      } catch {
        this._clearAuth(app);
      }
    }

    // Show the web /login page inside a WebView. Cache-buster: X5 ignores
    // Cache-Control on HTML; timestamp forces a fresh fetch each session.
    const webBase = app.globalData.apiBase;
    this.setData({ url: webBase + "/login?_t=" + Date.now(), loading: false });
  },

  // Called by the web /login page after a successful doctor login.
  // Payload: { action: "login", token, doctor_id, name }
  onMessage(e) {
    const msgs = e.detail.data || [];
    const last = msgs[msgs.length - 1];
    if (!last || last.action !== "login" || !last.token || !last.doctor_id) return;

    const app = getApp();
    app.globalData.accessToken = last.token;
    app.globalData.doctorId    = last.doctor_id;
    app.globalData.doctorName  = last.name || "";
    wx.setStorageSync("token",      last.token);
    wx.setStorageSync("doctorId",   last.doctor_id);
    wx.setStorageSync("doctorName", last.name || "");
    // Navigation is handled by wx.miniProgram.redirectTo called from the web page.
  },

  onShareAppMessage() {
    return {
      title: "鲸鱼随行 · AI 医疗助手",
      path: "/pages/login/login",
    };
  },

  _clearAuth(app) {
    app.globalData.accessToken = "";
    app.globalData.doctorId    = "";
    app.globalData.doctorName  = "";
    wx.removeStorageSync("token");
    wx.removeStorageSync("doctorId");
    wx.removeStorageSync("doctorName");
  },
});
