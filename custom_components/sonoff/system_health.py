"""Provide info to system health."""
import logging
import re
import uuid
from collections import deque
from datetime import datetime
from logging import Logger
from typing import Any

from aiohttp import web
from homeassistant.components import system_health
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .core.const import DOMAIN


@callback
def async_register(
        hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    cloud_online = local_online = cloud_total = local_total = 0

    for registry in hass.data[DOMAIN].values():
        for device in registry.devices.values():
            if "online" in device:
                cloud_total += 1
                if registry.cloud.online and device["online"]:
                    cloud_online += 1
            if "host" in device:
                local_total += 1
                if "params" in device:
                    local_online += 1

    info = {
        "cloud_online": f"{cloud_online} / {cloud_total}",
        "local_online": f"{local_online} / {local_total}",
    }

    if DebugView.url:
        info["debug"] = {
            "type": "failed", "error": "",
            "more_info": DebugView.url
        }

    return info


async def setup_debug(hass: HomeAssistant, logger: Logger):
    info = await hass.helpers.system_info.async_get_system_info()
    view = DebugView()

    logger.addHandler(view)
    logger.debug(f"SysInfo: {info}")

    hass.http.register_view(view)


class DebugView(logging.Handler, HomeAssistantView):
    name = "sonoff_debug"
    requires_auth = False

    # https://waymoot.org/home/python_string/
    text = deque(maxlen=10000)

    def __init__(self, ):
        super().__init__()

        # random url because without authorization!!!
        DebugView.url = f"/api/{DOMAIN}/{uuid.uuid4()}"

    def handle(self, rec: logging.LogRecord) -> None:
        dt = datetime.fromtimestamp(rec.created).strftime("%Y-%m-%d %H:%M:%S")
        self.text.append(f"{dt} [{rec.levelname[0]}] {rec.msg}")

    async def get(self, request: web.Request):
        try:
            lines = self.text

            if 'q' in request.query:
                reg = re.compile(fr"({request.query['q']})", re.IGNORECASE)
                lines = [p for p in lines if reg.search(p)]

            if 't' in request.query:
                tail = int(request.query['t'])
                lines = lines[-tail:]

            body = "\n".join(lines)
            r = request.query.get('r', '')

            return web.Response(
                text='<!DOCTYPE html><html>'
                     f'<head><meta http-equiv="refresh" content="{r}"></head>'
                     f'<body><pre>{body}</pre></body>'
                     '</html>',
                content_type="text/html"
            )
        except:
            return web.Response(status=500)
