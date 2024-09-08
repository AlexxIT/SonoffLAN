import time

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.util import color

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, LightEntity)]),
    )


def conv(value: int, a1: int, a2: int, b1: int, b2: int) -> int:
    value = round((value - a1) / (a2 - a1) * (b2 - b1) + b1)
    if value < min(b1, b2):
        value = min(b1, b2)
    if value > max(b1, b2):
        value = max(b1, b2)
    return value


###############################################################################
# Category 1. XLight base (brightness)
###############################################################################


class XOnOffLight(XEntity, LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}


# https://developers.home-assistant.io/docs/core/entity/light/
# noinspection PyAbstractClass
class XLight(XEntity, LightEntity):
    uid = ""  # prevent add param to entity_id

    # support on/off and brightness
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    def set_state(self, params: dict):
        if self.param in params:
            self._attr_is_on = params[self.param] == "on"

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        pass

    async def async_turn_on(
        self,
        brightness: int = None,
        color_temp: int = None,
        rgb_color=None,
        xy_color=None,
        hs_color=None,
        effect: str = None,
        transition: float = None,
        **kwargs,
    ) -> None:
        if xy_color:
            rgb_color = color.color_xy_to_RGB(*xy_color)
        elif hs_color:
            rgb_color = color.color_hs_to_RGB(*hs_color)

        if transition:
            await self.transiton(brightness, color_temp, rgb_color, transition)
            return

        if brightness == 0:
            await self.async_turn_off()
            return

        if brightness or color_temp or rgb_color or effect:
            params = self.get_params(brightness, color_temp, rgb_color, effect)
        else:
            params = None

        if params:
            # some lights can only be turned on when the lights are off
            if not self.is_on:
                await self.ewelink.send(
                    self.device, {self.param: "on"}, query_cloud=False
                )

            await self.ewelink.send(
                self.device,
                params,
                {"cmd": "dimmable", **params},
                cmd_lan="dimmable",
                query_cloud=kwargs.get("query_cloud", True),
            )
        else:
            await self.ewelink.send(self.device, {self.param: "on"})

    async def async_turn_off(self, **kwargs) -> None:
        await self.ewelink.send(self.device, {self.param: "off"})

    async def transiton(
        self,
        brightness: int,
        color_temp: int,
        rgb_color,
        transition: float,
    ):
        br0 = self.brightness or 0
        br1 = brightness
        ct0 = self.color_temp or self.min_mireds
        ct1 = color_temp
        rgb0 = self.rgb_color or [0, 0, 0]
        rgb1 = rgb_color

        t0 = time.time()

        while (k := (time.time() - t0) / transition) < 1:
            if br1 is not None:
                brightness = br0 + round((br1 - br0) * k)
            if ct1 is not None:
                color_temp = ct0 + round((ct1 - ct0) * k)
            if rgb1 is not None:
                rgb_color = [rgb0[i] + round((rgb1[i] - rgb0[i]) * k) for i in range(3)]

            await self.async_turn_on(
                brightness, color_temp, rgb_color, query_cloud=False
            )

        await self.async_turn_on(br1, ct1, rgb1)


# noinspection PyAbstractClass, UIID36
class XDimmer(XLight):
    params = {"switch", "bright"}
    param = "switch"

    def set_state(self, params: dict):
        XLight.set_state(self, params)
        if "bright" in params:
            self._attr_brightness = conv(params["bright"], 10, 100, 1, 255)

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        if brightness:
            return {"bright": conv(brightness, 1, 255, 10, 100)}


# noinspection PyAbstractClass, UIID57
class XLight57(XLight):
    params = {"state", "channel0"}
    param = "state"

    def set_state(self, params: dict):
        XLight.set_state(self, params)
        if "channel0" in params:
            self._attr_brightness = conv(params["channel0"], 25, 255, 1, 255)

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        if brightness:
            return {"channel0": str(conv(brightness, 1, 255, 25, 255))}


# noinspection PyAbstractClass, UIID44
class XLightD1(XLight):
    params = {"switch", "brightness"}
    param = "switch"

    def set_state(self, params: dict):
        XLight.set_state(self, params)
        if "brightness" in params:
            self._attr_brightness = conv(params["brightness"], 0, 100, 1, 255)

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        if brightness:
            # brightness can be only with switch=on in one message (error 400)
            # the purpose of the mode is unclear
            # max brightness=100 (error 400)
            return {
                "brightness": conv(brightness, 1, 255, 0, 100),
                "mode": 0,
                "switch": "on",
            }


