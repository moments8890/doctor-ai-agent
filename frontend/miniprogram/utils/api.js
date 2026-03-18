function getAppSafe() {
  return getApp();
}

function request(path, options = {}) {
  const app = getAppSafe();
  const base = app.globalData.apiBase;
  const token = app.globalData.accessToken;
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${base}${path}`,
      method: options.method || "GET",
      data: options.data || undefined,
      header: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.header || {}),
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
          return;
        }
        reject(new Error(`HTTP ${res.statusCode}: ${JSON.stringify(res.data)}`));
      },
      fail: reject,
    });
  });
}

function loginWithWechatCode(code, doctorName = "") {
  return request("/api/auth/wechat-mini/login", {
    method: "POST",
    data: {
      code,
      doctor_name: doctorName,
    },
  });
}

function loginWithInviteCode(code, jsCode) {
  const data = { code };
  if (jsCode) data.js_code = jsCode;
  return request("/api/auth/invite/login", {
    method: "POST",
    data,
  });
}

function authMe() {
  return request("/api/auth/me");
}

function miniMe() {
  return request("/api/mini/me");
}

function miniChat(text, history = []) {
  return request("/api/mini/chat", {
    method: "POST",
    data: { text, history },
  });
}

module.exports = {
  request,
  loginWithWechatCode,
  loginWithInviteCode,
  authMe,
  miniMe,
  miniChat,
};
