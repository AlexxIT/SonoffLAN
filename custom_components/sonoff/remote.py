import asyncio

from homeassistant.components.remote import RemoteEntity, ATTR_DELAY_SECS, \
    DEFAULT_DELAY_SECS
from homeassistant.const import ATTR_COMMAND

from .binary_sensor import XRemoteSensor, XRemoteSensorOff
from .button import XRemoteButton
from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, RemoteEntity)])
    )


# noinspection PyAbstractClass
class XRemote(XEntity, RemoteEntity):
    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)

        self.childs = {}
        self.params = {"cmd", "arming"}
        self.ts = None

        for remote in device.get("tags", {}).get("zyx_info", []):
            for remote2 in remote["buttonName"]:
                if remote["remote_type"] == "6":
                    child = XRemoteSensor(ewelink, device, remote)
                else:
                    child = XRemoteButton(ewelink, device, remote2)
                self.childs[child.channel] = child

        for name, sensor in XRemoteSensorOff.sensors.items():
            ch = next(k for k, v in self.childs.items() if v.name == name)
            # replace entity sensor to non entity remote chlid
            self.childs[ch] = XRemoteSensorOff(ch, name, sensor)

        ewelink.dispatcher_send(SIGNAL_ADD_ENTITIES, self.childs.values())

    def set_state(self, params: dict):
        # skip full cloud state update
        if "init" in params:
            return

        for param, ts in params.items():
            if not param.startswith("rfTrig"):
                continue

            # skip first msg from LAN because it sent old trigger event with
            # local discovery and only LAN sends arming param
            if self.ts is None and params.get("arming"):
                self.ts = ts
                return

            # skip same cmd from local and cloud
            if ts == self.ts:
                return

            self.ts = ts

            child = self.childs.get(param[6:])
            if not child:
                return
            child.internal_update(ts)

            self._attr_extra_state_attributes = data = {
                "command": int(child.channel), "name": child.name,
                "entity_id": self.entity_id, "ts": ts,
            }
            self.hass.bus.async_fire("sonoff.remote", data)

    async def async_send_command(self, command, **kwargs):
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        for i, channel in enumerate(command):
            if i:
                await asyncio.sleep(delay)

            # transform button name to channel number
            if not channel.isdigit():
                channel = next(
                    k for k, v in self.childs.items() if v.name == channel
                )

            # cmd param for local and for cloud mode
            await self.ewelink.send(self.device, {
                "cmd": "transmit", "rfChl": int(channel)
            })

    async def async_learn_command(self, **kwargs):
        command = kwargs[ATTR_COMMAND]
        # cmd param for local and for cloud mode
        await self.ewelink.send(self.device, {
            "cmd": "capture", "rfChl": int(command[0])
        })