###############################################################################
# Category 2. XLight base (color)
###############################################################################

UIID22_MODES = {
    "Good Night": {
        "channel0": "0",
        "channel1": "0",
        "channel2": "189",
        "channel3": "118",
        "channel4": "0",
        "zyx_mode": 3,
        "type": "middle",
    },
    "Reading": {
        "channel0": "0",
        "channel1": "0",
        "channel2": "255",
        "channel3": "255",
        "channel4": "255",
        "zyx_mode": 4,
        "type": "middle",
    },
    "Party": {
        "channel0": "0",
        "channel1": "0",
        "channel2": "207",
        "channel3": "56",
        "channel4": "3",
        "zyx_mode": 5,
        "type": "middle",
    },
    "Leisure": {
        "channel0": "0",
        "channel1": "0",
        "channel2": "56",
        "channel3": "85",
        "channel4": "179",
        "zyx_mode": 6,
        "type": "middle",
    },
}


# noinspection PyAbstractClass, UIID22
class XLightB1(XLight):
    params = {"state", "zyx_mode", "channel0", "channel2"}
    param = "state"

    _attr_min_mireds = 1  # cold
    _attr_max_mireds = 3  # warm
    _attr_effect_list = list(UIID22_MODES.keys())
    # support on/off, brightness, color_temp and RGB
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT | LightEntityFeature.TRANSITION

    def set_state(self, params: dict):
        XLight.set_state(self, params)

        if "zyx_mode" in params:
            mode = params["zyx_mode"]  # 1-6
            if mode == 1:
                self._attr_color_mode = ColorMode.COLOR_TEMP
            else:
                self._attr_color_mode = ColorMode.RGB
            if mode >= 3:
                self._attr_effect = self.effect_list[mode - 3]
            else:
                self._attr_effect = None

        if self.color_mode == ColorMode.COLOR_TEMP:
            # from 25 to 255
            cold = int(params["channel0"])
            warm = int(params["channel1"])
            if warm == 0:
                self._attr_color_temp = 1
            elif cold == warm:
                self._attr_color_temp = 2
            elif cold == 0:
                self._attr_color_temp = 3
            self._attr_brightness = conv(max(cold, warm), 25, 255, 1, 255)

        else:
            self._attr_rgb_color = (
                int(params["channel2"]),
                int(params["channel3"]),
                int(params["channel4"]),
            )

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        if brightness or color_temp:
            ch = str(conv(brightness or self.brightness, 1, 255, 25, 255))
            if not color_temp:
                color_temp = self.color_temp
            if color_temp == 1:
                params = {"channel0": ch, "channel1": "0"}
            elif color_temp == 2:
                params = {"channel0": ch, "channel1": ch}
            elif color_temp == 3:
                params = {"channel0": ch, "channel1": ch}
            else:
                raise NotImplementedError

            return {
                **params,
                "channel2": "0",
                "channel3": "0",
                "channel4": "0",
                "zyx_mode": 1,
            }

        if rgb_color:
            return {
                "channel0": "0",
                "channel1": "0",
                "channel2": str(rgb_color[0]),
                "channel3": str(rgb_color[1]),
                "channel4": str(rgb_color[2]),
                "zyx_mode": 2,
            }

        if effect:
            return UIID22_MODES[effect]


