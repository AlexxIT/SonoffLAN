from homeassistant.components.light import *
from homeassistant.util import color

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import XRegistry, SIGNAL_ADD_ENTITIES


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, LightEntity)])
    )


# noinspection PyAbstractClass, UIID 22
class XFanLight(XEntity, LightEntity):
    params = {"switches", "light"}
    uid = "1"  # backward compatibility

    def set_state(self, params: dict):
        if "switches" in params:
            params = next(i for i in params["switches"] if i["outlet"] == 0)
            self._attr_is_on = params["switch"] == "on"
        else:
            self._attr_is_on = params["light"] == "on"

    async def async_turn_on(self, **kwargs):
        params = {"switches": [{"outlet": 0, "switch": "on"}]}
        params_lan = {"light": "on"}
        await self.ewelink.send(self.device, params, params_lan)

    async def async_turn_off(self):
        params = {"switches": [{"outlet": 0, "switch": "off"}]}
        params_lan = {"light": "off"}
        await self.ewelink.send(self.device, params, params_lan)


# noinspection PyAbstractClass, UIID 22
class XLightB1(XEntity, LightEntity):
    params = {"state", "zyx_mode", "channel0", "channel2"}

    _attr_min_mireds = 1
    _attr_max_mireds = 3
    _attr_supported_features = (
            SUPPORT_BRIGHTNESS | SUPPORT_COLOR | SUPPORT_COLOR_TEMP
    )

    def set_state(self, params: dict):
        if 'state' in params:
            self._attr_is_on = params['state'] == 'on'

        # guess the mode if it is not in the data
        if 'zyx_mode' in params:
            mode = params['zyx_mode']
        elif 'channel0' in params:
            mode = 1
        elif 'channel2' in params:
            mode = 2
        else:
            mode = None

        if mode == 1:
            # from 25 to 255
            cold = int(params['channel0'])
            warm = int(params['channel1'])
            if warm == 0:
                self._attr_color_temp = 1
            elif cold == warm:
                self._attr_color_temp = 2
            elif cold == 0:
                self._attr_color_temp = 3
            br = round((max(cold, warm) - 25) / (255 - 25) * 255)
            # from 1 to 100
            self._attr_brightness = max(br, 1)
            self._attr_hs_color = None

        elif mode == 2:
            self._attr_hs_color = color.color_RGB_to_hs(
                int(params['channel2']),
                int(params['channel3']),
                int(params['channel4'])
            )

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_COLOR_TEMP in kwargs or ATTR_BRIGHTNESS in kwargs:
            if ATTR_BRIGHTNESS in kwargs:
                self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

            if ATTR_COLOR_TEMP in kwargs:
                self._attr_color_temp = kwargs[ATTR_COLOR_TEMP]

            ch = str(25 + round(self._attr_brightness / 255 * (255 - 25)))
            # type send no matter
            payload = {
                'zyx_mode': 1,
                'channel2': '0',
                'channel3': '0',
                'channel4': '0'
            }
            if self._attr_color_temp == 1:
                payload.update({'channel0': ch, 'channel1': '0'})
            elif self._attr_color_temp == 2:
                payload.update({'channel0': ch, 'channel1': ch})
            elif self._attr_color_temp == 3:
                payload.update({'channel0': '0', 'channel1': ch})

        elif ATTR_HS_COLOR in kwargs:
            rgb = color.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
            # type send no matter
            payload = {
                'zyx_mode': 2,
                'channel0': '0',
                'channel1': '0',
                'channel2': str(rgb[0]),
                'channel3': str(rgb[1]),
                'channel4': str(rgb[2]),
            }

        else:
            payload = {'state': 'on'}

        await self.ewelink.send(self.device, payload)

    async def async_turn_off(self, **kwargs) -> None:
        await self.ewelink.send(self.device, {'state': 'off'})


