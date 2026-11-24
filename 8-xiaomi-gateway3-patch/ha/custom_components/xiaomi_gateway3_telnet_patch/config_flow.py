"""Configure gateway credentials in HA UI; never prefill password fields."""
import ipaddress
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import DOMAIN, refresh_gateways
from .bootstrap import BootstrapError, install_bootstrap
from .runtime import MANAGER, Manager, PasswordPatchError

LOGGER = logging.getLogger(__name__)
PASSWORD_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def validate(host, password):
    try:
        host = str(ipaddress.ip_address(host.strip()))
    except (ValueError, AttributeError):
        return None, "invalid_host"
    try:
        Manager().configure({host: {"password": password}})
    except PasswordPatchError:
        return None, "invalid_password"
    return host, None


def duplicate(hass, host, current_id=None):
    return any(e.entry_id != current_id and e.data.get("host") == host
               for e in hass.config_entries.async_entries(DOMAIN))


class PasswordConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PasswordOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        host = ""
        if user_input is not None:
            host, error = validate(user_input.get("host", ""), user_input.get("password", ""))
            if error:
                errors["base"] = error
            elif duplicate(self.hass, host):
                return self.async_abort(reason="already_configured")
            elif not user_input.get("install_bootstrap", True) and not MANAGER.early_installed:
                errors["base"] = "bootstrap_required"
            else:
                try:
                    if user_input.get("install_bootstrap", True):
                        await self.hass.async_add_executor_job(
                            install_bootstrap, self.hass.config.path("custom_components"))
                except (OSError, BootstrapError, UnicodeError):
                    LOGGER.error("Password startup hook could not be installed; no credentials saved")
                    errors["base"] = "bootstrap_failed"
                else:
                    await self.async_set_unique_id(host)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=f"GW2 {host}", data={
                        "host": host, "password": user_input["password"],
                    })
        schema = vol.Schema({
            vol.Required("host", default=host or ""): str,
            vol.Required("password"): PASSWORD_SELECTOR,
            vol.Required("install_bootstrap", default=True): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class PasswordOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        entry = self.config_entry
        if user_input is not None:
            password = user_input.get("password") or entry.data["password"]
            host, error = validate(user_input.get("host", ""), password)
            if error:
                errors["base"] = error
            elif duplicate(self.hass, host, entry.entry_id):
                errors["base"] = "already_configured"
            else:
                self.hass.config_entries.async_update_entry(entry, title=f"GW2 {host}",
                    unique_id=host, data={"host": host, "password": password})
                refresh_gateways(self.hass)
                return self.async_create_entry(title="", data={})
        schema = vol.Schema({
            vol.Required("host", default=entry.data["host"]): str,
            vol.Optional("password"): PASSWORD_SELECTOR,
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