# noinspection PyAbstractClass, UIID59
class XLightL1(XLight):
    params = {"switch", "bright", "colorR", "mode"}
    param = "switch"

    modes = {
        "Colorful": {"mode": 1, "switch": "on"},
        "Colorful Gradient": {"mode": 2, "switch": "on"},
        "Colorful Breath": {"mode": 3, "switch": "on"},
        "DIY Gradient": {"mode": 4, "switch": "on"},
        "DIY Pulse": {"mode": 5, "switch": "on"},
        "DIY Breath": {"mode": 6, "switch": "on"},
        "DIY Strobe": {"mode": 7, "switch": "on"},
        "RGB Gradient": {"mode": 8, "switch": "on"},
        "RGB Pulse": {"mode": 9, "switch": "on"},
        "RGB Breath": {"mode": 10, "switch": "on"},
        "RGB Strobe": {"mode": 11, "switch": "on"},
        "Music": {"mode": 12, "switch": "on"},
    }

    _attr_color_mode = ColorMode.RGB
    _attr_effect_list = list(modes.keys())

    # support on/off, brightness, RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT | LightEntityFeature.TRANSITION

    def set_state(self, params: dict):
        XLight.set_state(self, params)

        if "bright" in params:
            self._attr_brightness = conv(params["bright"], 1, 100, 1, 255)
        if "colorR" in params and "colorG" in params and "colorB":
            self._attr_rgb_color = (
                params["colorR"],
                params["colorG"],
                params["colorB"],
            )
        if "mode" in params:
            self._attr_effect = next(
                (k for k, v in self.modes.items() if v["mode"] == params["mode"]), None
            )

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        params = {}
        if effect:
            params.update(self.modes[effect])
        if brightness:
            params.setdefault("mode", 1)
            params["bright"] = conv(brightness, 1, 255, 1, 100)
        if rgb_color:
            params.setdefault("mode", 1)
            params.update(
                {
                    "colorR": rgb_color[0],
                    "colorG": rgb_color[1],
                    "colorB": rgb_color[2],
                    "light_type": 1,
                }
            )
        return params


