"""Auth router unit tests: WeChat mini login, web login, invite login, /me, unlink."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import routers.auth as auth_mod
from services.auth.miniprogram_auth import MiniProgramAuthError, MiniProgramPrincipal


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestWechatMiniAppId:
    def test_returns_env_value(self):
        with patch.dict("os.environ", {"WECHAT_MINI_APP_ID": " wx123 "}, clear=False):
            assert auth_mod._wechat_mini_app_id() == "wx123"

    def test_returns_empty_when_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            assert auth_mod._wechat_mini_app_id() == ""


class TestWechatMiniSecret:
    def test_returns_env_value(self):
        with patch.dict("os.environ", {"WECHAT_MINI_APP_SECRET": "secret123"}, clear=False):
            assert auth_mod._wechat_mini_secret() == "secret123"


class TestAllowMockCodes:
    def test_true_values(self):
        for val in ("1", "true", "yes", "on", "TRUE"):
            with patch.dict("os.environ", {"WECHAT_MINI_ALLOW_MOCK_CODE": val}, clear=False):
                assert auth_mod._allow_mock_codes() is True

    def test_false_when_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            assert auth_mod._allow_mock_codes() is False

    def test_false_for_other_values(self):
        with patch.dict("os.environ", {"WECHAT_MINI_ALLOW_MOCK_CODE": "nope"}, clear=False):
            assert auth_mod._allow_mock_codes() is False


# ---------------------------------------------------------------------------
# _fetch_wechat_openid
# ---------------------------------------------------------------------------

class TestFetchWechatOpenid:
    @pytest.mark.asyncio
    async def test_mock_code_allowed(self):
        with patch.dict("os.environ", {"WECHAT_MINI_ALLOW_MOCK_CODE": "1"}, clear=False):
            result = await auth_mod._fetch_wechat_openid("mock:test_openid_123")
        assert result == "test_openid_123"

    @pytest.mark.asyncio
    async def test_mock_code_empty_falls_through(self):
        """mock: with empty value should fall through to real API."""
        with patch.dict("os.environ", {
            "WECHAT_MINI_ALLOW_MOCK_CODE": "1",
            "WECHAT_MINI_APP_ID": "wxid",
            "WECHAT_MINI_APP_SECRET": "secret",
        }, clear=False):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"openid": "real_openid"}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("routers.auth.httpx.AsyncClient", return_value=mock_client):
                result = await auth_mod._fetch_wechat_openid("mock:")
        assert result == "real_openid"

    @pytest.mark.asyncio
    async def test_no_appid_raises_500(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(HTTPException) as exc:
                await auth_mod._fetch_wechat_openid("real_code")
        assert exc.value.status_code == 500
        assert "not configured" in exc.value.detail

    @pytest.mark.asyncio
    async def test_errcode_nonzero_raises_401(self):
        with patch.dict("os.environ", {
            "WECHAT_MINI_APP_ID": "wxid",
            "WECHAT_MINI_APP_SECRET": "secret",
        }, clear=False):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"errcode": 40029, "errmsg": "invalid code"}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("routers.auth.httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(HTTPException) as exc:
                    await auth_mod._fetch_wechat_openid("bad_code")
        assert exc.value.status_code == 401
        assert "code2session failed" in exc.value.detail

    @pytest.mark.asyncio
    async def test_missing_openid_raises_401(self):
        with patch.dict("os.environ", {
            "WECHAT_MINI_APP_ID": "wxid",
            "WECHAT_MINI_APP_SECRET": "secret",
        }, clear=False):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"errcode": 0}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("routers.auth.httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(HTTPException) as exc:
                    await auth_mod._fetch_wechat_openid("some_code")
        assert exc.value.status_code == 401
        assert "missing openid" in exc.value.detail

    @pytest.mark.asyncio
    async def test_success_returns_openid(self):
        with patch.dict("os.environ", {
            "WECHAT_MINI_APP_ID": "wxid",
            "WECHAT_MINI_APP_SECRET": "secret",
        }, clear=False):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"errcode": 0, "openid": "wx_openid_abc"}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("routers.auth.httpx.AsyncClient", return_value=mock_client):
                result = await auth_mod._fetch_wechat_openid("valid_code")
        assert result == "wx_openid_abc"


# ---------------------------------------------------------------------------
# wechat_mini_login endpoint
# ---------------------------------------------------------------------------

class TestWechatMiniLogin:
    @pytest.mark.asyncio
    async def test_empty_code_raises_422(self):
        body = auth_mod.MiniProgramLoginInput(code="  ")
        with pytest.raises(HTTPException) as exc:
            await auth_mod.wechat_mini_login(body)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_success(self):
        with patch.dict("os.environ", {
            "WECHAT_MINI_ALLOW_MOCK_CODE": "1",
            "MINIPROGRAM_TOKEN_SECRET": "test-secret-123",
            "ENVIRONMENT": "test",
        }, clear=False), \
             patch("routers.auth._upsert_mini_doctor", new=AsyncMock(return_value="wxmini_test_oid")), \
             patch("routers.auth.enforce_doctor_rate_limit"):
            body = auth_mod.MiniProgramLoginInput(code="mock:test_oid")
            result = await auth_mod.wechat_mini_login(body)

        assert result.doctor_id == "wxmini_test_oid"
        assert result.channel == "wechat_mini"
        assert result.access_token
        assert result.wechat_openid == "test_oid"


# ---------------------------------------------------------------------------
# web_login endpoint
# ---------------------------------------------------------------------------

class TestWebLogin:
    @pytest.mark.asyncio
    async def test_empty_doctor_id_raises_422(self):
        body = auth_mod.WebLoginInput(doctor_id="  ")
        with pytest.raises(HTTPException) as exc:
            await auth_mod.web_login(body)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_success(self):
        with patch.dict("os.environ", {
            "MINIPROGRAM_TOKEN_SECRET": "test-secret",
            "ENVIRONMENT": "test",
        }, clear=False), \
             patch("routers.auth._upsert_web_doctor", new=AsyncMock()), \
             patch("routers.auth.enforce_doctor_rate_limit"):
            body = auth_mod.WebLoginInput(doctor_id="doc_abc", name="Dr. Test")
            result = await auth_mod.web_login(body)

        assert result.doctor_id == "doc_abc"
        assert result.channel == "app"
        assert result.access_token


# ---------------------------------------------------------------------------
# _upsert_web_doctor
# ---------------------------------------------------------------------------

class TestUpsertWebDoctor:
    @pytest.mark.asyncio
    async def test_creates_new_doctor(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        db.add = MagicMock()
        db.commit = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            await auth_mod._upsert_web_doctor("new_doc", "Dr. New")

        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_doctor(self):
        existing = MagicMock()
        existing.name = None

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            await auth_mod._upsert_web_doctor("existing_doc", "New Name")

        assert existing.name == "New Name"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_name(self):
        existing = MagicMock()
        existing.name = "Original Name"

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            await auth_mod._upsert_web_doctor("existing_doc", "Ignored Name")

        assert existing.name == "Original Name"

    @pytest.mark.asyncio
    async def test_specialty_set_on_new(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        db.add = MagicMock()
        db.commit = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            await auth_mod._upsert_web_doctor("doc", "Dr.", specialty="cardiology")

        added_obj = db.add.call_args[0][0]
        assert added_obj.specialty == "cardiology"


# ---------------------------------------------------------------------------
# invite_login endpoint
# ---------------------------------------------------------------------------

class TestInviteLogin:
    @pytest.mark.asyncio
    async def test_empty_code_raises_422(self):
        body = auth_mod.InviteLoginInput(code="  ")
        with pytest.raises(HTTPException) as exc:
            await auth_mod.invite_login(body)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_success_existing_doctor(self):
        with patch.dict("os.environ", {
            "MINIPROGRAM_TOKEN_SECRET": "test-secret",
            "ENVIRONMENT": "test",
        }, clear=False), \
             patch("routers.auth._resolve_invite_doctor_id", new=AsyncMock(return_value=("doc1", "Dr One", None))), \
             patch("routers.auth._upsert_web_doctor", new=AsyncMock()), \
             patch("routers.auth.enforce_doctor_rate_limit"), \
             patch("routers.auth.audit", new=AsyncMock()), \
             patch("asyncio.ensure_future"):
            body = auth_mod.InviteLoginInput(code="INVITE123")
            result = await auth_mod.invite_login(body)

        assert result.doctor_id == "doc1"
        assert result.channel == "app"

    @pytest.mark.asyncio
    async def test_success_new_doctor_id_created(self):
        with patch.dict("os.environ", {
            "MINIPROGRAM_TOKEN_SECRET": "test-secret",
            "ENVIRONMENT": "test",
        }, clear=False), \
             patch("routers.auth._resolve_invite_doctor_id", new=AsyncMock(return_value=("inv_new", "Dr New", "inv_new"))), \
             patch("routers.auth._upsert_web_doctor", new=AsyncMock()), \
             patch("routers.auth._bind_new_doctor_to_invite", new=AsyncMock(return_value="inv_new")), \
             patch("routers.auth.enforce_doctor_rate_limit"), \
             patch("routers.auth.audit", new=AsyncMock()), \
             patch("asyncio.ensure_future"):
            body = auth_mod.InviteLoginInput(code="NEW_INVITE")
            result = await auth_mod.invite_login(body)

        assert result.doctor_id == "inv_new"

    @pytest.mark.asyncio
    async def test_with_js_code_links_mini_openid(self):
        with patch.dict("os.environ", {
            "MINIPROGRAM_TOKEN_SECRET": "test-secret",
            "ENVIRONMENT": "test",
            "WECHAT_MINI_ALLOW_MOCK_CODE": "1",
        }, clear=False), \
             patch("routers.auth._resolve_invite_doctor_id", new=AsyncMock(return_value=("doc1", "Dr", None))), \
             patch("routers.auth._upsert_web_doctor", new=AsyncMock()), \
             patch("routers.auth._link_mini_openid_from_jscode", new=AsyncMock(return_value="mini_oid")), \
             patch("routers.auth.enforce_doctor_rate_limit"), \
             patch("routers.auth.audit", new=AsyncMock()), \
             patch("asyncio.ensure_future"):
            body = auth_mod.InviteLoginInput(code="INV", js_code="mock:mini_oid")
            result = await auth_mod.invite_login(body)

        assert result.channel == "wechat_mini"


# ---------------------------------------------------------------------------
# _resolve_invite_doctor_id
# ---------------------------------------------------------------------------

class TestResolveInviteDoctorId:
    @pytest.mark.asyncio
    async def test_invalid_code_raises_401(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            with pytest.raises(HTTPException) as exc:
                await auth_mod._resolve_invite_doctor_id("BADCODE")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_code_raises_401(self):
        invite = MagicMock()
        invite.active = False

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite
        db.execute = AsyncMock(return_value=result_mock)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            with pytest.raises(HTTPException) as exc:
                await auth_mod._resolve_invite_doctor_id("INACTIVE")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_existing_doctor_id_returned(self):
        invite = MagicMock()
        invite.active = True
        invite.doctor_id = "existing_doc"
        invite.doctor_name = "Dr. Existing"

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite
        db.execute = AsyncMock(return_value=result_mock)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            doc_id, doc_name, new_id = await auth_mod._resolve_invite_doctor_id("VALID")

        assert doc_id == "existing_doc"
        assert doc_name == "Dr. Existing"
        assert new_id is None

    @pytest.mark.asyncio
    async def test_no_doctor_id_generates_new(self):
        invite = MagicMock()
        invite.active = True
        invite.doctor_id = None
        invite.doctor_name = "New Doctor"

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite
        db.execute = AsyncMock(return_value=result_mock)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            doc_id, doc_name, new_id = await auth_mod._resolve_invite_doctor_id("NEW")

        assert new_id is not None
        assert new_id.startswith("inv_")
        assert doc_id == new_id


# ---------------------------------------------------------------------------
# _bind_new_doctor_to_invite
# ---------------------------------------------------------------------------

class TestBindNewDoctorToInvite:
    @pytest.mark.asyncio
    async def test_binds_new_doctor(self):
        invite = MagicMock()
        invite.doctor_id = None
        invite.used_count = 0

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            result = await auth_mod._bind_new_doctor_to_invite("CODE", "new_doc_id")

        assert result == "new_doc_id"
        assert invite.doctor_id == "new_doc_id"
        assert invite.used_count == 1

    @pytest.mark.asyncio
    async def test_race_condition_returns_existing(self):
        invite = MagicMock()
        invite.doctor_id = "race_winner_doc"

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite
        db.execute = AsyncMock(return_value=result_mock)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            result = await auth_mod._bind_new_doctor_to_invite("CODE", "loser_doc")

        assert result == "race_winner_doc"


# ---------------------------------------------------------------------------
# unlink_mini_openid
# ---------------------------------------------------------------------------

class TestUnlinkMiniOpenid:
    @pytest.mark.asyncio
    async def test_no_auth_raises_401(self):
        with patch("routers.auth.parse_bearer_token", side_effect=MiniProgramAuthError("bad")):
            with pytest.raises(HTTPException) as exc:
                await auth_mod.unlink_mini_openid(authorization="Bearer bad")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_doctor_not_found_raises_404(self):
        principal = MiniProgramPrincipal(doctor_id="doc1", channel="app", wechat_openid=None)

        db = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.parse_bearer_token", return_value="tok"), \
             patch("routers.auth.verify_miniprogram_token", return_value=principal), \
             patch("routers.auth.get_doctor_by_id", new=AsyncMock(return_value=None)), \
             patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            with pytest.raises(HTTPException) as exc:
                await auth_mod.unlink_mini_openid(authorization="Bearer tok")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_success_clears_mini_openid(self):
        principal = MiniProgramPrincipal(doctor_id="doc1", channel="wechat_mini", wechat_openid="oid")
        doctor_row = MagicMock()
        doctor_row.mini_openid = "hashed_oid"

        db = AsyncMock()
        db.commit = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.parse_bearer_token", return_value="tok"), \
             patch("routers.auth.verify_miniprogram_token", return_value=principal), \
             patch("routers.auth.get_doctor_by_id", new=AsyncMock(return_value=doctor_row)), \
             patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            await auth_mod.unlink_mini_openid(authorization="Bearer tok")

        assert doctor_row.mini_openid is None
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# auth_me endpoint
# ---------------------------------------------------------------------------

class TestAuthMe:
    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        with patch("routers.auth.parse_bearer_token", side_effect=MiniProgramAuthError("bad")):
            with pytest.raises(HTTPException) as exc:
                await auth_mod.auth_me(authorization="Bearer invalid")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_success_with_doctor_name(self):
        principal = MiniProgramPrincipal(doctor_id="doc1", channel="app", wechat_openid=None)
        doctor_row = MagicMock()
        doctor_row.name = "Dr. Test"

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = doctor_row
        db.execute = AsyncMock(return_value=result_mock)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.parse_bearer_token", return_value="tok"), \
             patch("routers.auth.verify_miniprogram_token", return_value=principal), \
             patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            result = await auth_mod.auth_me(authorization="Bearer tok")

        assert result.doctor_id == "doc1"
        assert result.name == "Dr. Test"
        assert result.channel == "app"

    @pytest.mark.asyncio
    async def test_success_doctor_not_in_db(self):
        principal = MiniProgramPrincipal(doctor_id="doc_ghost", channel="wechat_mini", wechat_openid="oid")

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.parse_bearer_token", return_value="tok"), \
             patch("routers.auth.verify_miniprogram_token", return_value=principal), \
             patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            result = await auth_mod.auth_me(authorization="Bearer tok")

        assert result.doctor_id == "doc_ghost"
        assert result.name is None


# ---------------------------------------------------------------------------
# _link_mini_openid_from_jscode
# ---------------------------------------------------------------------------

class TestLinkMiniOpenidFromJscode:
    @pytest.mark.asyncio
    async def test_success(self):
        db = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth._fetch_wechat_openid", new=AsyncMock(return_value="fetched_oid")), \
             patch("routers.auth.link_mini_openid", new=AsyncMock()), \
             patch("routers.auth.AsyncSessionLocal", return_value=ctx):
            result = await auth_mod._link_mini_openid_from_jscode("mock:code", "doc1")

        assert result == "fetched_oid"

    @pytest.mark.asyncio
    async def test_failure_returns_none(self):
        with patch("routers.auth._fetch_wechat_openid", new=AsyncMock(side_effect=RuntimeError("fail"))):
            result = await auth_mod._link_mini_openid_from_jscode("bad_code", "doc1")
        assert result is None


# ---------------------------------------------------------------------------
# _upsert_mini_doctor
# ---------------------------------------------------------------------------

class TestUpsertMiniDoctor:
    @pytest.mark.asyncio
    async def test_existing_by_mini_openid(self):
        existing = MagicMock()
        existing.doctor_id = "wxmini_existing"
        existing.name = "Already Named"

        db = AsyncMock()
        db.commit = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx), \
             patch("routers.auth.get_doctor_by_mini_openid", new=AsyncMock(return_value=existing)):
            result = await auth_mod._upsert_mini_doctor("oid", "Ignored Name")

        assert result == "wxmini_existing"

    @pytest.mark.asyncio
    async def test_invite_code_linking(self):
        db = AsyncMock()
        db.commit = AsyncMock()

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx), \
             patch("routers.auth.get_doctor_by_mini_openid", new=AsyncMock(return_value=None)), \
             patch("routers.auth._try_link_via_invite", new=AsyncMock(return_value="linked_doc")):
            result = await auth_mod._upsert_mini_doctor("oid", "Name", invite_code="INV")

        assert result == "linked_doc"

    @pytest.mark.asyncio
    async def test_fallback_creates_new(self):
        db = AsyncMock()
        db.commit = AsyncMock()

        # No mini_openid match, no legacy wechat match
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.auth.AsyncSessionLocal", return_value=ctx), \
             patch("routers.auth.get_doctor_by_mini_openid", new=AsyncMock(return_value=None)), \
             patch("routers.auth._upsert_mini_doctor_new", new=AsyncMock(return_value="wxmini_new_oid")):
            result = await auth_mod._upsert_mini_doctor("new_oid", "New Doctor")

        assert result == "wxmini_new_oid"


# ---------------------------------------------------------------------------
# _try_link_via_invite
# ---------------------------------------------------------------------------

class TestTryLinkViaInvite:
    @pytest.mark.asyncio
    async def test_no_invite_returns_none(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = await auth_mod._try_link_via_invite(db, "oid", "BAD", None, now)
        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_invite_returns_none(self):
        invite = MagicMock()
        invite.active = False

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite
        db.execute = AsyncMock(return_value=result_mock)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = await auth_mod._try_link_via_invite(db, "oid", "INACTIVE", None, now)
        assert result is None

    @pytest.mark.asyncio
    async def test_success_links_and_returns_doctor_id(self):
        invite = MagicMock()
        invite.active = True
        invite.doctor_id = "target_doc"

        target = MagicMock()
        target.name = "Existing"
        target.mini_openid = None

        db = AsyncMock()
        invite_result = MagicMock()
        invite_result.scalar_one_or_none.return_value = invite
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = target
        db.execute = AsyncMock(side_effect=[invite_result, target_result])
        db.commit = AsyncMock()

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = await auth_mod._try_link_via_invite(db, "oid", "CODE", "Dr Name", now)

        assert result == "target_doc"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_target_doctor_not_found_returns_none(self):
        invite = MagicMock()
        invite.active = True
        invite.doctor_id = "missing_doc"

        db = AsyncMock()
        invite_result = MagicMock()
        invite_result.scalar_one_or_none.return_value = invite
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[invite_result, target_result])

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = await auth_mod._try_link_via_invite(db, "oid", "CODE", None, now)
        assert result is None


# ---------------------------------------------------------------------------
# _upsert_mini_doctor_new
# ---------------------------------------------------------------------------

class TestUpsertMiniDoctorNew:
    @pytest.mark.asyncio
    async def test_creates_new(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        db.add = MagicMock()
        db.commit = AsyncMock()

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = await auth_mod._upsert_mini_doctor_new(db, "oid123", "Dr. New", now)

        assert result == "wxmini_oid123"
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing(self):
        existing = MagicMock()
        existing.mini_openid = None
        existing.name = None

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = await auth_mod._upsert_mini_doctor_new(db, "oid123", "Dr. Name", now)

        assert result == "wxmini_oid123"
        assert existing.channel == "wechat_mini"
        assert existing.name == "Dr. Name"