# noinspection PyAbstractClass, UIID 25
class XDiffuserLight(XEntity, LightEntity):
    params = {"lightswitch", "lightbright", "lightmode", "lightRcolor"}

    _attr_brightness = 0
    # TODO: names for 1 and 2
    _attr_effect_list = ["Color Light", "RGB Color", "Night Light"]

    def set_state(self, params: dict):
        if 'lightswitch' in params:
            self._attr_is_on = params['lightswitch'] == 1

        if 'lightbright' in params:
            # brightness from 0 to 100
            self._attr_brightness = max(round(params['lightbright'] * 2.55), 1)

        if 'lightmode' in params:
            mode = params['lightmode']
            if mode == 1:
                self._attr_supported_features = SUPPORT_EFFECT
            elif mode == 2:
                self._attr_supported_features = \
                    SUPPORT_BRIGHTNESS | SUPPORT_COLOR | SUPPORT_EFFECT
            elif mode == 3:
                self._attr_supported_features = \
                    SUPPORT_BRIGHTNESS | SUPPORT_EFFECT

        if 'lightRcolor' in params:
            self._attr_hs_color = color.color_RGB_to_hs(
                params['lightRcolor'], params['lightGcolor'],
                params['lightBcolor']
            )

    async def async_turn_on(self, **kwargs) -> None:
        payload = {}

        if ATTR_EFFECT in kwargs:
            mode = self._attr_effect_list.index(kwargs[ATTR_EFFECT]) + 1
            payload['lightmode'] = mode

            if mode == 2 and ATTR_HS_COLOR not in kwargs:
                kwargs[ATTR_HS_COLOR] = self._attr_hs_color

        if ATTR_BRIGHTNESS in kwargs:
            br = max(round(kwargs[ATTR_BRIGHTNESS] / 2.55), 1)
            payload['lightbright'] = br

        if ATTR_HS_COLOR in kwargs:
            rgb = color.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
            payload.update({
                'lightmode': 2, 'lightRcolor': rgb[0],
                'lightGcolor': rgb[1], 'lightBcolor': rgb[2]
            })

        if not kwargs:
            payload['lightswitch'] = 1

        await self.ewelink.send(self.device, payload)

    async def async_turn_off(self, **kwargs) -> None:
        await self.ewelink.send(self.device, {'lightswitch': 0})


# noinspection PyAbstractClass, UIID 36
class XDimmer(XEntity, LightEntity):
    params = {"switch", "bright"}

    _attr_brightness = 0
    _attr_supported_features = SUPPORT_BRIGHTNESS

    def set_state(self, params: dict):
        if 'switch' in params:
            self._attr_is_on = params['switch'] == 'on'

        if 'bright' in params:
            # from 10 to 100 => 1 .. 255
            br = round((params['bright'] - 10) / (100 - 10) * 255)
            self._attr_brightness = max(br, 1)

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        br = 10 + round(self._attr_brightness / 255 * (100 - 10))
        await self.ewelink.send(self.device, {'switch': 'on', 'bright': br})

    async def async_turn_off(self, **kwargs) -> None:
        await self.ewelink.send(self.device, {"switch": "off"})


# noinspection PyAbstractClass, UIID 44
class XLightD1(XDimmer):
    params = {"switch", "brightness"}

    def set_state(self, params: dict):
        if 'switch' in params:
            self._attr_is_on = params['switch'] == 'on'

        if 'brightness' in params:
            self._attr_brightness = max(round(params['brightness'] * 2.55), 1)

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        br = max(round(self._attr_brightness / 2.55), 1)
        # cmd param only for local mode, no need for cloud
        await self.ewelink.send(self.device, {
            'cmd': 'dimmable', 'switch': 'on', 'brightness': br, 'mode': 0
        })


# noinspection PyAbstractClass, UIID 57
class XLight57(XDimmer):
    params = {"state", "channel0"}

    def set_state(self, params: dict):
        if 'state' in params:
            self._attr_is_on = params['state'] == 'on'

        if 'channel0' in params:
            # from 25 to 255 => 1 .. 255
            br = int(params['channel0'])
            self._attr_brightness = round(
                1.0 + (br - 25.0) / (255.0 - 25.0) * 254.0
            )

    async def async_turn_on(self, **kwargs) -> None:
        payload = {'state': 'on'}

        if ATTR_BRIGHTNESS in kwargs:
            br = kwargs[ATTR_BRIGHTNESS]
            payload['channel0'] = str(round(
                25.0 + (br - 1.0) * (255.0 - 25.0) / 254.0
            ))

        await self.ewelink.send(self.device, payload)

    async def async_turn_off(self, **kwargs) -> None:
        await self.ewelink.send(self.device, {'state': 'off'})