# noinspection PyAbstractClass
class XLightL3(XLightL1):
    modes = {
        "Warm White": {
            "switch": "on",
            "mode": 2,
            "speed07": 50,
            "bright07": 100,
            "light_type": 1,
        },
        "Magic Forward": {
            "switch": "on",
            "mode": 7,
            "speed07": 50,
            "bright07": 100,
            "light_type": 1,
        },
        "Magic Back": {
            "switch": "on",
            "mode": 8,
            "speed08": 50,
            "bright08": 100,
            "light_type": 1,
        },
        "7 Color Wave": {
            "switch": "on",
            "mode": 35,
            "speed35": 50,
            "bright35": 100,
            "light_type": 1,
        },
        "7 Color Wave Back": {
            "switch": "on",
            "mode": 36,
            "speed36": 50,
            "bright36": 100,
            "light_type": 1,
        },
        "RGB Wave": {
            "switch": "on",
            "mode": 37,
            "speed37": 50,
            "bright37": 100,
            "light_type": 1,
        },
        "RGB Wave Back": {
            "switch": "on",
            "mode": 38,
            "speed38": 50,
            "bright38": 100,
            "light_type": 1,
        },
        "YCP Wave": {
            "switch": "on",
            "mode": 39,
            "speed39": 50,
            "bright39": 100,
            "light_type": 1,
        },
        "YCP Wave Back": {
            "switch": "on",
            "mode": 40,
            "speed40": 50,
            "bright40": 100,
            "light_type": 1,
        },
        "7 Color Race": {
            "switch": "on",
            "mode": 29,
            "speed29": 50,
            "bright29": 100,
            "light_type": 1,
        },
        "7 Color Race Back": {
            "switch": "on",
            "mode": 30,
            "speed30": 50,
            "bright30": 100,
            "light_type": 1,
        },
        "RGB Race": {
            "switch": "on",
            "mode": 31,
            "speed31": 50,
            "bright31": 100,
            "light_type": 1,
        },
        "RGB Race Back": {
            "switch": "on",
            "mode": 32,
            "speed32": 50,
            "bright32": 100,
            "light_type": 1,
        },
        "YCP Race": {
            "switch": "on",
            "mode": 33,
            "speed33": 50,
            "bright33": 100,
            "light_type": 1,
        },
        "YCP Race Back": {
            "switch": "on",
            "mode": 34,
            "speed34": 50,
            "bright34": 100,
            "light_type": 1,
        },
        "7 Color Flush": {
            "switch": "on",
            "mode": 41,
            "speed41": 50,
            "bright41": 100,
            "light_type": 1,
        },
        "7 Color Flush Back": {
            "switch": "on",
            "mode": 42,
            "speed42": 50,
            "bright42": 100,
            "light_type": 1,
        },
        "RGB Flush": {
            "switch": "on",
            "mode": 43,
            "speed43": 50,
            "bright43": 100,
            "light_type": 1,
        },
        "RGB Flush Back": {
            "switch": "on",
            "mode": 44,
            "speed44": 50,
            "bright44": 100,
            "light_type": 1,
        },
        "YCP Flush": {
            "switch": "on",
            "mode": 45,
            "speed45": 50,
            "bright45": 100,
            "light_type": 1,
        },
        "YCP Flush Back": {
            "switch": "on",
            "mode": 46,
            "speed46": 50,
            "bright46": 100,
            "light_type": 1,
        },
        "7 Color Flush Close": {
            "switch": "on",
            "mode": 47,
            "speed47": 50,
            "bright47": 100,
            "light_type": 1,
        },
        "7 Color Flush Open": {
            "switch": "on",
            "mode": 48,
            "speed48": 50,
            "bright48": 100,
            "light_type": 1,
        },
        "RGB Flush Close": {
            "switch": "on",
            "mode": 49,
            "speed49": 50,
            "bright49": 100,
            "light_type": 1,
        },
        "RGB Flush Open": {
            "switch": "on",
            "mode": 50,
            "speed50": 50,
            "bright50": 100,
            "light_type": 1,
        },
        "YCP Flush Close": {
            "switch": "on",
            "mode": 51,
            "speed51": 50,
            "bright51": 100,
            "light_type": 1,
        },
        "YCP Flush Open": {
            "switch": "on",
            "mode": 52,
            "speed52": 50,
            "bright52": 100,
            "light_type": 1,
        },
        "Red Marquee": {
            "switch": "on",
            "mode": 22,
            "speed22": 50,
            "bright22": 100,
            "light_type": 1,
        },
        "Green Marquee": {
            "switch": "on",
            "mode": 23,
            "speed23": 50,
            "bright23": 100,
            "light_type": 1,
        },
        "Blue Marquee": {
            "switch": "on",
            "mode": 24,
            "speed24": 50,
            "bright24": 100,
            "light_type": 1,
        },
        "Yellow Marquee": {
            "switch": "on",
            "mode": 25,
            "speed25": 50,
            "bright25": 100,
            "light_type": 1,
        },
        "Cyan Marquee": {
            "switch": "on",
            "mode": 26,
            "speed26": 50,
            "bright26": 100,
            "light_type": 1,
        },
        "Purple Marquee": {
            "switch": "on",
            "mode": 27,
            "speed27": 50,
            "bright27": 100,
            "light_type": 1,
        },
        "White Marquee": {
            "switch": "on",
            "mode": 28,
            "speed28": 50,
            "bright28": 100,
            "light_type": 1,
        },
        "7 Color Jump": {
            "switch": "on",
            "mode": 10,
            "speed10": 50,
            "bright10": 100,
            "light_type": 1,
        },
        "RGB Jump": {
            "switch": "on",
            "mode": 11,
            "speed11": 50,
            "bright11": 100,
            "light_type": 1,
        },
        "YCP Jump": {
            "switch": "on",
            "mode": 12,
            "speed12": 50,
            "bright12": 100,
            "light_type": 1,
        },
        "7 Color Gradual": {
            "switch": "on",
            "mode": 16,
            "speed16": 50,
            "bright16": 100,
            "light_type": 1,
        },
        "RY Gradual": {
            "switch": "on",
            "mode": 17,
            "speed17": 50,
            "bright17": 100,
            "light_type": 1,
        },
        "RP Gradual": {
            "switch": "on",
            "mode": 18,
            "speed18": 50,
            "bright18": 100,
            "light_type": 1,
        },
        "GC Gradual": {
            "switch": "on",
            "mode": 19,
            "speed19": 50,
            "bright19": 100,
            "light_type": 1,
        },
        "GY Gradual": {
            "switch": "on",
            "mode": 20,
            "speed20": 50,
            "bright20": 100,
            "light_type": 1,
        },
        "BP Gradual": {
            "switch": "on",
            "mode": 21,
            "speed21": 50,
            "bright21": 100,
            "light_type": 1,
        },
        "7 Color Strobe": {
            "switch": "on",
            "mode": 13,
            "speed13": 50,
            "bright13": 100,
            "light_type": 1,
        },
        "RGB Strobe": {
            "switch": "on",
            "mode": 14,
            "speed14": 50,
            "bright14": 100,
            "light_type": 1,
        },
        "YCP Strobe": {
            "switch": "on",
            "mode": 15,
            "speed15": 50,
            "bright15": 100,
            "light_type": 1,
        },
        "Classic Music": {
            "switch": "on",
            "mode": 4,
            "rhythmMode": 0,
            "rhythmSensitive": 100,
            "bright": 100,
            "light_type": 1,
        },
        "Soft Music": {
            "switch": "on",
            "mode": 4,
            "rhythmMode": 1,
            "rhythmSensitive": 100,
            "bright": 100,
            "light_type": 1,
        },
        "Dynamic Music": {
            "switch": "on",
            "mode": 4,
            "rhythmMode": 2,
            "rhythmSensitive": 100,
            "bright": 100,
            "light_type": 1,
        },
        "Disco Music": {
            "switch": "on",
            "mode": 4,
            "rhythmMode": 3,
            "rhythmSensitive": 100,
            "bright": 100,
            "light_type": 1,
        },
    }

    _attr_effect_list = list(modes.keys())

    def set_state(self, params: dict):
        XLightL1.set_state(self, params)

        if "rhythmMode" in params:
            self._attr_effect = next(
                (
                    k
                    for k, v in self.modes.items()
                    if v.get("rhythmMode") == params["rhythmMode"]
                ),
                None,
            )

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        # fix https://github.com/AlexxIT/SonoffLAN/issues/1394
        if brightness is not None and rgb_color is None:
            rgb_color = self.rgb_color
        if brightness is None and rgb_color is not None:
            brightness = self.brightness
        return super().get_params(brightness, color_temp, rgb_color, effect)


