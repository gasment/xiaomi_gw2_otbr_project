"""Opt-in, bounded IPv6 multicast test for an existing ESP32-C6 Thread node."""
import ipaddress
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.esp32 import VARIANT_ESP32C6, only_on_variant
from esphome.const import CONF_ID, CONF_PORT
from esphome.core import CORE

DEPENDENCIES = ["esp32", "openthread"]
MULTI_CONF = False
ns = cg.esphome_ns.namespace("thread_multicast_test")
ThreadMulticastTest = ns.class_("ThreadMulticastTest", cg.PollingComponent)

def _group(value):
    value = cv.string_strict(value)
    try: address = ipaddress.IPv6Address(value)
    except ValueError as error: raise cv.Invalid("Expected an IPv6 multicast group") from error
    if not address.is_multicast or not 4 <= (address.packed[1] & 15) <= 14:
        raise cv.Invalid("BBR test requires a multicast scope larger than realm-local (4..14)")
    return str(address)

def _interval(value):
    period = cv.positive_time_period_milliseconds(value)
    if not 1000 <= period.total_milliseconds <= 60000:
        raise cv.Invalid("send_interval must be 1s..60s")
    return period

def _platform(config):
    if not CORE.is_esp32 or CORE.target_framework != "esp-idf":
        raise cv.Invalid("thread_multicast_test requires ESP32-C6 with ESP-IDF")
    return only_on_variant(supported=[VARIANT_ESP32C6])(config)

CONFIG_SCHEMA = cv.All(
    cv.Schema({
        cv.GenerateID(): cv.declare_id(ThreadMulticastTest),
        cv.Optional("group", default="ff15::1234"): _group,
        cv.Optional(CONF_PORT, default=18515): cv.port,
        cv.Optional("send_interval", default="5s"): _interval,
        cv.Optional("send_count", default=10): cv.int_range(min=0, max=50),
    }).extend(cv.polling_component_schema("1s")),
    _platform,
)

async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_group(config["group"]))
    cg.add(var.set_port(config[CONF_PORT]))
    cg.add(var.set_send_interval(config["send_interval"].total_milliseconds))
    cg.add(var.set_send_count(config["send_count"]))
