from typing import Callable, Dict, List

from aiohttp import ClientSession

SIGNAL_CONNECTED = "connected"
SIGNAL_UPDATE = "update"


class XRegistryBase:
    dispatcher: Dict[str, List[Callable]] = None

    def __init__(self, session: ClientSession):
        self.dispatcher = {}
        self.session = session

    def dispatcher_connect(self, signal: str, target: Callable):
        targets = self.dispatcher.setdefault(signal, [])
        if target not in targets:
            targets.append(target)

    def dispatcher_send(self, signal: str, *args, **kwargs):
        if not self.dispatcher.get(signal):
            return
        for handler in self.dispatcher[signal]:
            handler(*args, **kwargs)