B02_MODE_PAYLOADS = {
    "nightLight": {"br": 5, "ct": 0},
    "read": {"br": 50, "ct": 0},
    "computer": {"br": 20, "ct": 255},
    "bright": {"br": 100, "ct": 255},
}


# noinspection PyAbstractClass, UIID103
class XLightB02(XLight):
    params = {"switch", "ltype"}
    param = "switch"

    # FS-1, B02-F-A60 and other
    _attr_max_mireds: int = int(1000000 / 2200)  # 454
    _attr_min_mireds: int = int(1000000 / 6500)  # 153

    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_effect_list = list(B02_MODE_PAYLOADS.keys())
    # support on/off, brightness and color_temp
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.EFFECT | LightEntityFeature.TRANSITION

    # ewelink specs
    min_br = 1
    max_br = 100
    min_ct = 0
    max_ct = 255

    def __init__(self, ewelink: XRegistry, device: dict):
        XEntity.__init__(self, ewelink, device)

        model = device.get("productModel")
        if model == "B02-F-ST64":
            self._attr_max_mireds = int(1000000 / 1800)  # 555
            self._attr_min_mireds = int(1000000 / 5000)  # 200
        elif model == "QMS-2C-CW":
            self._attr_max_mireds = int(1000000 / 2700)  # 370
            self._attr_min_mireds = int(1000000 / 6500)  # 153

    def set_state(self, params: dict):
        XLight.set_state(self, params)

        if "ltype" not in params:
            return

        self._attr_effect = params["ltype"]

        state = params[self.effect]
        if "br" in state:
            self._attr_brightness = conv(state["br"], self.min_br, self.max_br, 1, 255)
        if "ct" in state:
            self._attr_color_temp = conv(
                state["ct"], self.min_ct, self.max_ct, self.max_mireds, self.min_mireds
            )

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        if brightness or color_temp:
            return {
                "ltype": "white",
                "white": {
                    "br": conv(
                        brightness or self.brightness, 1, 255, self.min_br, self.max_br
                    ),
                    "ct": conv(
                        color_temp or self.color_temp,
                        self.max_mireds,
                        self.min_mireds,
                        self.min_ct,
                        self.max_ct,
                    ),
                },
            }
        if effect:
            return {"ltype": effect, effect: B02_MODE_PAYLOADS[effect]}


# Taken straight from the debug mode and the eWeLink app
B05_MODE_PAYLOADS = {
    "bright": {"r": 255, "g": 255, "b": 255, "br": 100},
    "goodNight": {"r": 254, "g": 254, "b": 126, "br": 25},
    "read": {"r": 255, "g": 255, "b": 255, "br": 60},
    "nightLight": {"r": 255, "g": 242, "b": 226, "br": 5},
    "party": {"r": 254, "g": 132, "b": 0, "br": 45, "tf": 1, "sp": 1},
    "leisure": {"r": 0, "g": 40, "b": 254, "br": 55, "tf": 1, "sp": 1},
    "soft": {"r": 38, "g": 254, "b": 0, "br": 20, "tf": 1, "sp": 1},
    "colorful": {"r": 255, "g": 0, "b": 0, "br": 100, "tf": 1, "sp": 1},
}


