"""
https://coolkit-technologies.github.io/eWeLink-API/#/en/PlatformOverview
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Dict

from aiohttp import ClientConnectorError, ClientWebSocketResponse, WSMessage

from .base import SIGNAL_CONNECTED, SIGNAL_UPDATE, XDevice, XRegistryBase

_LOGGER = logging.getLogger(__name__)

# https://coolkit-technologies.github.io/eWeLink-API/#/en/APICenterV2?id=interface-domain-name
API = {
    "cn": "https://cn-apia.coolkit.cn",
    "as": "https://as-apia.coolkit.cc",
    "us": "https://us-apia.coolkit.cc",
    "eu": "https://eu-apia.coolkit.cc",
}
# https://coolkit-technologies.github.io/eWeLink-API/#/en/APICenterV2?id=http-dispatchservice-app
WS = {
    "cn": "https://cn-dispa.coolkit.cn/dispatch/app",
    "as": "https://as-dispa.coolkit.cc/dispatch/app",
    "us": "https://us-dispa.coolkit.cc/dispatch/app",
    "eu": "https://eu-dispa.coolkit.cc/dispatch/app",
}

REGIONS = {
    "+93": ("Afghanistan", "as"),
    "+355": ("Albania", "eu"),
    "+213": ("Algeria", "eu"),
    "+376": ("Andorra", "eu"),
    "+244": ("Angola", "eu"),
    "+1264": ("Anguilla", "us"),
    "+1268": ("Antigua and Barbuda", "as"),
    "+54": ("Argentina", "us"),
    "+374": ("Armenia", "as"),
    "+297": ("Aruba", "eu"),
    "+247": ("Ascension", "eu"),
    "+61": ("Australia", "us"),
    "+43": ("Austria", "eu"),
    "+994": ("Azerbaijan", "as"),
    "+1242": ("Bahamas", "us"),
    "+973": ("Bahrain", "as"),
    "+880": ("Bangladesh", "as"),
    "+1246": ("Barbados", "us"),
    "+375": ("Belarus", "eu"),
    "+32": ("Belgium", "eu"),
    "+501": ("Belize", "us"),
    "+229": ("Benin", "eu"),
    "+1441": ("Bermuda", "as"),
    "+591": ("Bolivia", "us"),
    "+387": ("Bosnia and Herzegovina", "eu"),
    "+267": ("Botswana", "eu"),
    "+55": ("Brazil", "us"),
    "+673": ("Brunei", "as"),
    "+359": ("Bulgaria", "eu"),
    "+226": ("Burkina Faso", "eu"),
    "+257": ("Burundi", "eu"),
    "+855": ("Cambodia", "as"),
    "+237": ("Cameroon", "eu"),
    "+238": ("Cape Verde Republic", "eu"),
    "+1345": ("Cayman Islands", "as"),
    "+236": ("Central African Republic", "eu"),
    "+235": ("Chad", "eu"),
    "+56": ("Chile", "us"),
    "+86": ("China", "cn"),
    "+57": ("Colombia", "us"),
    "+682": ("Cook Islands", "us"),
    "+506": ("Costa Rica", "us"),
    "+385": ("Croatia", "eu"),
    "+53": ("Cuba", "us"),
    "+357": ("Cyprus", "eu"),
    "+420": ("Czech", "eu"),
    "+243": ("Democratic Republic of Congo", "eu"),
    "+45": ("Denmark", "eu"),
    "+253": ("Djibouti", "eu"),
    "+1767": ("Dominica", "as"),
    "+1809": ("Dominican Republic", "us"),
    "+670": ("East Timor", "as"),
    "+684": ("Eastern Samoa (US)", "us"),
    "+593": ("Ecuador", "us"),
    "+20": ("Egypt", "eu"),
    "+503": ("El Salvador", "us"),
    "+372": ("Estonia", "eu"),
    "+251": ("Ethiopia", "eu"),
    "+298": ("Faroe Islands", "eu"),
    "+679": ("Fiji", "us"),
    "+358": ("Finland", "eu"),
    "+33": ("France", "eu"),
    "+594": ("French Guiana", "us"),
    "+689": ("French Polynesia", "as"),
    "+241": ("Gabon", "eu"),
    "+220": ("Gambia", "eu"),
    "+995": ("Georgia", "as"),
    "+49": ("Germany", "eu"),
    "+233": ("Ghana", "eu"),
    "+350": ("Gibraltar", "eu"),
    "+30": ("Greece", "eu"),
    "+299": ("Greenland", "us"),
    "+1473": ("Grenada", "as"),
    "+590": ("Guadeloupe", "us"),
    "+1671": ("Guam", "us"),
    "+502": ("Guatemala", "us"),
    "+240": ("Guinea", "eu"),
    "+224": ("Guinea", "eu"),
    "+592": ("Guyana", "us"),
    "+509": ("Haiti", "us"),
    "+504": ("Honduras", "us"),
    "+852": ("Hong Kong, China", "as"),
    "+36": ("Hungary", "eu"),
    "+354": ("Iceland", "eu"),
    "+91": ("India", "as"),
    "+62": ("Indonesia", "as"),
    "+98": ("Iran", "as"),
    "+353": ("Ireland", "eu"),
    "+269": ("Islamic Federal Republic of Comoros", "eu"),
    "+972": ("Israel", "as"),
    "+39": ("Italian", "eu"),
    "+225": ("Ivory Coast", "eu"),
    "+1876": ("Jamaica", "us"),
    "+81": ("Japan", "as"),
    "+962": ("Jordan", "as"),
    "+254": ("Kenya", "eu"),
    "+975": ("Kingdom of Bhutan", "as"),
    "+383": ("Kosovo", "eu"),
    "+965": ("Kuwait", "as"),
    "+996": ("Kyrgyzstan", "as"),
    "+856": ("Laos", "as"),
    "+371": ("Latvia", "eu"),
    "+961": ("Lebanon", "as"),
    "+266": ("Lesotho", "eu"),
    "+231": ("Liberia", "eu"),
    "+218": ("Libya", "eu"),
    "+423": ("Liechtenstein", "eu"),
    "+370": ("Lithuania", "eu"),
    "+352": ("Luxembourg", "eu"),
    "+853": ("Macau, China", "as"),
    "+261": ("Madagascar", "eu"),
    "+265": ("Malawi", "eu"),
    "+60": ("Malaysia", "as"),
    "+960": ("Maldives", "as"),
    "+223": ("Mali", "eu"),
    "+356": ("Malta", "eu"),
    "+596": ("Martinique", "us"),
    "+222": ("Mauritania", "eu"),
    "+230": ("Mauritius", "eu"),
    "+52": ("Mexico", "us"),
    "+373": ("Moldova", "eu"),
    "+377": ("Monaco", "eu"),
    "+976": ("Mongolia", "as"),
    "+382": ("Montenegro", "as"),
    "+1664": ("Montserrat", "as"),
    "+212": ("Morocco", "eu"),
    "+258": ("Mozambique", "eu"),
    "+95": ("Myanmar", "as"),
    "+264": ("Namibia", "eu"),
    "+977": ("Nepal", "as"),
    "+31": ("Netherlands", "eu"),
    "+599": ("Netherlands Antilles", "as"),
    "+687": ("New Caledonia", "as"),
    "+64": ("New Zealand", "us"),
    "+505": ("Nicaragua", "us"),
    "+227": ("Niger", "eu"),
    "+234": ("Nigeria", "eu"),
    "+47": ("Norway", "eu"),
    "+968": ("Oman", "as"),
    "+92": ("Pakistan", "as"),
    "+970": ("Palestine", "as"),
    "+507": ("Panama", "us"),
    "+675": ("Papua New Guinea", "as"),
    "+595": ("Paraguay", "us"),
    "+51": ("Peru", "us"),
    "+63": ("Philippines", "as"),
    "+48": ("Poland", "eu"),
    "+351": ("Portugal", "eu"),
    "+974": ("Qatar", "as"),
    "+242": ("Republic of Congo", "eu"),
    "+964": ("Republic of Iraq", "as"),
    "+389": ("Republic of Macedonia", "eu"),
    "+262": ("Reunion", "eu"),
    "+40": ("Romania", "eu"),
    "+7": ("Russia", "eu"),
    "+250": ("Rwanda", "eu"),
    "+1869": ("Saint Kitts and Nevis", "as"),
    "+1758": ("Saint Lucia", "us"),
    "+1784": ("Saint Vincent", "as"),
    "+378": ("San Marino", "eu"),
    "+239": ("Sao Tome and Principe", "eu"),
    "+966": ("Saudi Arabia", "as"),
    "+221": ("Senegal", "eu"),
    "+381": ("Serbia", "eu"),
    "+248": ("Seychelles", "eu"),
    "+232": ("Sierra Leone", "eu"),
    "+65": ("Singapore", "as"),
    "+421": ("Slovakia", "eu"),
    "+386": ("Slovenia", "eu"),
    "+27": ("South Africa", "eu"),
    "+82": ("South Korea", "as"),
    "+34": ("Spain", "eu"),
    "+94": ("Sri Lanka", "as"),
    "+249": ("Sultan", "eu"),
    "+597": ("Suriname", "us"),
    "+268": ("Swaziland", "eu"),
    "+46": ("Sweden", "eu"),
    "+41": ("Switzerland", "eu"),
    "+963": ("Syria", "as"),
    "+886": ("Taiwan, China", "as"),
    "+992": ("Tajikistan", "as"),
    "+255": ("Tanzania", "eu"),
    "+66": ("Thailand", "as"),
    "+228": ("Togo", "eu"),
    "+676": ("Tonga", "us"),
    "+1868": ("Trinidad and Tobago", "us"),
    "+216": ("Tunisia", "eu"),
    "+90": ("Turkey", "as"),
    "+993": ("Turkmenistan", "as"),
    "+1649": ("Turks and Caicos", "as"),
    "+44": ("UK", "eu"),
    "+256": ("Uganda", "eu"),
    "+380": ("Ukraine", "eu"),
    "+971": ("United Arab Emirates", "as"),
    "+1": ("United States", "us"),
    "+598": ("Uruguay", "us"),
    "+998": ("Uzbekistan", "as"),
    "+678": ("Vanuatu", "us"),
    "+58": ("Venezuela", "us"),
    "+84": ("Vietnam", "as"),
    "+685": ("Western Samoa", "us"),
    "+1340": ("Wilk Islands", "as"),
    "+967": ("Yemen", "as"),
    "+260": ("Zambia", "eu"),
    "+263": ("Zimbabwe", "eu"),
}

DATA_ERROR = {0: "online", 503: "offline", 504: "timeout", None: "unknown"}

APP = [
    ("R8Oq3y0eSZSYdKccHlrQzT1ACCOUT9Gv", "1ve5Qk9GXfUhKAn1svnKwpAlxXkMarru"),
]


class AuthError(Exception):
    pass


class ResponseWaiter:
    """Class wait right sequences in response messages."""

    _waiters: Dict[str, asyncio.Future] = {}

    def _set_response(self, sequence: str, error: int) -> bool:
        if sequence not in self._waiters:
            return False

        try:
            # sometimes the error doesn't exists
            result = DATA_ERROR[error] if error in DATA_ERROR else f"E#{error}"
            self._waiters[sequence].set_result(result)
            return True
        except Exception:
            return False

    async def _wait_response(self, sequence: str, timeout: float):
        self._waiters[sequence] = fut = asyncio.get_event_loop().create_future()

        try:
            # limit future wait time
            await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            return "timeout"
        finally:
            # remove future from waiters
            _ = self._waiters.pop(sequence, None)

        # remove future from waiters and return result
        return fut.result()


# noinspection PyProtectedMember
class WebSocket:
    """Default asyncio.WebSocket keep-alive only incoming messages with heartbeats.
    This is helpful if messages from the server don't come very often.

    With this changes we also keep-alive outgoing messages with heartbeats.
    This is helpful if our messages to the server are not sent very often.
    """

    def __init__(self, ws: ClientWebSocketResponse):
        self._heartbeat: float = ws._heartbeat
        self._heartbeat_cb: asyncio.TimerHandle | None = None
        self.ws = ws

    def __aiter__(self):
        return self.ws

    async def __anext__(self):
        return await self.ws.__anext__()

    async def receive_json(self):
        return await self.ws.receive_json()

    async def send_json(self, data: dict):
        if self._heartbeat_cb:
            self._heartbeat_cb.cancel()
            self._heartbeat_cb = None

        self._heartbeat_cb = self.ws._loop.call_later(
            self._heartbeat, self.ws._send_heartbeat
        )

        await self.ws.send_json(data)


class XRegistryCloud(ResponseWaiter, XRegistryBase):
    auth: dict | None = None
    devices: dict[str, dict] = None
    last_ts: float = 0
    online: bool | None = None
    region: str = None

    task: asyncio.Task | None = None
    ws: WebSocket = None

    @property
    def host(self) -> str:
        return API[self.region]

    @property
    def ws_host(self) -> str:
        return WS[self.region]

    @property
    def headers(self) -> dict:
        return {"Authorization": "Bearer " + self.auth["at"]}

    @property
    def token(self) -> str:
        return self.region + ":" + self.auth["at"]

    @property
    def country_code(self) -> str:
        return self.auth["user"]["countryCode"]

    async def login(
        self, username: str, password: str, country_code: str = "+86", app: int = 0
    ) -> bool:
        if username == "token":
            self.region, token = password.split(":")
            return await self.login_token(token, 1)

        self.region = REGIONS[country_code][1]

        # https://coolkit-technologies.github.io/eWeLink-API/#/en/DeveloperGuideV2
        payload = {"password": password, "countryCode": country_code}
        if "@" in username:
            payload["email"] = username
        elif username.startswith("+"):
            payload["phoneNumber"] = username
        else:
            payload["phoneNumber"] = "+" + username

        appid, appsecret = APP[0]  # force using app=0

        # ensure POST payload and Sign payload will be same
        data = json.dumps(payload).encode()
        hex_dig = hmac.new(appsecret.encode(), data, hashlib.sha256).digest()

        headers = {
            "Authorization": "Sign " + base64.b64encode(hex_dig).decode(),
            "Content-Type": "application/json",
            "X-CK-Appid": appid,
        }
        r = await self.session.post(
            self.host + "/v2/user/login", data=data, headers=headers, timeout=5
        )
        resp = await r.json()

        # wrong default region
        if resp["error"] == 10004:
            self.region = resp["data"]["region"]
            r = await self.session.post(
                self.host + "/v2/user/login", data=data, headers=headers, timeout=5
            )
            resp = await r.json()

        if resp["error"] != 0:
            raise AuthError(resp["msg"])

        self.auth = resp["data"]
        self.auth["appid"] = appid

        return True

    async def login_token(self, token: str, app: int = 0) -> bool:
        appid = APP[app][0]
        headers = {"Authorization": "Bearer " + token, "X-CK-Appid": appid}
        r = await self.session.get(
            self.host + "/v2/user/profile", headers=headers, timeout=5
        )
        resp = await r.json()
        if resp["error"] != 0:
            raise AuthError(resp["msg"])

        self.auth = resp["data"]
        self.auth["at"] = token
        self.auth["appid"] = appid

        return True

    async def get_homes(self) -> dict:
        r = await self.session.get(
            self.host + "/v2/family", headers=self.headers, timeout=10
        )
        resp = await r.json()
        return {i["id"]: i["name"] for i in resp["data"]["familyList"]}

    async def get_devices(self, homes: list = None) -> list[dict]:
        devices = []
        for home in homes or [None]:
            r = await self.session.get(
                self.host + "/v2/device/thing",
                headers=self.headers,
                timeout=10,
                params={"num": 0, "familyid": home} if home else {"num": 0},
            )
            resp = await r.json()
            if resp["error"] != 0:
                raise Exception(resp["msg"])
            # item type: 1 - user device, 2 - shared device, 3 - user group,
            # 5 - share device (home)
            devices += [
                i["itemData"]
                for i in resp["data"]["thingList"]
                if "deviceid" in i["itemData"]  # skip groups
            ]
        return devices

    async def send(
        self,
        device: XDevice,
        params: dict = None,
        sequence: str = None,
        timeout: float = 5,
    ):
        """With params - send new state to device, without - request device
        state. With zero timeout - won't wait response.
        """
        log = f"{device['deviceid']} => Cloud4 | "
        if params:
            log += f"{params} | "

        # protect cloud from DDoS (it can break connection)
        while (delay := self.last_ts + 0.1 - time.time()) > 0:
            log += "DDoS | "
            await asyncio.sleep(delay)
        self.last_ts = time.time()

        if sequence is None:
            sequence = await self.sequence()
        log += sequence

        _LOGGER.debug(log)
        try:
            # https://coolkit-technologies.github.io/eWeLink-API/#/en/APICenterV2?id=websocket-update-device-status
            payload = {
                "action": "update" if params else "query",
                # we need to use device apikey bacause device may be shared from
                # another account
                "apikey": device["apikey"],
                # auth can be null (logged in from another place)
                "selfApikey": self.auth["user"]["apikey"],
                "deviceid": device["deviceid"],
                "params": params or [],
                "userAgent": "app",
                "sequence": sequence,
            }

            await self.ws.send_json(payload)

            if timeout:
                # wait for response with same sequence
                return await self._wait_response(sequence, timeout)
        except ConnectionResetError:
            return "offline"
        except Exception as e:
            _LOGGER.error(log, exc_info=e)
            return "E#???"

    def start(self, **kwargs):
        self.task = asyncio.create_task(self.run_forever(**kwargs))

    async def stop(self):
        if self.task:
            self.task.cancel()
            self.task = None

        self.set_online(None)

    def set_online(self, value: Optional[bool]):
        _LOGGER.debug(f"CLOUD change state old={self.online}, new={value}")
        if self.online == value:
            return
        self.online = value
        self.dispatcher_send(SIGNAL_CONNECTED)

    async def run_forever(self, **kwargs):
        fails = 0

        while not self.session.closed:
            if fails:
                self.set_online(False)

                # 15s 30s 1m 2m 4m 8m 16m 32m 64m
                delay = 15 * 2 ** min(fails - 1, 8)
                _LOGGER.debug(f"Cloud connection retrying in {delay} seconds")
                await asyncio.sleep(delay)

            if not self.auth:
                try:
                    assert await self.login(**kwargs)
                except:
                    fails += 1
                    continue

            if not await self.connect():
                fails += 1
                continue

            fails = 0
            self.set_online(True)

            try:
                msg: WSMessage
                async for msg in self.ws:
                    resp = json.loads(msg.data)
                    _ = asyncio.create_task(self._process_ws_msg(resp))
            except Exception as e:
                _LOGGER.warning("Cloud processing error", exc_info=e)

    async def connect(self) -> bool:
        try:
            # https://coolkit-technologies.github.io/eWeLink-API/#/en/APICenterV2?id=http-dispatchservice-app
            r = await self.session.get(self.ws_host, headers=self.headers)
            resp = await r.json()

            # we can use IP, but using domain because security
            ws = await self.session.ws_connect(
                f"wss://{resp['domain']}:{resp['port']}/api/ws", heartbeat=90
            )
            self.ws = WebSocket(ws)

            # https://coolkit-technologies.github.io/eWeLink-API/#/en/APICenterV2?id=websocket-handshake
            ts = time.time()
            payload = {
                "action": "userOnline",
                "at": self.auth["at"],
                "apikey": self.auth["user"]["apikey"],
                "appid": self.auth["appid"],
                "nonce": str(int(ts / 100)),
                "ts": int(ts),
                "userAgent": "app",
                "sequence": str(int(ts * 1000)),
                "version": 8,
            }
            await self.ws.send_json(payload)

            resp = await self.ws.receive_json()
            if (error := resp.get("error", 0)) != 0:
                # {'error': 406, 'reason': 'Authentication Failed'}
                # can happened when login from another place with same user/appid
                if error == 406:
                    _LOGGER.error(
                        "You logged in from another place, read more "
                        "https://github.com/AlexxIT/SonoffLAN#configuration"
                    )
                    # self.auth = None
                    return False

                raise Exception(resp)

            if (config := resp.get("config")) and config.get("hb"):
                self.ws._heartbeat = config.get("hbInterval")

            return True

        except ClientConnectorError as e:
            _LOGGER.warning(f"Cloud WS Connection error: {e}")

        except Exception as e:
            _LOGGER.error("Cloud WS exception", exc_info=e)

        return False

    async def _process_ws_msg(self, data: dict):
        if "action" not in data:
            # response on our command
            if "sequence" in data:
                self._set_response(data["sequence"], data.get("error"))

            # with params response on query, without - on update
            if "params" in data:
                self.dispatcher_send(SIGNAL_UPDATE, data)
            elif "config" in data:
                data["params"] = data.pop("config")
                self.dispatcher_send(SIGNAL_UPDATE, data)
            elif "error" in data:
                if data["error"] != 0:
                    _LOGGER.warning(f"Cloud ERROR: {data}")
            else:
                _LOGGER.warning(f"UNKNOWN cloud msg: {data}")

        elif data["action"] == "update":
            # new state from device
            self.dispatcher_send(SIGNAL_UPDATE, data)

        elif data["action"] == "sysmsg":
            # changed device online status
            self.dispatcher_send(SIGNAL_UPDATE, data)

        elif data["action"] == "reportSubDevice":
            # nothing useful: https://github.com/AlexxIT/SonoffLAN/issues/767
            pass

        else:
            _LOGGER.warning(f"UNKNOWN cloud msg: {data}")
