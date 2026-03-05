from __future__ import annotations

from unittest.mock import patch

from services.wechat_voice import _media_get_url


def test_media_get_url_uses_qyapi_for_kf_env() -> None:
    with patch.dict("os.environ", {"WECHAT_KF_CORP_ID": "ww123"}, clear=False):
        assert _media_get_url() == "https://qyapi.weixin.qq.com/cgi-bin/media/get"


def test_media_get_url_uses_wechat_public_api_without_kf_env() -> None:
    with patch.dict("os.environ", {"WECHAT_KF_CORP_ID": ""}, clear=False):
        assert _media_get_url() == "https://api.weixin.qq.com/cgi-bin/media/get"

