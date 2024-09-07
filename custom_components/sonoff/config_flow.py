from functools import lru_cache

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_MODE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .core.const import CONF_DEBUG, CONF_COUNTRY_CODE, CONF_MODES, DOMAIN
from .core.ewelink import XRegistryCloud
from .core.ewelink.cloud import REGIONS


class FlowHandler(ConfigFlow, domain=DOMAIN):
    @property
    @lru_cache(maxsize=1)
    def cloud(self):
        session = async_get_clientsession(self.hass)
        return XRegistryCloud(session)

    async def async_step_import(self, user_input=None):
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input: dict = None):
        codes = {k: f"{v[0]} | {k}" for k, v in REGIONS.items()}

        data_schema = vol_schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Optional(CONF_PASSWORD): str,
                vol.Optional(CONF_COUNTRY_CODE): vol.In(codes),
            },
            user_input,
        )

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input.get(CONF_PASSWORD)

            try:
                config_entry = await self.async_set_unique_id(username)
                if config_entry and password == "token":
                    # a special way to share a user's token
                    await self.cloud.login(**config_entry.data, app=1)
                    return self.async_show_form(
                        step_id="user",
                        data_schema=data_schema,
                        errors={"base": "template"},
                        description_placeholders={
                            "error": "Token: " + self.cloud.token
                        },
                    )

                if password:
                    await self.cloud.login(**user_input)

                if config_entry:
                    self.hass.config_entries.async_update_entry(
                        config_entry, data=user_input, unique_id=self.unique_id
                    )
                    # entry will reload automatically because
                    # `entry.update_listeners` linked to `async_update_options`
                    return self.async_abort(reason="reauth_successful")

                return self.async_create_entry(title=username, data=user_input)

            except Exception as e:
                return self.async_show_form(
                    step_id="user",
                    data_schema=data_schema,
                    errors={"base": "template"},
                    description_placeholders={"error": str(e)},
                )

        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_reauth(self, user_input=None):
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return OptionsFlowHandler(config_entry)


# noinspection PyUnusedLocal
class OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry):
        self.config_entry = config_entry

    async def async_step_init(self, data: dict = None):
        if data is not None:
            return self.async_create_entry(title="", data=data)

        homes = {}

        if self.config_entry.data.get(CONF_PASSWORD):
            try:
                # important to use another accout for get user homes
                session = async_get_clientsession(self.hass)
                cloud = XRegistryCloud(session)
                await cloud.login(**self.config_entry.data, app=1)
                homes = await cloud.get_homes()
            except:
                pass

        for home in self.config_entry.options.get("homes", []):
            if home not in homes:
                homes[home] = home

        data = vol_schema(
            {
                vol.Optional(CONF_MODE, default="auto"): vol.In(CONF_MODES),
                vol.Optional(CONF_DEBUG, default=False): bool,
                vol.Optional("homes"): cv.multi_select(homes),
            },
            dict(self.config_entry.options),
        )
        return self.async_show_form(step_id="init", data_schema=data)


def vol_schema(schema: dict, defaults: dict | None) -> vol.Schema:
    if defaults:
        for key in schema:
            if (value := defaults.get(key.schema)) is not None:
                key.default = vol.default_factory(value)
    return vol.Schema(schema)
