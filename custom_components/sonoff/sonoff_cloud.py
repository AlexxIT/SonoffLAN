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
from typing import Optional, Callable, List

from aiohttp import ClientSession, WSMsgType, ClientConnectorError

_LOGGER = logging.getLogger(__name__)

RETRY_DELAYS = [0, 15, 30, 60, 150, 300]


class EWeLinkCloud:
    _devices: dict = None
    _handlers = None
    _ws = None

    _baseurl = 'https://eu-api.coolkit.cc:8080/'
    _apikey = None
    _token = None

    _send_sequence = None
    _send_event = asyncio.Event()
    _send_result = False

    def __init__(self, session: ClientSession):
        self.session = session

    async def _send(self, mode: str, api: str, payload: dict) -> dict:
        """Send API request to Cloud Server.

        :param mode: `get`, `post` or `login`
        :param api: api url without host: `api/user/login`
        :param payload: url params for `get` mode or json body for `post` mode
        :return: response as dict
        """
        ts = int(time.time())
        payload.update({
            'appid': 'oeVkj2lYFGnJu5XUtWisfW4utiN4u9Mq',
            'nonce': str(ts),  # 8-digit random alphanumeric characters
            'ts': ts,  # 10-digit standard timestamp
            'version': 8
        })

        if mode == 'post':
            headers = {'Authorization': "Bearer " + self._token}
            r = await self.session.post(self._baseurl + api, json=payload,
                                        headers=headers)
        elif mode == 'login':
            hex_dig = hmac.new(b'6Nz4n0xA8s8qdxQf2GqurZj2Fs55FUvM',
                               json.dumps(payload).encode(),
                               digestmod=hashlib.sha256).digest()
            headers = {
                'Authorization': "Sign " + base64.b64encode(hex_dig).decode()
            }
            r = await self.session.post(self._baseurl + api, json=payload,
                                        headers=headers)
        elif mode == 'get':
            headers = {'Authorization': "Bearer " + self._token}
            r = await self.session.get(self._baseurl + api, params=payload,
                                       headers=headers)
        else:
            raise NotImplemented

        return await r.json()

    async def _process_msg(self, data: dict):
        deviceid = data.get('deviceid')
        if deviceid and 'params' in data:
            state = data['params']
            _LOGGER.debug(f"{deviceid} <= Cloud3 | {state}")

            for handler in self._handlers:
                handler(deviceid, state, data.get('seq'))

        elif deviceid:
            _LOGGER.debug(f"{deviceid} => Cloud0 | Force update")

            # respond for `'action': 'update'`
            if data['sequence'] == self._send_sequence:
                self._send_result = data['error'] == 0
                self._send_event.set()

            # Force update device actual status
            await self._ws.send_json({
                'action': 'query',
                'apikey': self._devices[deviceid]['apikey'],
                'selfApikey': self._apikey,
                'deviceid': deviceid,
                'params': [],
                'userAgent': 'app',
                'sequence': str(int(time.time() * 1000)),
                'ts': 0
            })

        else:
            _LOGGER.debug(f"Cloud msg: {data}")

    async def _connect(self, fails: int = 0):
        """Permanent connection loop to Cloud Servers."""
        resp = await self._send('post', 'dispatch/app', {'accept': 'ws'})
        url = f"wss://{resp['IP']}:{resp['port']}/api/ws"

        try:
            self._ws = await self.session.ws_connect(url, heartbeat=55,
                                                     ssl=False)
            fails = 0

            ts = time.time()
            payload = {
                'action': 'userOnline',
                'at': self._token,
                'apikey': self._apikey,
                'userAgent': 'app',
                'appid': 'oeVkj2lYFGnJu5XUtWisfW4utiN4u9Mq',
                'nonce': str(int(ts / 100)),
                'ts': int(ts),
                'version': 8,
                'sequence': str(int(ts * 1000))
            }
            await self._ws.send_json(payload)

            async for msg in self._ws:
                if msg.type == WSMsgType.TEXT:
                    resp = json.loads(msg.data)
                    await self._process_msg(resp)

                elif msg.type == WSMsgType.CLOSED:
                    _LOGGER.debug(f"Cloud WS Closed: {msg.data}")
                    break

                elif msg.type == WSMsgType.ERROR:
                    _LOGGER.debug(f"Cloud WS Error: {msg.data}")
                    break

        except ClientConnectorError as e:
            _LOGGER.error(f"Cloud WS Connection error: {e}")

        except Exception:
            _LOGGER.exception(f"Cloud WS exception")

        else:
            _LOGGER.debug("Cloud WS else")

        delay = RETRY_DELAYS[fails]
        _LOGGER.debug(f"Cloud WS retrying in {delay} seconds")
        await asyncio.sleep(delay)

        if fails + 1 < len(RETRY_DELAYS):
            fails += 1

        asyncio.create_task(self._connect(fails))

    async def login(self, username: str, password: str) -> bool:
        _LOGGER.debug("Login to Cloud Servers")

        # add a plus to the beginning of the phone number
        if '@' not in username and not username.startswith('+'):
            username = f"+{username}"

        pname = 'email' if '@' in username else 'phoneNumber'
        payload = {pname: username, 'password': password}
        resp = await self._send('login', 'api/user/login', payload)

        if 'region' not in resp:
            _LOGGER.error(f"Login error: {resp}")
            return False

        region = resp['region']
        if region != 'eu':
            self._baseurl = self._baseurl.replace('eu', region)
            _LOGGER.debug(f"Redirect to region: {region}")
            resp = await self._send('login', 'api/user/login', payload)

        self._apikey = resp['user']['apikey']
        self._token = resp['at']

        return True

    async def load_devices(self) -> Optional[list]:
        _LOGGER.debug("Load device list from Cloud Servers")
        assert self._token, "Login first"
        resp = await self._send('get', 'api/user/device', {'getTags': 1})
        return resp['devicelist'] if resp['error'] == 0 else None

    @property
    def started(self) -> bool:
        return self._ws is not None

    async def start(self, handlers: List[Callable], devices: dict = None):
        assert self._token, "Login first"
        self._handlers = handlers
        self._devices = devices

        asyncio.create_task(self._connect())

    async def send(self, deviceid: str, data: dict, sequence: str):
        """Send request to device.

        :param deviceid: example `1000abcdefg`
        :param data: example `{'switch': 'on'}`
        :param sequence: 13-digit standard timestamp, to verify uniqueness
        """
        device = self._devices[deviceid]
        if 'apikey' not in device:
            return

        payload = {
            'action': 'update',
            'deviceid': deviceid,
            # device apikey for shared devices
            'apikey': device['apikey'],
            'selfApikey': self._apikey,
            'userAgent': 'app',
            'sequence': sequence,
            'ts': 0,
            'params': data
        }
        _LOGGER.debug(f"{deviceid} => Cloud4 | {data}")
        await self._ws.send_json(payload)

        # wait for response with same sequence
        self._send_sequence = sequence
        self._send_event.clear()

        try:
            await asyncio.wait_for(self._send_event.wait(), 5)
        except asyncio.TimeoutError:
            return False

        return self._send_result
