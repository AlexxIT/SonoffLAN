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

import requests

from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad
from Crypto.Util.Padding import unpad

_LOGGER = logging.getLogger(__name__)


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


def load_devices(username: str, password: str):
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
    r = requests.post('https://eu-api.coolkit.cc:8080/api/user/login',
                      headers=headers, json=params)
    resp = r.json()

    if 'region' not in resp:
        info = 'email' if '@' in username else 'phone'
        _LOGGER.error(f"Login with {info} error: {resp}")
        return None

    region = resp['region']
    if region != 'eu':
        _LOGGER.debug(f"Redirect to region: {region}")
        r = requests.post(
            f"https://{region}-api.coolkit.cc:8080/api/user/login",
            headers=headers, json=params)
        resp = r.json()

    headers = {'Authorization': "Bearer " + resp['at']}
    params = _params(apiKey=resp['user']['apikey'], lang='en', getTags=1)
    r = requests.get(f"https://{region}-api.coolkit.cc:8080/api/user/device",
                     headers=headers, params=params)
    resp = r.json()

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


SWITCH = 'switch'
SWITCH2 = ['switch', 'switch']
SWITCH3 = ['switch', 'switch', 'switch']
SWITCH4 = ['switch', 'switch', 'switch', 'switch']
SWITCHX = ['switch']

UIIDS = {
    1: SWITCH,
    2: SWITCH2,
    3: SWITCH3,
    4: SWITCH4,
    5: SWITCH,
    6: SWITCH,
    7: SWITCH2,
    8: SWITCH3,
    9: SWITCH4,
    28: 'remote',  # Sonoff RF Brigde 433
    29: SWITCH2,
    30: SWITCH3,
    31: SWITCH4,
    44: 'light',  # Sonoff D1
    77: SWITCHX,  # Sonoff Micro
    78: SWITCHX,
    81: SWITCH,
    82: SWITCH2,
    83: SWITCH3,
    84: SWITCH4,
    107: SWITCHX
}

TYPES = {
    'plug': SWITCH,
    'enhanced_plug': SWITCH,  # Sonoff Pow R2?
    'th_plug': SWITCH,  # Sonoff TH?
    'strip': SWITCH4,
    'light': 'light',
    'rf': 'remote'
}


def guess_device_class(config: dict):
    """Get device_class from uiid (from eWeLink Servers) or from zeroconf type.
    """
    uiid = config.get('uiid')
    type_ = config.get('type')
    return UIIDS.get(uiid) or TYPES.get(type_)
