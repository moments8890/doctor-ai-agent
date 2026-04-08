const runtimeConfig = require("../../config.js");

const recorderManager = wx.getRecorderManager();

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
  _tempFilePath: null,

  onLoad() {
    // RecorderManager events
    recorderManager.onStart(() => {
      console.log("[Voice] recording started");
    });

    recorderManager.onStop((res) => {
      console.log("[Voice] recording stopped, tempFilePath:", res.tempFilePath);
      this._tempFilePath = res.tempFilePath;

      if (this.data.cancelled) {
        this.setData({ recording: false, cancelled: false });
        wx.navigateBack();
        return;
      }

      // Upload and transcribe
      this.setData({ recording: false, processing: true });
      this._uploadAndTranscribe(res.tempFilePath);
    });

    recorderManager.onError((err) => {
      console.error("[Voice] recorder error:", err);
      this._stopTimer();
      this.setData({
        recording: false,
        processing: false,
        error: "录音失败: " + (err.errMsg || "未知错误"),
      });
    });
  },

  onTouchStart(e) {
    if (this.data.recording || this.data.processing) return;
    this._startY = e.touches[0].clientY;
    this._seconds = 0;
    this.setData({ recording: true, cancelled: false, error: "", timerText: "00:00" });

    recorderManager.start({
      format: "mp3",
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 96000,
    });

    this._startTimer();
  },

  onTouchEnd() {
    if (!this.data.recording) return;
    this._stopTimer();

    if (this._seconds < 1) {
      recorderManager.stop();
      this.setData({ recording: false, error: "说话时间太短" });
      setTimeout(() => {
        if (this.data.error === "说话时间太短") this.setData({ error: "" });
      }, 1500);
      return;
    }

    recorderManager.stop();
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

  _uploadAndTranscribe(filePath) {
    const apiBase = runtimeConfig.apiBase;
    const doctorId = getApp().globalData.doctorId || "";

    wx.uploadFile({
      url: apiBase + "/api/transcribe",
      filePath: filePath,
      name: "file",
      success: (res) => {
        console.log("[Voice] upload response:", res.data);
        try {
          const data = JSON.parse(res.data);
          if (data.text) {
            // Store result on server so the web-view can pick it up
            wx.request({
              url: apiBase + "/api/voice/result",
              method: "POST",
              header: { "Content-Type": "application/json" },
              data: { doctor_id: doctorId, text: data.text },
              complete: () => wx.navigateBack(),
            });
          } else {
            this.setData({ processing: false, error: "未识别到语音内容" });
          }
        } catch (e) {
          console.error("[Voice] parse error:", e);
          this.setData({ processing: false, error: "语音识别失败" });
        }
      },
      fail: (err) => {
        console.error("[Voice] upload failed:", err);
        this.setData({ processing: false, error: "上传失败: " + (err.errMsg || "") });
      },
    });
  },
});
