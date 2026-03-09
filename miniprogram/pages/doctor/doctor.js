const runtimeConfig = require("../../config.js");

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

    // Subscription requested on first user tap (see onLoadingTap) to satisfy
    // WeChat's requirement that requestSubscribeMessage is called from a TAP.
    this._subscriptionPending = true;
  },

  // Called when the user taps the loading overlay — the first natural tap
  // gesture on this page. We use it to fire requestSubscribeMessage, which
  // WeChat requires to originate from a user TAP event.
  onLoadingTap() {
    if (this._subscriptionPending) {
      this._subscriptionPending = false;
      this._requestSubscription();
    }
  },

  _requestSubscription() {
    const tmplId = runtimeConfig.subscribeTemplateId;
    if (!tmplId) return;  // Template not configured; skip.

    wx.requestSubscribeMessage({
      tmplIds: [tmplId],
      success() {
        // User's response (accept/reject) is handled by WeChat natively.
        // We don't need to do anything special here — the backend will
        // attempt to send messages and WeChat will deliver only if accepted.
      },
      fail(err) {
        // Subscription request declined or unsupported (e.g. in DevTools).
        console.warn("[doctor] requestSubscribeMessage failed:", err);
      },
    });
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