# noinspection PyAbstractClass, UIID 104
class XLightB05B(XLightB02):
    _attr_effect_list = list(B05_MODE_PAYLOADS.keys())
    # support on/off, brightness, color_temp and RGB
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.RGB}
    _attr_max_mireds = 500
    _attr_min_mireds = 153

    def set_state(self, params: dict):
        XLight.set_state(self, params)

        if "ltype" not in params:
            return

        effect = params["ltype"]
        if effect == "white":
            self._attr_color_mode = ColorMode.COLOR_TEMP
        else:
            self._attr_color_mode = ColorMode.RGB

        if effect in self.effect_list:
            self._attr_effect = effect

        # fix https://github.com/AlexxIT/SonoffLAN/issues/1093
        state = params.get(effect) or B05_MODE_PAYLOADS.get(effect) or {}
        if "br" in state:
            self._attr_brightness = conv(state["br"], self.min_br, self.max_br, 1, 255)

        if "ct" in state:
            self._attr_color_temp = conv(
                state["ct"], self.min_ct, self.max_ct, self.max_mireds, self.min_mireds
            )

        if "r" in state or "g" in state or "b" in state:
            self._attr_rgb_color = (
                state.get("r", 0),
                state.get("g", 0),
                state.get("b", 0),
            )

    def get_params(self, brightness, color_temp, rgb_color, effect) -> dict:
        if color_temp:
            return {
                "ltype": "white",
                "white": {
                    "br": conv(
                        brightness or self.brightness, 1, 255, self.min_br, self.max_br
                    ),
                    "ct": conv(
                        color_temp,
                        self.max_mireds,
                        self.min_mireds,
                        self.min_ct,
                        self.max_ct,
                    ),
                },
            }
        if rgb_color:
            return {
                "ltype": "color",
                "color": {
                    "br": conv(
                        brightness or self.brightness, 1, 255, self.min_br, self.max_br
                    ),
                    "r": rgb_color[0],
                    "g": rgb_color[1],
                    "b": rgb_color[2],
                },
            }
        if brightness:
            if self.color_mode == ColorMode.COLOR_TEMP:
                return self.get_params(brightness, self.color_temp, None, None)
            else:
                return self.get_params(brightness, None, self.rgb_color, None)
        if effect is not None:
            return {"ltype": effect, effect: B05_MODE_PAYLOADS[effect]}


class XZigbeeLight(XLight):
    param = "switch"

    _attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.HS}

    def set_state(self, params: dict):
        XLight.set_state(self, params)

        mode = params.get("colorMode")

        if mode == "cct":
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif mode == "rgb":
            self._attr_color_mode = ColorMode.HS

        if "colorTemp" in params:
            self._attr_color_temp = conv(
                params["colorTemp"],
                0,
                100,
                self._attr_max_mireds,  # yellow
                self._attr_min_mireds,  # blue
            )

        if br := params.get(f"{mode}Brightness"):
            self._attr_brightness = conv(br, 1, 100, 0, 255)

        if "hue" in params and "saturation" in params:
            self._attr_hs_color = (params["hue"], params["saturation"])

    async def async_turn_on(
        self,
        brightness: int = None,
        color_temp: int = None,
        hs_color: tuple = None,
        **kwargs,
    ) -> None:
        params = {self.param: "on"}

        if color_temp is not None:
            params["colorMode"] = "cct"
            params["colorTemp"] = conv(
                color_temp, self._attr_max_mireds, self._attr_min_mireds, 0, 100
            )

        if hs_color is not None:
            params["colorMode"] = "rgb"
            params["hue"] = hs_color[0]
            params["saturation"] = hs_color[1]

        if brightness is not None:
            if "colorMode" not in params:
                if self._attr_color_mode == ColorMode.COLOR_TEMP:
                    params["colorMode"] = "cct"
                elif self._attr_color_mode == ColorMode.HS:
                    params["colorMode"] = "rgb"

            k = params["colorMode"] + "Brightness"  # cctBrightness or rgbBrightness
            params[k] = conv(brightness, 0, 255, 1, 100)

        await self.ewelink.send(self.device, params)


###############################################################################
# Category 3. Other
###############################################################################


