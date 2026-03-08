const { loginWithWechatCode } = require("../../utils/api");

Page({
  data: {
    loading: false,
    doctorName: "",
  },

  onDoctorNameInput(e) {
    this.setData({ doctorName: e.detail.value || "" });
  },

  async onLogin() {
    if (this.data.loading) return;
    this.setData({ loading: true });

    try {
      const loginRes = await new Promise((resolve, reject) => {
        wx.login({
          success: resolve,
          fail: reject,
        });
      });

      if (!loginRes.code) {
        throw new Error("wx.login 未返回 code");
      }

      const auth = await loginWithWechatCode(loginRes.code, this.data.doctorName);
      const app = getApp();
      app.globalData.accessToken = auth.access_token;
      app.globalData.doctorId = auth.doctor_id;
      app.globalData.doctorName = auth.doctor_name || this.data.doctorName || "";

      wx.redirectTo({ url: "/pages/doctor/doctor" });
    } catch (err) {
      wx.showToast({ title: "登录失败", icon: "none" });
      console.error("login failed", err);
    } finally {
      this.setData({ loading: false });
    }
  },
});
