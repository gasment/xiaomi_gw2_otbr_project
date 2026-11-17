"""UI configuration with optional legacy YAML; early hooks enforce startup ordering."""
import logging

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir

from .runtime import MANAGER, PasswordPatchError

DOMAIN = "xiaomi_gateway3_telnet_patch"
LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): vol.Schema({
        vol.Required("gateways"): {cv.string: vol.Schema({vol.Required("password"): cv.string})},
    }),
}, extra=vol.ALLOW_EXTRA)


def refresh_gateways(hass, *, exclude_entry_id=None):
    data = hass.data.setdefault(DOMAIN, {})
    gateways = dict(data.get("yaml_gateways", {}))
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == exclude_entry_id:
            continue
        gateways[entry.data["host"]] = {"password": entry.data["password"]}
    MANAGER.configure(gateways, allow_empty=True)
    data["protected_gateways"] = len(gateways)


async def async_setup(hass, config):
    data = hass.data.setdefault(DOMAIN, {})
    data["yaml_gateways"] = config.get(DOMAIN, {}).get("gateways", {})
    try:
        refresh_gateways(hass)
    except (PasswordPatchError, KeyError):
        LOGGER.error("GW2_PASSWORD_PATCH_CONFIG_ERROR: check gateway addresses and passwords")
        return False
    if MANAGER.early_installed:
        LOGGER.info("GW2_PASSWORD_PATCH_READY: early hooks active; %d protected gateway(s)", data["protected_gateways"])
    elif data["yaml_gateways"]:
        LOGGER.error("GW2_PASSWORD_PATCH_NOT_READY: install startup hook and restart HA")
        return False
    return True


async def _entry_updated(hass, entry):
    refresh_gateways(hass)


async def async_setup_entry(hass, entry):
    refresh_gateways(hass)
    if not MANAGER.early_installed:
        ir.async_create_issue(hass, DOMAIN, "restart_required", is_fixable=False,
                              severity=ir.IssueSeverity.WARNING, translation_key="restart_required")
        raise ConfigEntryNotReady("Restart HA to activate the installed password startup hook before setting the gateway password")
    ir.async_delete_issue(hass, DOMAIN, "restart_required")
    entry.async_on_unload(entry.add_update_listener(_entry_updated))
    LOGGER.info("GW2_PASSWORD_PATCH_READY: UI gateway protection loaded")
    return True


async def async_unload_entry(hass, entry):
    return True


async def async_remove_entry(hass, entry):
    refresh_gateways(hass, exclude_entry_id=entry.entry_id)
