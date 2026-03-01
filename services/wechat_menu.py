import httpx
from utils.log import log

MENU_CREATE_URL = "https://api.weixin.qq.com/cgi-bin/menu/create"

MENU = {
    "button": [
        {
            "name": "患者",
            "sub_button": [
                {"type": "click", "name": "我的病历", "key": "PATIENT_RECORDS"},
                {"type": "click", "name": "咨询医生", "key": "PATIENT_CONSULT"},
                {"type": "click", "name": "使用说明", "key": "PATIENT_HELP"},
            ],
        },
        {
            "name": "医生",
            "sub_button": [
                {"type": "click", "name": "所有病人", "key": "DOCTOR_ALL_PATIENTS"},
                {"type": "click", "name": "新建患者", "key": "DOCTOR_NEW_PATIENT"},
                {"type": "click", "name": "录入病历", "key": "DOCTOR_ADD_RECORD"},
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
