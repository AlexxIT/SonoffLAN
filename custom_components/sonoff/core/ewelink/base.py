import asyncio
import time
from typing import Callable, Optional, TypedDict

from aiohttp import ClientSession

SIGNAL_CONNECTED = "connected"
SIGNAL_UPDATE = "update"


class XDevice(TypedDict, total=False):
    deviceid: str
    extra: dict
    name: str
    params: dict

    brandName: Optional[str]
    productModel: Optional[str]

    online: Optional[bool]  # required for cloud
    apikey: Optional[str]  # required for cloud

    local: Optional[bool]  # required for local
    localtype: Optional[str]  # exist for local DIY device type
    host: Optional[str]  # required for local
    devicekey: Optional[str]  # required for encrypted local devices (not DIY)

    local_ts: Optional[float]  # time of last local msg from device
    params_bulk: Optional[dict]  # helper for send_bulk commands
    pow_ts: Optional[float]  # required for pow devices with cloud connection

    parent: Optional[dict]


class XRegistryBase:
    dispatcher: dict[str, list[Callable]] = None
    _sequence: int = 0
    _sequence_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, session: ClientSession):
        self.dispatcher = {}
        self.session = session

    @staticmethod
    async def sequence() -> str:
        """Return sequnce counter in ms. Always unique."""
        t = time.time_ns() // 1_000_000
        async with XRegistryBase._sequence_lock:
            if t > XRegistryBase._sequence:
                XRegistryBase._sequence = t
            else:
                XRegistryBase._sequence += 1
            return str(XRegistryBase._sequence)

    def dispatcher_connect(self, signal: str, target: Callable) -> Callable:
        targets = self.dispatcher.setdefault(signal, [])
        if target not in targets:
            targets.append(target)
        return lambda: targets.remove(target)

    def dispatcher_send(self, signal: str, *args, **kwargs):
        if not self.dispatcher.get(signal):
            return
        for handler in self.dispatcher[signal]:
            handler(*args, **kwargs)

    async def dispatcher_wait(self, signal: str):
        event = asyncio.Event()
        disconnect = self.dispatcher_connect(signal, lambda: event.set())
        await event.wait()
        disconnect()
