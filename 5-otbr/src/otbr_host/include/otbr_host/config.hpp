#pragma once
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include <iosfwd>

namespace otbr_host {
struct EntityConfig {
  std::string id, name, icon, category;
};
struct ProxyConfig {
  bool enabled{false};
  std::uint16_t port{6065};
  unsigned max_connections{2}, status_interval_ms{30000};
  unsigned queue_groups{16}, queue_bytes{131072};
  std::string api_key, udp_key;
};
struct Config {
  ProxyConfig proxy;
  std::string device_name, friendly_name, mac_address;
  std::uint16_t api_port{6053}, web_port{8080};
  std::string api_key, web_user, web_password, ha_url, ha_token;
  std::string ha_origin, ha_path, ha_ca_file{"/data/otbr/certs/ca-certificates.crt"};
  std::string id, backbone{"auto"}, radio{"uart_rcp"};
  std::vector<std::string> candidates;
  std::string backbone_policy{"follow_default_route"};
  unsigned switch_delay_ms{3000};
  std::string uart_device{"/dev/ttyS1"}, flow_control{"none"};
  unsigned baud_rate{115200};
  std::optional<int> output_power; // Requested dBm; absent means keep RCP default.
  bool commissioner_enabled{false}, force_dataset{false};
  std::string commissioner_id;
  unsigned channel{20}, pan_id{};
  std::string network_name, network_key, ext_pan_id, pskc, mesh_local_prefix, omr_prefix;
  std::string thread_interface{"wpan0"}, state_directory{"/data/otbr/state"};
  unsigned update_interval_ms{15000};
  std::map<std::string, EntityConfig> entities;
  std::vector<std::string> warnings;
  bool runtime_web{false};
};
// Parses and validates only. Never opens the UART, creates interfaces or prints secrets.
Config load_config(const std::string &filename);
// 0=schema and implemented feature set ready; 3=valid schema, pending feature.
// Never prints credentials or performs hardware/network operations.
int report_config(std::ostream &out, const Config &config);
}
