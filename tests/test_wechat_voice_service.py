"""微信语音服务测试：验证企业微信客服与公众号环境下语音媒体文件下载 URL 的正确选择逻辑。"""

from __future__ import annotations

from unittest.mock import patch

from services.wechat.wechat_voice import _media_get_url


def test_media_get_url_uses_qyapi_for_kf_env() -> None:
    with patch.dict("os.environ", {"WECHAT_KF_CORP_ID": "ww123"}, clear=False):
        assert _media_get_url() == "https://qyapi.weixin.qq.com/cgi-bin/media/get"


def test_media_get_url_uses_wechat_public_api_without_kf_env() -> None:
    with patch.dict("os.environ", {"WECHAT_KF_CORP_ID": ""}, clear=False):
        assert _media_get_url() == "https://api.weixin.qq.com/cgi-bin/media/get"

