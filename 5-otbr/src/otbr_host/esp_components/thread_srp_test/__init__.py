"""Opt-in SRP server pinning for a real ESP32-C6 registration test."""
import ipaddress
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.esp32 import VARIANT_ESP32C6, only_on_variant
from esphome.const import CONF_ID, CONF_PORT
from esphome.core import CORE

DEPENDENCIES = ["esp32", "openthread"]
MULTI_CONF = False
ns = cg.esphome_ns.namespace("thread_srp_test")
ThreadSrpTest = ns.class_("ThreadSrpTest", cg.PollingComponent)


def _server(value):
    value = cv.string_strict(value)
    try:
        address = ipaddress.IPv6Address(value)
    except ValueError as error:
        raise cv.Invalid("Expected the selected SRP server IPv6 address") from error
    if '%' in value or address.is_multicast or address.is_unspecified or address.is_loopback or address.is_link_local:
        raise cv.Invalid("Use the gateway mesh-local EID, not multicast, link-local, loopback or an unspecified address")
    return str(address)


def _platform(config):
    if not CORE.is_esp32 or CORE.target_framework != "esp-idf":
        raise cv.Invalid("thread_srp_test requires ESP32-C6 with ESP-IDF")
    return only_on_variant(supported=[VARIANT_ESP32C6])(config)


CONFIG_SCHEMA = cv.All(
    cv.Schema({
        cv.GenerateID(): cv.declare_id(ThreadSrpTest),
        cv.Required("server"): _server,
        cv.Required(CONF_PORT): cv.int_range(min=1, max=65535),
    }).extend(cv.polling_component_schema("1s")),
    _platform,
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_server(config["server"]))
    cg.add(var.set_port(config[CONF_PORT]))
