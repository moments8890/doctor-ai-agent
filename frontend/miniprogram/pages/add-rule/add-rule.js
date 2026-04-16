const config = require('../../config.js');

const RECORDER_OPTIONS = {
  duration: 60000,
  sampleRate: 16000,
  numberOfChannels: 1,
  encodeBitRate: 96000,
  format: 'mp3',
};

const MIN_RECORDING_MS = 1000;

const CATEGORY_META = {
  custom:     { label: '自定义', badgeClass: 'badge-custom' },
  diagnosis:  { label: '诊断',   badgeClass: 'badge-diagnosis' },
  followup:   { label: '随访',   badgeClass: 'badge-followup' },
  medication: { label: '用药',   badgeClass: 'badge-medication' },
};

function categoryMeta(key) {
  return CATEGORY_META[key] || CATEGORY_META.custom;
}

Page({
  data: {
    state: 'idle',
    hintText: '前交通动脉瘤术后第二周要关注记忆问题',
    elapsed: 0,
    transcript: '',
    candidate: null,
    errorCode: null,
    errorCopy: {
      audio_unclear: '没听清楚，请靠近麦克风再说一次',
      no_rule_found: '没找到明确的规则。试试说：「当 X 时，要 Y」',
      multi_rule_detected: '听起来像多条规则，请一次说一条',
      too_long: '录音超过 1 分钟，请分条说明',
      network: '网络异常，请重试',
      rate_limited: '今日额度已用完，请明天再试',
      internal: '出错了，请重试',
    },
  },

  onLoad() {
    this.recorderManager = wx.getRecorderManager();
    this._recordStartTs = 0;
    this._timerHandle = null;

    this.recorderManager.onStart(() => {
      this._recordStartTs = Date.now();
      this.setData({ state: 'recording', elapsed: 0 });
      this._timerHandle = setInterval(() => {
        this.setData({ elapsed: Math.floor((Date.now() - this._recordStartTs) / 1000) });
      }, 250);
    });

    this.recorderManager.onStop((res) => {
      if (this._timerHandle) { clearInterval(this._timerHandle); this._timerHandle = null; }
      const duration = Date.now() - this._recordStartTs;
      if (duration < MIN_RECORDING_MS) {
        this.setData({ state: 'idle' });
        return;
      }
      this._handleRecordingFinished(res.tempFilePath);
    });

    this.recorderManager.onError((err) => {
      console.warn('recorder error', err);
      this.setData({ state: 'error', errorCode: 'internal' });
    });
  },

  onUnload() {
    if (this._timerHandle) clearInterval(this._timerHandle);
  },

  onHide() {
    if (this.data.state === 'recording') {
      try { this.recorderManager.stop(); } catch (_) {}
      this.setData({ state: 'idle' });
    }
  },

  onMicPressStart() {
    wx.authorize({
      scope: 'scope.record',
      success: () => this.recorderManager.start(RECORDER_OPTIONS),
      fail: () => this.setData({ state: 'perm_denied' }),
    });
  },

  onMicPressEnd() {
    if (this.data.state === 'recording') {
      this.recorderManager.stop();
    }
  },

  _handleRecordingFinished(tempFilePath) {
    this.setData({ state: 'processing' });

    const token = wx.getStorageSync('token') || '';
    const doctorId = wx.getStorageSync('doctorId') || '';

    wx.uploadFile({
      url: `${config.apiBase}/api/manage/knowledge/voice-extract?doctor_id=${encodeURIComponent(doctorId)}`,
      filePath: tempFilePath,
      name: 'file',
      header: { 'Authorization': `Bearer ${token}` },
      timeout: 15000,
      success: (res) => this._onExtractResponse(res),
      fail: () => this.setData({ state: 'error', errorCode: 'network' }),
    });
  },

  _onExtractResponse(res) {
    if (res.statusCode !== 200) {
      this.setData({ state: 'error', errorCode: 'network' });
      return;
    }
    let body;
    try { body = JSON.parse(res.data); }
    catch (_) { this.setData({ state: 'error', errorCode: 'internal' }); return; }

    if (body.error) {
      this.setData({ state: 'error', errorCode: body.error, transcript: body.transcript || '' });
      return;
    }
    if (body.candidate) {
      this.setData({
        state: 'candidate',
        candidate: this._decorate(body.candidate),
        transcript: body.transcript || '',
      });
      return;
    }
    this.setData({ state: 'error', errorCode: 'internal' });
  },

  _decorate(candidate) {
    if (!candidate) return candidate;
    const meta = categoryMeta(candidate.category);
    return Object.assign({}, candidate, { _label: meta.label, _badgeClass: meta.badgeClass });
  },

  onEditContent() {
    if (!this.data.candidate) return;
    const current = this.data.candidate.content || '';
    wx.showModal({
      title: '修改规则文字',
      editable: true,
      placeholderText: '修改规则内容…',
      content: current,
      success: (res) => {
        if (res.confirm && typeof res.content === 'string' && res.content.trim()) {
          const updated = Object.assign({}, this.data.candidate, {
            content: res.content.trim(),
          });
          this.setData({ candidate: updated });
        }
      },
    });
  },

  onReRecord() {
    this.setData({ state: 'idle', candidate: null, errorCode: null, transcript: '' });
  },

  onSave() {
    if (!this.data.candidate) return;
    this.setData({ state: 'saving' });

    const token = wx.getStorageSync('token') || '';
    const doctorId = wx.getStorageSync('doctorId') || '';

    wx.request({
      url: `${config.apiBase}/api/manage/knowledge?doctor_id=${encodeURIComponent(doctorId)}`,
      method: 'POST',
      header: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {
        content: this.data.candidate.content,
        category: this.data.candidate.category,
      },
      timeout: 10000,
      success: (res) => {
        if (res.statusCode === 200 && res.data && res.data.status === 'ok') {
          wx.showToast({ title: '已保存', icon: 'success', duration: 1500 });
          setTimeout(() => wx.navigateBack(), 1500);
        } else {
          wx.showToast({ title: '保存失败', icon: 'none' });
          this.setData({ state: 'candidate' });
        }
      },
      fail: () => {
        wx.showToast({ title: '网络异常', icon: 'none' });
        this.setData({ state: 'candidate' });
      },
    });
  },

  onOpenSetting() {
    wx.openSetting({
      success: (res) => {
        if (res.authSetting['scope.record']) {
          this.setData({ state: 'idle' });
        }
      },
    });
  },

  onCancel() {
    wx.navigateBack();
  },
});
