"""
微信公众号自定义菜单创建工具，定义医生助手的快捷操作菜单结构。
"""

import httpx
from utils.log import log

MENU_CREATE_URL = "https://api.weixin.qq.com/cgi-bin/menu/create"

MENU = {
    "button": [
        {
            "name": "医生",
            "sub_button": [
                {"type": "click", "name": "所有病人", "key": "DOCTOR_ALL_PATIENTS"},
                {"type": "click", "name": "新建患者", "key": "DOCTOR_NEW_PATIENT"},
                {"type": "click", "name": "查询病历", "key": "DOCTOR_QUERY"},
            ],
        },
    ]
}


async def create_menu(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            MENU_CREATE_URL,
            params={"access_token": access_token},
            json=MENU,
        )
        data = resp.json()
        log(f"[WeChat menu] create response: {data}")
        return data
