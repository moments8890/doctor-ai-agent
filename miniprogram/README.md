# WeChat Mini Program Client (MVP)

This folder contains a minimal native Mini Program client that integrates with the new backend APIs:

- `POST /api/auth/wechat-mini/login`
- `GET /api/mini/me`
- `POST /api/mini/chat`
- `GET /api/mini/patients`
- `GET /api/mini/records`
- `GET/PATCH /api/mini/tasks`

## Configure

1. Open `miniprogram/config.js`.
2. Set `apiBase` to your backend HTTPS origin, for example:

```js
module.exports = {
  apiBase: "https://api.example.com",
};
```

## Run in WeChat DevTools

1. Import this `miniprogram/` folder in WeChat DevTools.
2. Ensure the appid is your Mini Program appid.
3. Start with `pages/login/login` and login via `wx.login`.

## Backend env vars

- `WECHAT_MINI_APP_ID`
- `WECHAT_MINI_APP_SECRET`
- `MINIPROGRAM_TOKEN_SECRET`
- `MINIPROGRAM_TOKEN_TTL_SECONDS` (default 604800)

For local mock login (no real WeChat exchange):

- `WECHAT_MINI_ALLOW_MOCK_CODE=true`
- pass `code = mock:<openid>` to `/api/auth/wechat-mini/login`
