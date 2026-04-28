module.exports = {
  // Local dev only. Used by app.js when WeChat reports platform === "devtools"
  // (the laptop preview). On a real phone, app.js ignores this and reads
  // wx.getAccountInfoSync().miniProgram.envVersion to pick:
  //   release → webBase=app.* + apiBase=api.*
  //   develop / trial → webBase=app.stg.* + apiBase=api.stg.*
  //
  // For LAN dev: a single Vite host serves both SPA and /api proxy, so we
  // use the same value for both webBase and apiBase.
  apiBase: "http://localhost:5173",

  subscribeTemplateId: "",
};
