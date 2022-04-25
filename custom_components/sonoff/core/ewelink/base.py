import time
from typing import Callable, Dict, List

from aiohttp import ClientSession

SIGNAL_CONNECTED = "connected"
SIGNAL_UPDATE = "update"


class XRegistryBase:
    dispatcher: Dict[str, List[Callable]] = None
    _sequence: int = 0

    def __init__(self, session: ClientSession):
        self.dispatcher = {}
        self.session = session

    @staticmethod
    def sequence() -> str:
        """Return sequnce counter in ms. Always unique."""
        t = int(time.time()) * 1000
        if t > XRegistryBase._sequence:
            XRegistryBase._sequence = t
        else:
            XRegistryBase._sequence += 1
        return str(XRegistryBase._sequence)

    def dispatcher_connect(self, signal: str, target: Callable):
        targets = self.dispatcher.setdefault(signal, [])
        if target not in targets:
            targets.append(target)

    def dispatcher_send(self, signal: str, *args, **kwargs):
        if not self.dispatcher.get(signal):
            return
        for handler in self.dispatcher[signal]:
            handler(*args, **kwargs)
