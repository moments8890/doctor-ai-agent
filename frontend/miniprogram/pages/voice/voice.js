const runtimeConfig = require("../../config.js");

const plugin = requirePlugin("WechatSI");

Page({
  data: {
    recording: false,
    processing: false,
    cancelled: false,
    error: "",
    timerText: "00:00",
  },

  _startY: 0,
  _seconds: 0,
  _timer: null,
  _manager: null,

  onLoad() {
    const manager = plugin.getRecordRecognitionManager();
    this._manager = manager;

    manager.onStart = () => {};
    manager.onRecognize = () => {};

    manager.onStop = (res) => {
      this._stopTimer();

      if (this.data.cancelled) {
        this.setData({ recording: false, cancelled: false });
        wx.navigateBack();
        return;
      }

      const text = (res && res.result) || "";
      if (!text) {
        this.setData({ recording: false, processing: false, error: "未识别到语音内容" });
        return;
      }

      this.setData({ recording: false, processing: true });
      this._postResult(text);
    };

    manager.onError = (err) => {
      console.error("[Voice] recorder", err);
      this._stopTimer();
      this.setData({
        recording: false,
        processing: false,
        error: "录音失败: " + ((err && err.msg) || "未知错误"),
      });
    };
  },

  onTouchStart(e) {
    if (this.data.recording || this.data.processing) return;
    this._startY = e.touches[0].clientY;
    this._seconds = 0;
    this.setData({ recording: true, cancelled: false, error: "", timerText: "00:00" });

    this._manager.start({ duration: 58000, lang: "zh_CN" });

    this._startTimer();
  },

  onTouchEnd() {
    if (!this.data.recording) return;
    this._stopTimer();

    if (this._seconds < 1) {
      this._manager.stop();
      this.setData({ recording: false, error: "说话时间太短" });
      setTimeout(() => {
        if (this.data.error === "说话时间太短") this.setData({ error: "" });
      }, 1500);
      return;
    }

    this._manager.stop();
  },

  onTouchMove(e) {
    if (!this.data.recording) return;
    const dy = this._startY - e.touches[0].clientY;
    this.setData({ cancelled: dy > 100 });
  },

  onCancel() {
    wx.navigateBack();
  },

  _startTimer() {
    this._timer = setInterval(() => {
      this._seconds++;
      const m = String(Math.floor(this._seconds / 60)).padStart(2, "0");
      const s = String(this._seconds % 60).padStart(2, "0");
      this.setData({ timerText: m + ":" + s });
    }, 1000);
  },

  _stopTimer() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  _postResult(text) {
    const apiBase = runtimeConfig.apiBase;
    const doctorId = getApp().globalData.doctorId || "";

    wx.request({
      url: apiBase + "/api/voice/result",
      method: "POST",
      header: { "Content-Type": "application/json" },
      data: { doctor_id: doctorId, text: text },
      complete: () => wx.navigateBack(),
    });
  },
});