# noinspection PyAbstractClass, UIID 59
class XLightLED(XDimmer):
    _attr_effect_list = [
        "Colorful", "Colorful Gradient", "Colorful Breath", "DIY Gradient",
        "DIY Pulse", "DIY Breath", "DIY Strobe", "RGB Gradient",
        "DIY Gradient", "RGB Breath", "RGB Strobe", "Music"
    ]
    _attr_supported_features = (
            SUPPORT_BRIGHTNESS | SUPPORT_COLOR | SUPPORT_EFFECT
    )

    def set_state(self, params: dict):
        if 'switch' in params:
            self._attr_is_on = params['switch'] == 'on'

        if 'bright' in params:
            # sonoff brightness from 1 to 100
            self._attr_brightness = max(round(params['bright'] * 2.55), 1)

        if 'colorR' in params and 'colorG' in params and 'colorB':
            self._attr_hs_color = color.color_RGB_to_hs(
                params['colorR'], params['colorG'], params['colorB']
            )

        if 'mode' in params:
            self._attr_effect = self._attr_effect_list[params['mode'] - 1]

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_EFFECT in kwargs:
            mode = self._attr_effect_list.index(kwargs[ATTR_EFFECT]) + 1
            payload = {'switch': 'on', 'mode': mode}

        elif ATTR_BRIGHTNESS in kwargs or ATTR_HS_COLOR in kwargs:
            payload = {'mode': 1}

            if ATTR_BRIGHTNESS in kwargs:
                br = max(round(kwargs[ATTR_BRIGHTNESS] / 2.55), 1)
                payload['bright'] = br

            if ATTR_HS_COLOR in kwargs:
                rgb = color.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
                payload.update({
                    'colorR': rgb[0], 'colorG': rgb[1], 'colorB': rgb[2],
                    'light_type': 1
                })

        else:
            payload = {'switch': 'on'}

        await self.ewelink.send(self.device, payload)


B02_MODE_PAYLOADS = {
    "nightLight": {"br": 5, "ct": 0},
    "read": {"br": 50, "ct": 0},
    "computer": {"br": 20, "ct": 255},
    "bright": {"br": 100, "ct": 255},
}


# noinspection PyAbstractClass, UIID 103
class XLightB02(XDimmer):
    params = {"switch", "ltype"}

    # FS-1, B02-F-A60 and other
    _attr_max_mireds: int = int(1000000 / 2200)
    _attr_min_mireds: int = int(1000000 / 6500)

    # names from eWeLink API
    _attr_effect_list = ["white", "nightLight", "read", "computer", "bright"]
    _attr_supported_features = (
            SUPPORT_BRIGHTNESS | SUPPORT_COLOR_TEMP | SUPPORT_EFFECT
    )

    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)

        model = device.get("productModel")
        if model == "B02-F-ST64":
            self._attr_min_mireds = int(1000000 / 5000)
            self._attr_max_mireds = int(1000000 / 1800)
        elif model == "QMS-2C-CW":
            self._attr_min_mireds = int(1000000 / 6500)
            self._attr_max_mireds = int(1000000 / 2700)

    def set_state(self, params: dict):
        if "switch" in params:
            self._attr_is_on = params["switch"] == "on"

        if "ltype" not in params:
            return

        self._attr_effect = params["ltype"]

        state = params[self._attr_effect]
        if "br" in state:
            # 1..100 => 1..255
            br = state["br"]
            self._attr_brightness = round(
                1.0 + (br - 1.0) / (100.0 - 1.0) * 254.0
            )

        if "ct" in state:
            # 0..255 => Mireds..
            ct = min(255, max(0, state["ct"]))
            self._attr_color_temp = round(
                self._attr_max_mireds - ct / 255.0 *
                (self._attr_max_mireds - self._attr_min_mireds)
            )

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs or ATTR_COLOR_TEMP in kwargs:
            mode = "white"
        elif ATTR_EFFECT in kwargs:
            mode = kwargs[ATTR_EFFECT]
        else:
            mode = self._attr_effect

        if mode == "white":
            br = kwargs.get(ATTR_BRIGHTNESS) or self._attr_brightness or 1
            ct = kwargs.get(ATTR_COLOR_TEMP) or self._attr_color_temp or 153
            # Adjust to the dynamic range of the device.
            ct = min(self._attr_max_mireds, max(self._attr_min_mireds, ct))
            payload = {
                "br": int(round((br - 1.0) * (100.0 - 1.0) / 254.0 + 1.0)),
                "ct": int(round(
                    (self._attr_max_mireds - ct) /
                    (self._attr_max_mireds - self._attr_min_mireds) * 255.0)
                )
            }
        else:
            payload = B02_MODE_PAYLOADS[mode]

        if not self._attr_is_on:
            await self.ewelink.send(self.device, {"switch": "on"})

        payload = {"ltype": mode, mode: payload}

        await self.ewelink.send(self.device, payload)


# Taken straight from the debug mode and the eWeLink app
B05_MODE_PAYLOADS = {
    'bright': {'r': 255, 'g': 255, 'b': 255, 'br': 100},
    'goodNight': {'r': 254, 'g': 254, 'b': 126, 'br': 25},
    'read': {'r': 255, 'g': 255, 'b': 255, 'br': 60},
    'nightLight': {'r': 255, 'g': 242, 'b': 226, 'br': 5},
    'party': {'r': 254, 'g': 132, 'b': 0, 'br': 45, 'tf': 1, 'sp': 1},
    'leisure': {'r': 0, 'g': 40, 'b': 254, 'br': 55, 'tf': 1, 'sp': 1},
    'soft': {'r': 38, 'g': 254, 'b': 0, 'br': 20, 'tf': 1, 'sp': 1},
    'colorful': {'r': 255, 'g': 0, 'b': 0, 'br': 100, 'tf': 1, 'sp': 1},
}


