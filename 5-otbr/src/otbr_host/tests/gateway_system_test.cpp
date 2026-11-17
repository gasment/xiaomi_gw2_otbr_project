#include "otbr_host/gateway_system.hpp"
#include "otbr_host/optimistic_switch.hpp"
#include <sstream>
#include <stdexcept>
#include <iostream>
using namespace otbr_host;
void require(bool value) { if (!value) throw std::runtime_error("gateway system regression"); }
int main() {
  OptimisticSwitchState led;
  require(!led.snapshot(0).available);
  require(led.confirm(0, false, 0));
  const auto old_poll = led.revision();
  led.request(true, 100);
  require(led.snapshot(100).available && led.snapshot(100).boolean);
  require(!led.confirm(old_poll, false, 101)); // Old poll cannot undo the click.
  led.unavailable(old_poll);
  require(led.snapshot(102).available && led.snapshot(102).boolean);
  const auto first_command = led.revision();
  led.request(false, 103);
  require(!led.confirm(first_command, true, 104)); // Rapid on/off stays off.
  require(led.snapshot(104).available && !led.snapshot(104).boolean);
  require(led.confirm(led.revision(), true, 105)); // Current real feedback wins.
  require(led.snapshot(105).boolean);
  led.unavailable(led.revision());
  require(!led.snapshot(106).available); // Never retain a failed optimistic value forever.
  led.request(false, 200);
  require(!led.snapshot(30200).available);
  require(format_gateway_uptime(324120) == "3d:18h:02m");
  require(format_gateway_uptime(0) == "0d:00h:00m");
  require(format_gateway_uptime(100 * 86400ull + 23 * 3600 + 59 * 60) == "100d:23h:59m");
  std::istringstream props("ro.sys.mi_fw_ver=1.0.8\nro.sys.mi_build_num=0013\n");
  require(gateway_firmware_version(props) == "1.0.8_0013");
  std::istringstream missing("unrelated=value\n");
  require(gateway_firmware_version(missing).empty());
  Config config; config.entities["reset"] = {}; config.entities["sys_led"] = {};
  GatewaySystem disabled(config, false);
  require(!disabled.command("reset", false)); require(!disabled.command("sys_led", true));
  require(!disabled.snapshot("").count("sys_led"));
  std::cout << "GATEWAY_SYSTEM_LOGIC_PASS (no OS control or MQTT operation)\n";
}
