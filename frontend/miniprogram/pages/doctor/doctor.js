const runtimeConfig = require("../../config.js");

// Miniapp polls /api/voice/session as a lightweight command-bus. Kept very
// short because click-to-recording latency is dominated by this interval —
// users start speaking before WechatSI has engaged and the opening syllables
// get clipped. The endpoint is an in-memory dict lookup, so 200ms is cheap.
const VOICE_POLL_IDLE_MS = 200;
const VOICE_POLL_ACTIVE_MS = 200;

const plugin = requirePlugin("WechatSI");

Page({
  data: {
    url: "",
    loading: true,
    loadError: false,
    showPermissionPrompt: false,
  },

  // Voice recording state (not in data — no UI rendering needed)
  _voicePollTimer: null,
  _isRecording: false,
  _siManager: null,

  onLoad() {
    const app = getApp();
    const token = app.globalData.accessToken;
    const doctorId = app.globalData.doctorId;
    const doctorName = app.globalData.doctorName || "";

    if (!token) {
      wx.redirectTo({ url: "/pages/login/login" });
      return;
    }

    const webBase = app.globalData.apiBase;
    const qs = [
      "token="     + encodeURIComponent(token),
      "doctor_id=" + encodeURIComponent(doctorId),
      "name="      + encodeURIComponent(doctorName),
    ].join("&");

    this.setData({ url: webBase + "/doctor?" + qs });

    // Initialize WechatSI recognition manager
    const manager = plugin.getRecordRecognitionManager();
    this._siManager = manager;

    manager.onStart = () => {
      // WechatSI fires onStart only after its audio stream to the cloud is
      // fully established (typically 500-1000ms after plugin.start()). Post
      // "recording" here rather than in _startRecording so the web UI flips
      // to "正在识别…" at the moment the plugin can actually hear the user —
      // otherwise the first syllables get clipped.
      this._postVoiceSession("recording");
    };

    manager.onRecognize = (res) => {
      const interim = (res && res.result) || "";
      if (interim && interim !== this._lastInterim) {
        this._lastInterim = interim;
        this._postVoiceSession("interim", { text: interim });
      }
    };

    manager.onStop = (res) => {
      this._isRecording = false;
      this._stopRequested = false;
      this._lastInterim = null;
      const text = (res && res.result) || "";
      if (!text) {
        this._postVoiceSession("error", { error: "audio_unclear" });
        return;
      }
      this._postVoiceSession("result", { text: text });
    };

    manager.onError = (res) => {
      console.error("[voice] manager.onError", res);
      this._isRecording = false;
      this._stopRequested = false;
      this._postVoiceSession("error", { error: "asr_failed" });
    };

    // Show permission prompt if configured
    if (runtimeConfig.subscribeTemplateId && !wx.getStorageSync("permission_prompted")) {
      this.setData({ showPermissionPrompt: true, loading: false });
    }
  },

  onShow() {
    this._startVoicePoll();

    // Legacy: check voice result from add-rule page
    const app = getApp();
    const result = app.globalData.voiceResult;
    const ts = app.globalData.voiceResultTs;
    if (result && ts && Date.now() - ts < 10000) {
      app.globalData.voiceResult = null;
      app.globalData.voiceResultTs = null;
      this._pendingVoiceText = result;
    }
  },

  onHide() {
    this._stopVoicePoll();
    if (this._isRecording) {
      try { this._siManager.stop(); } catch (_) {}
      this._isRecording = false;
    }
  },

  onUnload() {
    this._stopVoicePoll();
  },

  // ── Voice polling ──────────────────────────────────────────────────────

  _startVoicePoll() {
    this._stopVoicePoll();
    const app = getApp();
    const doctorId = app.globalData.doctorId;
    const token = app.globalData.accessToken;
    if (!doctorId || !token) return;

    this._voicePollMode = "idle";
    this._scheduleNextVoicePoll(doctorId, token);
  },

  _scheduleNextVoicePoll(doctorId, token) {
    const delay = (this._voicePollMode === "active" || this._isRecording)
      ? VOICE_POLL_ACTIVE_MS
      : VOICE_POLL_IDLE_MS;
    this._voicePollTimer = setTimeout(() => {
      this._pollVoiceSession(doctorId, token);
    }, delay);
  },

  _stopVoicePoll() {
    if (this._voicePollTimer) {
      clearTimeout(this._voicePollTimer);
      this._voicePollTimer = null;
    }
    this._voicePollMode = "idle";
  },

  _pollVoiceSession(doctorId, token) {
    wx.request({
      url: runtimeConfig.apiBase + "/api/voice/session?doctor_id=" + encodeURIComponent(doctorId),
      header: { "Authorization": "Bearer " + token },
      timeout: 3000,
      success: (res) => {
        if (res.statusCode === 200) {
          const data = res.data || {};

          if (data.action === "start") {
            if (!this._isRecording) {
              this._startRecording(doctorId, token);
            }
          } else if (data.action === "stop") {
            if (this._isRecording && !this._stopRequested) {
              // Call plugin.stop() only ONCE — onStop fires asynchronously and
              // acks the session via _postVoiceSession("result"/"error").
              this._stopRequested = true;
              this._siManager.stop();
            } else if (!this._isRecording && !this._stopRequested) {
              // Stop arrived but we're not recording — plugin may have auto-
              // stopped (58s cap) or session drifted. Ack so the server doesn't
              // sit at pending_stop forever.
              this._postVoiceSession("error", { error: "recording_not_active" });
            }
          } else if (data.status === "idle" || data.status === "error") {
            // Server session cleared (web-view posted "clear" or timed out).
            // If the plugin actually started in the tiny race window, stop it
            // so we don't leave a zombie recognition eating battery.
            if (this._isRecording && !this._stopRequested) {
              this._stopRequested = true;
              try { this._siManager.stop(); } catch (_) {}
            }
            this._isRecording = false;
          }

          // Speed up or slow down polling based on session activity.
          // Active when: there's a pending command, or we're mid-recording,
          // or the session exists but not yet cleared (status != idle).
          const hasActivity = !!data.action
            || this._isRecording
            || (data.status && data.status !== "idle");
          this._voicePollMode = hasActivity ? "active" : "idle";
        }
      },
      complete: () => {
        // Always re-arm — single-shot setTimeout so interval can change between ticks.
        if (this._voicePollTimer !== null) {
          this._scheduleNextVoicePoll(doctorId, token);
        }
      },
    });
  },

  _startRecording(doctorId, token) {
    // Guard synchronously before any async work — prevents the next poll tick
    // from re-entering this function while authorize is still resolving.
    this._isRecording = true;
    wx.authorize({
      scope: "scope.record",
      success: () => {
        try {
          this._siManager.start({ duration: 58000, lang: "zh_CN" });
          // Don't post "recording" here — onStart posts it when the plugin is
          // actually streaming to the cloud. Leaving the session at
          // pending_start keeps the web UI in "准备中…" until we're truly live.
        } catch (e) {
          console.error("[voice] plugin.start", e);
          this._isRecording = false;
          this._postVoiceSession("error", { error: "asr_failed" });
        }
      },
      fail: () => {
        this._isRecording = false;
        this._postVoiceSession("error", { error: "permission_denied" });
      },
    });
  },

  _postVoiceSession(action, extra) {
    const app = getApp();
    const doctorId = app.globalData.doctorId;
    const token = app.globalData.accessToken;
    wx.request({
      url: runtimeConfig.apiBase + "/api/voice/session",
      method: "POST",
      header: {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
      },
      data: Object.assign({ doctor_id: doctorId, action: action }, extra || {}),
      timeout: 5000,
    });
  },

  // ── Existing handlers ──────────────────────────────────────────────────

  onEnterTap() {
    const tmplId = runtimeConfig.subscribeTemplateId;
    if (tmplId) {
      wx.requestSubscribeMessage({
        tmplIds: [tmplId],
        complete: () => {
          wx.setStorageSync("permission_prompted", "1");
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

  onError(e) {
    console.error("WebView load failed:", e.detail);
    this.setData({ loadError: true, loading: false });
  },

  onRetry() {
    const base = this.data.url.split("?")[0];
    const qs = this.data.url.split("?")[1] || "";
    const bust = "_t=" + Date.now();
    const newUrl = base + "?" + (qs ? qs + "&" : "") + bust;
    this.setData({ url: newUrl, loadError: false, loading: true });
  },

  onMessage(e) {
    const msgs = e.detail.data || [];
    const last = msgs[msgs.length - 1];
    if (!last) return;

    if (last.action === "logout") {
      this._clearAuth();
      wx.redirectTo({ url: "/pages/login/login" });
    }
  },

  onShareAppMessage() {
    return {
      title: "鲸鱼随行 · AI 医疗助手",
      path: "/pages/login/login",
    };
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
