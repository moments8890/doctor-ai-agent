const { loginWithWechatCode, loginWithInviteCode, authMe } = require("../../utils/api");

Page({
  data: {
    mode: "invite",    // "invite" | "wechat"
    inviteCode: "",
    loading: false,
    error: "",
  },

  async onLoad() {
    const app = getApp();
    const token = app.globalData.accessToken;

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

    this.setData({ loading: true });
    try {
      const loginRes = await new Promise((resolve, reject) =>
        wx.login({ success: resolve, fail: reject })
      );
      if (loginRes.code) {
        const auth = await loginWithWechatCode(loginRes.code, "");
        if (auth.doctor_id && !auth.doctor_id.startsWith("wxmini_")) {
          this._saveAuth(auth);
          return;
        }
      }
    } catch {
      // Silent login failed — show login form
    }
    this.setData({ loading: false });
  },

  onModeSwitch(e) {
    this.setData({ mode: e.currentTarget.dataset.mode, error: "" });
  },

  onInviteInput(e) {
    this.setData({ inviteCode: (e.detail.value || "").trim(), error: "" });
  },

  async onInviteLogin() {
    const code = this.data.inviteCode.trim();
    if (!code) { this.setData({ error: "请输入邀请码" }); return; }
    if (this.data.loading) return;
    this.setData({ loading: true, error: "" });
    try {
      // Get a fresh wx.login code for openid linking (previous code was consumed by code2session)
      let jsCode = "";
      try {
        const loginRes = await new Promise((resolve, reject) =>
          wx.login({ success: resolve, fail: reject })
        );
        jsCode = loginRes.code || "";
      } catch {
        // wx.login failed — proceed without linking, openid can be linked on next login
      }
      const auth = await loginWithInviteCode(code, jsCode);
      this._saveAuth(auth);
    } catch (err) {
      const msg = (err && err.message) || "";
      const detail = msg.includes("401") ? "邀请码无效或已停用" : "登录失败，请重试";
      this.setData({ error: detail });
    } finally {
      this.setData({ loading: false });
    }
  },

  async onWechatLogin() {
    if (this.data.loading) return;
    this.setData({ loading: true, error: "" });
    try {
      const loginRes = await new Promise((resolve, reject) =>
        wx.login({ success: resolve, fail: reject })
      );
      if (!loginRes.code) throw new Error("wx.login 未返回 code");
      const auth = await loginWithWechatCode(loginRes.code, "");

      if (auth.doctor_id && auth.doctor_id.startsWith("wxmini_")) {
        this.setData({
          mode: "invite",
          error: "",
          loading: false,
        });
        wx.showToast({ title: "请输入邀请码完成注册", icon: "none", duration: 2500 });
        return;
      }

      this._saveAuth(auth);
    } catch (err) {
      const msg = (err && err.message) || "";
      const detail = msg.includes("not configured") ? "后端未配置微信登录" : "微信登录失败，请重试";
      this.setData({ error: detail });
    } finally {
      this.setData({ loading: false });
    }
  },

  _saveAuth(auth) {
    const app = getApp();
    const doctorName = auth.doctor_name || "";
    app.globalData.accessToken = auth.access_token;
    app.globalData.doctorId    = auth.doctor_id;
    app.globalData.doctorName  = doctorName;
    wx.setStorageSync("token",      auth.access_token);
    wx.setStorageSync("doctorId",   auth.doctor_id);
    wx.setStorageSync("doctorName", doctorName);
    wx.redirectTo({ url: "/pages/doctor/doctor" });
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
