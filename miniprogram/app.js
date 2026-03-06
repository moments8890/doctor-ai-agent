const runtimeConfig = require("./config.js");

App({
  globalData: {
    apiBase: runtimeConfig.apiBase || "https://nano-redhead-attitudes-attachment.trycloudflare.com",
    accessToken: "",
    doctorId: "",
  },
});
