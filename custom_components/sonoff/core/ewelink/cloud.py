"""
https://coolkit-technologies.github.io/apiDocs/#/en/APICenter
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import List

from aiohttp import ClientConnectorError, WSMessage, WSMsgType, \
    ClientWebSocketResponse

from .base import XRegistryBase, SIGNAL_CONNECTED, SIGNAL_UPDATE

_LOGGER = logging.getLogger(__name__)

RETRY_DELAYS = [0, 15, 60, 5 * 60, 15 * 60, 60 * 60]

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

DATA_ERROR = {
    0: 'online',
    503: 'offline',
    504: 'timeout',
    None: 'unknown'
}


class AuthError(Exception):
    pass


class ResponseWaiter:
    """Class wait right sequences in response messages."""
    _waiters = {}

    async def _set_response(self, sequence: str, error: int):
        # sometimes the error doesn't exists
        result = DATA_ERROR[error] if error in DATA_ERROR else f"E#{error}"
        # set future result
        self._waiters[sequence].set_result(result)

    async def _wait_response(self, sequence: str, timeout: int):
        self._waiters[sequence] = asyncio.get_event_loop().create_future()

        try:
            # limit future wait time
            await asyncio.wait_for(self._waiters[sequence], timeout)
        except asyncio.TimeoutError:
            # remove future from waiters, in very rare cases, we can send two
            # commands with the same sequence
            self._waiters.pop(sequence, None)
            return 'timeout'

        # remove future from waiters and return result
        return self._waiters.pop(sequence).result()


class XRegistryCloud(ResponseWaiter, XRegistryBase):
    # appid = 'oeVkj2lYFGnJu5XUtWisfW4utiN4u9Mq'
    # appsecret = '6Nz4n0xA8s8qdxQf2GqurZj2Fs55FUvM'
    appid = "4s1FXKC9FaGfoqXhmXSJneb3qcm1gOak"
    appsecret = "oKvCM06gvwkRbfetd6qWRrbC3rFrbIpV"

    auth: dict = None
    devices: dict = None
    last_ts = 0
    online = False
    region = "eu"

    task: asyncio.Task = None
    ws: ClientWebSocketResponse = None

    @property
    def host(self) -> str:
        return API[self.region]

    @property
    def ws_host(self) -> str:
        return WS[self.region]

    @property
    def headers(self) -> dict:
        return {"Authorization": "Bearer " + self.auth["at"]}

    async def login(self, username: str, password: str) -> bool:
        # https://coolkit-technologies.github.io/eWeLink-API/#/en/DeveloperGuideV2
        payload = {
            "password": password,
            "countryCode": "+86",
        }
        if "@" in username:
            payload["email"] = username
        elif username.startswith("+"):
            payload["phoneNumber"] = username
        else:
            payload["phoneNumber"] = "+" + username

        hex_dig = hmac.new(
            self.appsecret.encode(),
            json.dumps(payload).encode(),
            digestmod=hashlib.sha256
        ).digest()

        headers = {
            "Authorization": "Sign " + base64.b64encode(hex_dig).decode(),
            "X-CK-Appid": self.appid,
        }
        r = await self.session.post(
            self.host + "/v2/user/login", json=payload, headers=headers,
            timeout=10
        )
        resp = await r.json()

        # wrong default region
        if resp["error"] == 10004:
            self.region = resp["data"]["region"]
            r = await self.session.post(
                self.host + "/v2/user/login", json=payload, headers=headers,
                timeout=10
            )
            resp = await r.json()

        if resp["error"] != 0:
            raise AuthError(resp["msg"])

        self.auth = resp["data"]

        return True

    async def get_devices(self) -> List[dict]:
        r = await self.session.get(
            self.host + "/v2/device/thing", headers=self.headers,
            timeout=10
        )
        resp = await r.json()
        return [i["itemData"] for i in resp["data"]["thingList"]]

    async def send(
            self, device: dict, params: dict = None, sequence: str = None,
            timeout: int = 5
    ):
        """With params - send new state to device, without - request device
        state.
        """
        # protect cloud from DDoS (it can break connection)
        while time.time() - self.last_ts < 0.1:
            _LOGGER.debug("Protect cloud from DDoS")
            await asyncio.sleep(0.1)
            sequence = None

        self.last_ts = time.time()

        if sequence is None:
            sequence = str(int(self.last_ts * 1000))

        # https://coolkit-technologies.github.io/eWeLink-API/#/en/APICenterV2?id=websocket-update-device-status
        payload = {
            "action": "update" if params else "query",
            # we need to use device apikey bacause device may be shared from
            # another account
            "apikey": device["apikey"],
            "selfApikey": self.auth["user"]["apikey"],
            "deviceid": device['deviceid'],
            "params": params or [],
            "userAgent": "app",
            "sequence": sequence,
        }

        log = f"{device['deviceid']} => Cloud4 | {params} | {sequence}"
        _LOGGER.debug(log)
        try:
            await self.ws.send_json(payload)

            # wait for response with same sequence
            return await self._wait_response(sequence, timeout)

        except:
            _LOGGER.exception(log)
            return 'E#???'

    def start(self):
        self.task = asyncio.create_task(self._connect())

    async def stop(self):
        self.online = False
        if self.task:
            self.task.cancel()

    async def _connect(self, fails: int = 0):
        try:
            # https://coolkit-technologies.github.io/eWeLink-API/#/en/APICenterV2?id=http-dispatchservice-app
            r = await self.session.get(self.ws_host, headers=self.headers)
            resp = await r.json()

            # we can use IP, but using domain because security
            self.ws = await self.session.ws_connect(
                f"wss://{resp['domain']}:{resp['port']}/api/ws", heartbeat=145
            )

            # https://coolkit-technologies.github.io/eWeLink-API/#/en/APICenterV2?id=websocket-handshake
            ts = time.time()
            payload = {
                "action": "userOnline",
                "at": self.auth["at"],
                "apikey": self.auth["user"]["apikey"],
                "appid": self.appid,
                "nonce": str(int(ts / 100)),
                "ts": int(ts),
                "userAgent": "app",
                "sequence": str(int(ts * 1000)),
                "version": 8,
            }
            await self.ws.send_json(payload)

            msg: WSMessage = await self.ws.receive()
            resp = json.loads(msg.data) if msg.data else None
            assert resp["error"] == 0, resp

            _LOGGER.debug("Connected to cloud")

            fails = 0

            self.online = True
            self.dispatcher_send(SIGNAL_CONNECTED)

            async for msg in self.ws:
                assert msg.type == WSMsgType.TEXT, msg.type
                resp = json.loads(msg.data)
                await self._process_ws_msg(resp)

        except ClientConnectorError as e:
            _LOGGER.error(f"Cloud WS Connection error", exc_info=e)

        except Exception as e:
            _LOGGER.error(f"Cloud WS exception", exc_info=e)

        self.online = False
        self.dispatcher_send(SIGNAL_CONNECTED)

        # stop reconnection because session closed
        if self.session.closed:
            return

        delay = RETRY_DELAYS[min(fails, len(RETRY_DELAYS) - 1)]
        _LOGGER.debug(f"Cloud connection retrying in {delay} seconds")
        await asyncio.sleep(delay)

        self.task = asyncio.create_task(self._connect(fails + 1))

    async def _process_ws_msg(self, data: dict):
        _LOGGER.debug(data)

        # deviceid = data.get('deviceid')
        # device = self.devices[deviceid]
        if "action" not in data:
            # response on our command
            await self._set_response(data["sequence"], data["error"])

            # with params response on query, without - on update
            if "params" in data:
                self.dispatcher_send(SIGNAL_UPDATE, data)
            elif "config" in data:
                data["params"] = data.pop("config")
                self.dispatcher_send(SIGNAL_UPDATE, data)
            elif data["error"] == 0:
                # Force update device actual status
                asyncio.create_task(self.send(data))

        elif data["action"] in "update":
            # new state from device
            self.dispatcher_send(SIGNAL_UPDATE, data)

        elif data["action"] == "sysmsg":
            # changed device online status
            self.dispatcher_send(SIGNAL_UPDATE, data)
