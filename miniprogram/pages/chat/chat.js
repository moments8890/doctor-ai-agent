const { miniChat } = require("../../utils/api");

Page({
  data: {
    doctorId: "",
    text: "",
    sending: false,
    messages: [],
  },

  onShow() {
    const app = getApp();
    this.setData({ doctorId: app.globalData.doctorId || "" });
    if (!app.globalData.accessToken) {
      wx.redirectTo({ url: "/pages/login/login" });
    }
  },

  onInput(e) {
    this.setData({ text: e.detail.value || "" });
  },

  async onSend() {
    const text = (this.data.text || "").trim();
    if (!text || this.data.sending) return;

    const next = [...this.data.messages, { role: "user", content: text }];
    this.setData({ sending: true, text: "", messages: next });

    try {
      const resp = await miniChat(text, next);
      this.setData({
        messages: [...next, { role: "assistant", content: resp.reply || "" }],
      });
    } catch (err) {
      wx.showToast({ title: "发送失败", icon: "none" });
      console.error("chat failed", err);
    } finally {
      this.setData({ sending: false });
    }
  },
});
