from functools import lru_cache

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.const import *
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .core.const import DOMAIN, CONF_MODES
from .core.ewelink import XRegistryCloud


class SonoffLANFlowHandler(ConfigFlow, domain=DOMAIN):
    @property
    @lru_cache(maxsize=0)
    def cloud(self):
        session = async_get_clientsession(self.hass)
        return XRegistryCloud(session)

    async def async_step_import(self, user_input=None):
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)
            try:
                if username and password:
                    await self.cloud.login(username, password)
                return self.async_create_entry(title=username, data=user_input)
            except Exception as e:
                error = f"\n\n`{e}`"
        else:
            error = None
            username = vol.UNDEFINED

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME, default=username): str,
                vol.Optional(CONF_PASSWORD): str,
            }),
            description_placeholders={"error": error}
        )

    async def async_step_reauth(self, user_input=None):
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry):
        return OptionsFlowHandler(entry)


# noinspection PyUnusedLocal
class OptionsFlowHandler(OptionsFlow):
    def __init__(self, entry: ConfigEntry):
        self.entry = entry

    async def async_step_init(self, user_input: dict = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        mode = self.entry.options.get(CONF_MODE, "auto")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_MODE, default=mode): vol.In(CONF_MODES),
            })
        )
