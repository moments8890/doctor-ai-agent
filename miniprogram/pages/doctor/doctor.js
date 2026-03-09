const runtimeConfig = require("../../config.js");

Page({
  data: {
    url: "",
    loading: true,
    // True while the notification-permission prompt is shown.
    // Skipped automatically when no subscribeTemplateId is configured.
    showPermissionPrompt: false,
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

    // Show the permission prompt if a template is configured and the user
    // hasn't been asked yet this session. The prompt's CTA button provides
    // the TAP gesture that wx.requestSubscribeMessage requires.
    if (runtimeConfig.subscribeTemplateId) {
      this.setData({ showPermissionPrompt: true, loading: false });
    }
  },

  // Called when the doctor taps "开始使用" on the permission prompt.
  // This is the TAP gesture required by wx.requestSubscribeMessage.
  onEnterTap() {
    const tmplId = runtimeConfig.subscribeTemplateId;
    if (tmplId) {
      wx.requestSubscribeMessage({
        tmplIds: [tmplId],
        complete: () => {
          // Proceed regardless of accept/reject — the WebView should load.
          this.setData({ showPermissionPrompt: false, loading: true });
        },
      });
    } else {
      this.setData({ showPermissionPrompt: false, loading: true });
    }
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
