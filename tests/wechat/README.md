# WeChat E2E Tests

This folder contains WeChat/WeCom entrypoint E2E-style tests:

- `test_wechat_kf_e2e.py`
- `test_wechat_multi_input_e2e.py`

## Test types

- Local simulation tests:
  - Use mocked WeCom API calls and mocked async tasks.
  - Validate callback/sync message parsing, routing, and persistence behavior.
  - Usually runnable without real WeChat credentials.

- Live WeCom sync test (optional):
  - `test_wecom_kf_sync_msg_live_https` in `test_wechat_kf_e2e.py`.
  - Only runs when explicitly enabled.

## Requirements

1. Bootstrap dependencies:
   - `./dev.sh bootstrap --with-frontend`
2. For local simulation tests:
   - no live WeChat credentials required
   - no running server required
3. For live test:
   - `WECHAT_KF_LIVE_TEST=1`
   - valid `WECHAT_KF_ACCESS_TOKEN`
   - outbound internet access to `qyapi.weixin.qq.com`

## WeCom KF setup checklist

Configure in:
- `https://work.weixin.qq.com/kf`

Required console fields:
- `企业ID (CorpID)` (example: `ww9c1d2ea57364ffd0`)
- `Secret` (客服应用 Secret; do not commit plaintext)
- `微信开发者ID绑定` (if you need unionid mapping APIs)
- `回调 URL` (example: `https://<your-domain>/wechat`)
- `Token`
- `EncodingAESKey`

Runtime env/config mapping used by tests/services:
- `WECHAT_KF_CORP_ID` -> 企业ID
- `WECHAT_KF_SECRET` -> Secret
- `WECHAT_TOKEN` -> 回调 Token
- `WECHAT_AES_KEY` -> 回调 EncodingAESKey
- `WECHAT_KF_ACCESS_TOKEN` -> live sync test token (`test_wecom_kf_sync_msg_live_https`)

Security note:
- Keep Secret/Token/AESKey in local runtime config or local env only.
- If credentials were exposed, rotate them in WeCom console before further testing.

## Run

```bash
.venv/bin/python -m pytest tests/wechat/ -v
```

Run live test only:

```bash
WECHAT_KF_LIVE_TEST=1 WECHAT_KF_ACCESS_TOKEN=<token> \
  .venv/bin/python -m pytest tests/wechat/test_wechat_kf_e2e.py -k live -v
```
