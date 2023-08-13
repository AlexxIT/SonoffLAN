from functools import lru_cache

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_MODE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowHandler
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .core.const import CONF_DEBUG, CONF_MODES, DOMAIN
from .core.ewelink import XRegistryCloud


def form(
    flow: FlowHandler,
    step_id: str,
    schema: dict,
    defaults: dict = None,
    template: dict = None,
    error: str = None,
):
    """Suppport:
    - overwrite schema defaults from dict (user_input or entry.options)
    - set base error code (translations > config > error > code)
    - set custom error via placeholders ("template": "{error}")
    """
    if defaults:
        for key in schema:
            if key.schema in defaults:
                key.default = vol.default_factory(defaults[key.schema])

    if template and "error" in template:
        error = {"base": "template"}
    elif error:
        error = {"base": error}

    return flow.async_show_form(
        step_id=step_id,
        data_schema=vol.Schema(schema),
        description_placeholders=template,
        errors=error,
    )


class SonoffLANFlowHandler(ConfigFlow, domain=DOMAIN):
    @property
    @lru_cache(maxsize=1)
    def cloud(self):
        session = async_get_clientsession(self.hass)
        return XRegistryCloud(session)

    async def async_step_import(self, user_input=None):
        return await self.async_step_user(user_input)

    async def async_step_user(self, data=None, error=None):
        schema = {vol.Required(CONF_USERNAME): str, vol.Optional(CONF_PASSWORD): str}

        if data is not None:
            username = data.get(CONF_USERNAME)
            password = data.get(CONF_PASSWORD)

            try:
                entry = await self.async_set_unique_id(username)
                if entry and password == "token":
                    # a special way to share a user's token
                    await self.cloud.login(
                        entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], 1
                    )
                    return form(
                        self,
                        "user",
                        schema,
                        data,
                        template={"error": "Token: " + self.cloud.token},
                    )

                if username and password:
                    await self.cloud.login(username, password)

                if entry:
                    self.hass.config_entries.async_update_entry(
                        entry, data=data, unique_id=self.unique_id
                    )
                    # entry will reload automatically because
                    # `entry.update_listeners` linked to `async_update_options`
                    return self.async_abort(reason="reauth_successful")

                return self.async_create_entry(title=username, data=data)

            except Exception as e:
                return form(self, "user", schema, data, template={"error": str(e)})

        return form(self, "user", schema)

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

    async def async_step_init(self, data: dict = None):
        if data is not None:
            return self.async_create_entry(title="", data=data)

        homes = {}

        username = self.entry.data.get(CONF_USERNAME)
        password = self.entry.data.get(CONF_PASSWORD)
        if username and password:
            try:
                # important to use another accout for get user homes
                session = async_get_clientsession(self.hass)
                cloud = XRegistryCloud(session)
                await cloud.login(username, password, app=1)
                homes = await cloud.get_homes()
            except:
                pass

        for home in self.entry.options.get("homes", []):
            if home not in homes:
                homes[home] = home

        return form(
            self,
            "init",
            {
                vol.Optional(CONF_MODE, default="auto"): vol.In(CONF_MODES),
                vol.Optional(CONF_DEBUG, default=False): bool,
                vol.Optional("homes"): cv.multi_select(homes),
            },
            self.entry.options,
        )
