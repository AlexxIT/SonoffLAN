import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from base64 import b64decode
from base64 import b64encode
from typing import Optional

from aiohttp import ClientSession

from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad
from Crypto.Util.Padding import unpad

_LOGGER = logging.getLogger(__name__)


def init_zeroconf_singleton(hass):
    """Generate only one Zeroconf. Component must be loaded before Zeroconf."""
    from homeassistant.components import zeroconf
    if isinstance(zeroconf.Zeroconf, type):
        def zeroconf_singleton():
            if 'zeroconf' not in hass.data:
                from zeroconf import Zeroconf
                _LOGGER.debug("Generate zeroconf singleton")
                hass.data['zeroconf'] = Zeroconf()
            else:
                _LOGGER.debug("Use zeroconf singleton")
            return hass.data['zeroconf']

        _LOGGER.debug("Init zeroconf singleton")
        zeroconf.Zeroconf = zeroconf_singleton


def _params(**kwargs):
    """Generate params for sonoff API. Pretend mobile application."""
    return {
        **kwargs,
        'version': 6,
        'ts': int(time.time()),
        'nonce': int(time.time() * 100000),
        'appid': 'oeVkj2lYFGnJu5XUtWisfW4utiN4u9Mq',
        'imei': str(uuid.uuid4()),
        'os': 'android',
        'model': '',
        'romVersion': '',
        'appVersion': '3.12.0'
    }


def load_cache(filename: str) -> Optional[dict]:
    """Load device list from file."""
    if os.path.isfile(filename):
        with open(filename, 'rt', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_cache(filename: str, data: dict):
    """Save device list to file."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


async def load_devices(username: str, password: str, session: ClientSession):
    """Load device list from ewelink servers."""

    # add a plus to the beginning of the phone number
    if '@' not in username and not username.startswith('+'):
        username = f"+{username}"

    params = _params(email=username, password=password) \
        if '@' in username else \
        _params(phoneNumber=username, password=password)

    hex_dig = hmac.new(b'6Nz4n0xA8s8qdxQf2GqurZj2Fs55FUvM',
                       json.dumps(params).encode(),
                       digestmod=hashlib.sha256).digest()
    headers = {'Authorization': "Sign " + base64.b64encode(hex_dig).decode()}

    r = await session.post('https://eu-api.coolkit.cc:8080/api/user/login',
                           headers=headers, json=params)
    resp = await r.json()

    if 'region' not in resp:
        info = 'email' if '@' in username else 'phone'
        _LOGGER.error(f"Login with {info} error: {resp}")
        return None

    region = resp['region']
    if region != 'eu':
        _LOGGER.debug(f"Redirect to region: {region}")
        r = await session.post(
            f"https://{region}-api.coolkit.cc:8080/api/user/login",
            headers=headers, json=params)
        resp = await r.json()

    headers = {'Authorization': "Bearer " + resp['at']}
    params = _params(apiKey=resp['user']['apikey'], lang='en', getTags=1)
    r = await session.get(
        f"https://{region}-api.coolkit.cc:8080/api/user/device",
        headers=headers, params=params)
    resp = await r.json()

    if resp['error'] == 0:
        return resp['devicelist']

    return None


def encrypt(payload: dict, devicekey: str):
    devicekey = devicekey.encode('utf-8')

    hash_ = MD5.new()
    hash_.update(devicekey)
    key = hash_.digest()

    iv = get_random_bytes(16)
    plaintext = json.dumps(payload['data']).encode('utf-8')

    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    padded = pad(plaintext, AES.block_size)
    ciphertext = cipher.encrypt(padded)

    payload['encrypt'] = True
    payload['iv'] = b64encode(iv).decode('utf-8')
    payload['data'] = b64encode(ciphertext).decode('utf-8')

    return payload


def decrypt(payload: dict, devicekey: str):
    try:
        devicekey = devicekey.encode('utf-8')

        hash_ = MD5.new()
        hash_.update(devicekey)
        key = hash_.digest()

        encoded = ''.join([payload[f'data{i}'] for i in range(1, 4, 1)
                           if f'data{i}' in payload])

        cipher = AES.new(key, AES.MODE_CBC, iv=b64decode(payload['iv']))
        ciphertext = b64decode(encoded)
        padded = cipher.decrypt(ciphertext)
        return unpad(padded, AES.block_size)

    except:
        return None


UIIDS = {}
TYPES = {}


def init_device_class(default_class: str = 'switch'):
    switch1 = default_class
    switch2 = [default_class, default_class]
    switch3 = [default_class, default_class, default_class]
    switch4 = [default_class, default_class, default_class, default_class]
    switchx = [default_class]

    UIIDS.update({
        1: switch1,
        2: switch2,
        3: switch3,
        4: switch4,
        5: switch1,
        6: switch1,
        7: switch2,
        8: switch3,
        9: switch4,
        28: 'remote',  # Sonoff RF Brigde 433
        29: switch2,
        30: switch3,
        31: switch4,
        34: ['light', {'fan': [2, 3, 4]}],  # Sonoff iFan02 and iFan03
        44: 'light',  # Sonoff D1
        77: switchx,  # Sonoff Micro
        78: switchx,
        81: switch1,
        82: switch2,
        83: switch3,
        84: switch4,
        107: switchx
    })

    TYPES.update({
        'plug': switch1,  # Basic, Mini
        'enhanced_plug': switch1,  # Sonoff Pow R2?
        'th_plug': switch1,  # Sonoff TH?
        'strip': switch4,  # 4CH Pro R2, Micro!, iFan02!
        'light': 'light',  # D1
        'rf': 'remote',  # RF Bridge 433
        'fan_light': ['light', 'fan'],  # iFan03
    })


def guess_device_class(config: dict):
    """Get device_class from uiid (from eWeLink Servers) or from zeroconf type.

    Sonoff iFan02 and iFan03 both have uiid 34. But different types (strip and
    fan_light) and different local API for each type. Without uiid iFan02 will
    be displayed as 4 switches.
    """
    uiid = config.get('uiid')
    type_ = config.get('type')
    return UIIDS.get(uiid) or TYPES.get(type_)