# noinspection PyAbstractClass, UIID 104
class XLightB05(XDimmer):
    def set_state(self, params: dict):
        if "switch" in params:
            self._attr_is_on = params["switch"] == "on"

        if "ltype" not in params:
            return

        effect = params["ltype"]

        if effect != self._attr_effect:
            self._attr_effect = effect

            if effect == "color":
                self._attr_supported_features = \
                    SUPPORT_BRIGHTNESS | SUPPORT_COLOR | SUPPORT_EFFECT
            elif effect == "white":
                self._attr_supported_features = \
                    SUPPORT_BRIGHTNESS | SUPPORT_COLOR_TEMP | SUPPORT_EFFECT
            else:
                self._attr_supported_features = SUPPORT_EFFECT

        state = params[effect]
        if "br" in state:
            # 1..100 => 1..255
            br = state["br"]
            self._attr_brightness = round(
                1.0 + (br - 1.0) / (100.0 - 1.0) * 254.0
            )

        if "ct" in state:
            # 0..255 => 500..153
            ct = state['ct']
            self._attr_color_temp = round(500.0 - ct / 255.0 * (500.0 - 153.0))
            self._attr_hs_color = None

        if 'r' in state or 'g' in state or 'b' in state:
            self._attr_hs_color = color.color_RGB_to_hs(
                state.get('r', 0),
                state.get('g', 0),
                state.get('b', 0)
            )
            self._attr_color_temp = None

    async def async_turn_on(self, **kwargs) -> None:
        payload = {}

        if ATTR_EFFECT in kwargs:
            mode = kwargs[ATTR_EFFECT]
            payload['ltype'] = mode
            if mode in B05_MODE_PAYLOADS:
                payload.update({mode: B05_MODE_PAYLOADS[mode]})
        else:
            mode = self._attr_effect

        if mode == 'color':
            br = kwargs.get(ATTR_BRIGHTNESS) or self._attr_brightness or 1
            hs = kwargs.get(ATTR_HS_COLOR) or self._attr_hs_color or (0, 0)
            rgb = color.color_hs_to_RGB(*hs)

            payload['ltype'] = mode
            payload[mode] = {
                'br': int(round((br - 1.0) * (100.0 - 1.0) / 254.0 + 1.0)),
                'r': rgb[0],
                'g': rgb[1],
                'b': rgb[2],
            }

        elif mode == 'white':
            br = kwargs.get(ATTR_BRIGHTNESS) or self._attr_brightness or 1
            ct = kwargs.get(ATTR_COLOR_TEMP) or self._attr_color_temp or 153

            payload['ltype'] = mode
            payload[mode] = {
                'br': int(round((br - 1.0) * (100.0 - 1.0) / 254.0 + 1.0)),
                'ct': int(round((500.0 - ct) / (500.0 - 153.0) * 255.0))
            }

        if not self._attr_is_on:
            await self.ewelink.send(self.device, {'switch': 'on'})

        await self.ewelink.send(self.device, payload)


# noinspection PyAbstractClass
class XLightGroup(XDimmer):
    """Differs from the usual switch by brightness adjustment. Is logical
    use only for two or more channels. Able to remember brightness on moment
    off.
    The sequence of channels is important. The first channels will be turned on
    at low brightness.
    """
    params = {"switches"}
    channels: list = None

    def set_state(self, params: dict):
        cnt = sum(
            1 for i in params["switches"]
            if i["outlet"] in self.channels and i["switch"] == "on"
        )
        if cnt:
            # if at least something is on - remember the new brightness
            self._attr_brightness = round(cnt / len(self.channels) * 255)
            self._attr_is_on = True
        else:
            self._attr_is_on = False

    async def async_turn_on(self, brightness: int = None, **kwargs):
        if brightness is not None:
            self._attr_brightness = brightness
        elif self._attr_brightness == 0:
            self._attr_brightness = 255

        # how much light should turn on at such brightness
        cnt = round(self._attr_brightness / 255 * len(self.channels))

        # the first part of the lights - turn on, the second - turn off
        switches = [
            {"outlet": channel, "switch": "on" if i < cnt else "off"}
            for i, channel in enumerate(self.channels)
        ]
        await self.ewelink.send(self.device, {"switches": switches})

    async def async_turn_off(self, **kwargs) -> None:
        switches = [{"outlet": ch, "switch": "off"} for ch in self.channels]
        await self.ewelink.send(self.device, {"switches": switches})