# noinspection PyAbstractClass
class XLightGroup(XEntity, LightEntity):
    """Differs from the usual switch by brightness adjustment. Is logical
    use only for two or more channels. Able to remember brightness on moment
    off.
    The sequence of channels is important. The first channels will be turned on
    at low brightness.
    """

    params = {"switches"}
    channels: list = None

    _attr_brightness = 0
    # support on/off and brightness
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def set_state(self, params: dict):
        cnt = sum(
            1
            for i in params["switches"]
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
        await self.ewelink.send_bulk(self.device, {"switches": switches})

    async def async_turn_off(self, **kwargs) -> None:
        switches = [{"outlet": ch, "switch": "off"} for ch in self.channels]
        await self.ewelink.send_bulk(self.device, {"switches": switches})


# noinspection PyAbstractClass, UIID22
class XFanLight(XOnOffLight):
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
        if self.device.get("localtype") == "fan_light":
            params_lan = {"light": "on"}
        else:
            params_lan = None
        await self.ewelink.send(self.device, params, params_lan)

    async def async_turn_off(self):
        params = {"switches": [{"outlet": 0, "switch": "off"}]}
        if self.device.get("localtype") == "fan_light":
            params_lan = {"light": "off"}
        else:
            params_lan = None
        await self.ewelink.send(self.device, params, params_lan)


# noinspection PyAbstractClass, UIID25
class XDiffuserLight(XOnOffLight):
    params = {"lightswitch", "lightbright", "lightmode", "lightRcolor"}

    _attr_effect_list = ["Color Light", "RGB Color", "Night Light"]
    _attr_supported_features = LightEntityFeature.EFFECT

    def set_state(self, params: dict):
        if "lightswitch" in params:
            self._attr_is_on = params["lightswitch"] == 1

        if "lightbright" in params:
            self._attr_brightness = conv(params["lightbright"], 0, 100, 1, 255)

        if "lightmode" in params:
            mode = params["lightmode"]
            if mode == 1:
                # support on/off
                self._attr_color_mode = ColorMode.ONOFF
                self._attr_supported_color_modes = {ColorMode.ONOFF}
            elif mode == 2:
                self._attr_color_mode = ColorMode.RGB
                # support on/off, brightness and RGB
                self._attr_supported_color_modes = {ColorMode.RGB}
            elif mode == 3:
                # support on/off and brightness
                self._attr_color_mode = ColorMode.BRIGHTNESS
                self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        if "lightRcolor" in params:
            self._attr_rgb_color = (
                params["lightRcolor"],
                params["lightGcolor"],
                params["lightBcolor"],
            )

    async def async_turn_on(
        self, brightness: int = None, rgb_color=None, effect: str = None, **kwargs
    ) -> None:
        params = {}

        if effect is not None:
            params["lightmode"] = mode = self.effect.index(effect) + 1
            if mode == 2 and rgb_color is None:
                rgb_color = self._attr_rgb_color

        if brightness is not None:
            params["lightbright"] = conv(brightness, 1, 255, 0, 100)

        if rgb_color is not None:
            params.update(
                {
                    "lightmode": 2,
                    "lightRcolor": rgb_color[0],
                    "lightGcolor": rgb_color[1],
                    "lightBcolor": rgb_color[2],
                }
            )

        if not params:
            params["lightswitch"] = 1

        await self.ewelink.send(self.device, params)

    async def async_turn_off(self, **kwargs) -> None:
        await self.ewelink.send(self.device, {"lightswitch": 0})


T5_EFFECTS = {
    "Night Light": 0,
    "Party": 1,
    "Leisure": 2,
    "Color": 3,
    "Childhood": 4,
    "Wiper": 5,
    "Fairy": 6,
    "Starburst": 7,
    "DIY 1": 101,
    "DIY 2": 102,
}


class XT5Light(XOnOffLight):
    params = {"lightSwitch", "lightMode"}

    _attr_effect_list = list(T5_EFFECTS.keys())
    _attr_supported_features = LightEntityFeature.EFFECT

    def set_state(self, params: dict):
        if "lightSwitch" in params:
            self._attr_is_on = params["lightSwitch"] == "on"

        if "lightMode" in params:
            self._attr_effect = next(
                (k for k, v in T5_EFFECTS.items() if v == params["lightMode"]), None
            )

    async def async_turn_on(
        self, brightness: int = None, effect: str = None, **kwargs
    ) -> None:
        params = {}

        if effect and effect in T5_EFFECTS:
            params["lightMode"] = T5_EFFECTS[effect]

        if not params:
            params["lightSwitch"] = "on"

        await self.ewelink.send(self.device, params)

    async def async_turn_off(self, **kwargs) -> None:
        await self.ewelink.send(self.device, {"lightSwitch": "off"})
