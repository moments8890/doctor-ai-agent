Page({
  data: {
    url: "",
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

    // Build web-view URL: strip any /api path from apiBase to get the web root
    const webBase = app.globalData.apiBase.replace(/\/api.*$/, "");
    const qs = [
      "token=" + encodeURIComponent(token),
      "doctor_id=" + encodeURIComponent(doctorId),
      "name=" + encodeURIComponent(doctorName),
    ].join("&");

    this.setData({ url: webBase + "/doctor?" + qs });
  },

  // Receive postMessages from the web-view (e.g. logout signal)
  onMessage(e) {
    const msgs = e.detail.data || [];
    const last = msgs[msgs.length - 1];
    if (last && last.action === "logout") {
      const app = getApp();
      app.globalData.accessToken = "";
      app.globalData.doctorId = "";
      app.globalData.doctorName = "";
      wx.redirectTo({ url: "/pages/login/login" });
    }
  },
});
