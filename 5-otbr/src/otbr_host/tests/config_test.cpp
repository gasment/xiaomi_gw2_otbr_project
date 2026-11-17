#include "otbr_host/config.hpp"
#include <yaml-cpp/yaml.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unistd.h>
namespace fs = std::filesystem;
void require(bool x, const char *reason) { if (!x) throw std::runtime_error(reason); }
int main(int argc, char **argv) {
  if (argc != 3) return 2;
  char pattern[] = "/tmp/mi-otbr-config-test-XXXXXX";
  const char *dir = mkdtemp(pattern);
  if (!dir) return 1;
  const fs::path base(dir), target = base / "config.yaml";
  try {
    fs::copy_file(argv[2], base / "secrets.yaml");
    auto original = YAML::LoadFile(argv[1]);
    auto write = [&](const YAML::Node &node) { std::ofstream out(target); out << node; };
    write(original);
    auto c = otbr_host::load_config(target.string());
    require(c.backbone == "auto" && c.switch_delay_ms == 3000, "auto backbone config");
    require(c.web_password == "CHANGE-ME", "substitution to secret resolution");
    require(c.entities.at("thread_identity").icon == "mdi:identifier", "entity metadata retained");
    require(c.network_key == "00112233445566778899aabbccddeeff", "leading zeroes retained");
    auto minimal = YAML::Clone(original);
    minimal["thread_br"]["rcp_connectivity"] = minimal["thread_br"]["rcp"]["rcp_connectivity"];
    minimal["thread_br"].remove("rcp"); write(minimal);
    auto defaults = otbr_host::load_config(target.string());
    require(defaults.uart_device == "/dev/ttyS1" && defaults.baud_rate == 460800 && defaults.flow_control == "hardware", "omitted RCP block uses gateway defaults");
    require(defaults.entities.at("rcp_connectivity").id == c.entities.at("rcp_connectivity").id, "top-level connectivity metadata retained");
    minimal["api"].remove("encryption");
    minimal["thread_br"]["backbone"] = YAML::Clone(minimal["thread_br"]["backbone_config"]);
    minimal["thread_br"].remove("backbone_config");
    for (const char *key : {"id", "thread_interface", "state_directory", "update_interval", "radio"}) minimal["thread_br"].remove(key);
    write(minimal);
    auto plain = otbr_host::load_config(target.string());
    require(plain.api_key.empty(), "omitted encryption selects plaintext API");
    require(plain.backbone == "auto" && plain.switch_delay_ms == c.switch_delay_ms && plain.candidates == c.candidates, "backbone mapping preserves dynamic selection");
    require(!plain.output_power, "omitted power must not override RCP");
    require(!plain.proxy.enabled, "absent proxy must stay disabled");
    auto proxy_config = YAML::Clone(original);
    proxy_config["thread_proxy_api"] = YAML::Node(YAML::NodeType::Map);
    write(proxy_config);
    auto proxy = otbr_host::load_config(target.string()).proxy;
    require(proxy.enabled && proxy.port == 6065 && proxy.queue_groups == 16 && proxy.queue_bytes == 131072, "proxy defaults");
    proxy_config["thread_proxy_api"]["status_interval"] = "5min";
    proxy_config["thread_proxy_api"]["encryption"]["key"] = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=";
    proxy_config["thread_proxy_api"]["udp"]["encryption"]["key"] = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=";
    write(proxy_config);proxy = otbr_host::load_config(target.string()).proxy;
    require(proxy.status_interval_ms == 300000 && !proxy.api_key.empty() && !proxy.udp_key.empty(), "independent proxy keys");
    for (const char *field : {"port", "max_connections", "status_interval", "queue_groups", "queue_bytes", "key"}) {
      auto invalid = YAML::Clone(proxy_config);
      if (std::string(field) == "port") invalid["thread_proxy_api"]["port"] = plain.api_port;
      else if (std::string(field) == "key") invalid["thread_proxy_api"]["udp"]["encryption"]["key"] = std::string(43,'A')+"=";
      else if (std::string(field) == "queue_groups" || std::string(field) == "queue_bytes") invalid["thread_proxy_api"]["udp"][field] = 0;
      else invalid["thread_proxy_api"][field] = 0;
      write(invalid);bool rejected=false;
      try { (void)otbr_host::load_config(target.string()); } catch(const std::exception &) { rejected=true; }
      require(rejected, "invalid proxy configuration accepted");
    }
    auto system_entities = YAML::Clone(original);
    for (const char *kind : {"ipv4", "uptime", "reset", "fw_ver", "sys_led"})
      system_entities["thread_br"][kind]["name"] = kind;
    write(system_entities);
    auto configured = otbr_host::load_config(target.string());
    for (const char *kind : {"ipv4", "uptime", "reset", "fw_ver", "sys_led"})
      require(configured.entities.at(kind).id == kind, "gateway entity ID default");
    require(configured.entities.at("reset").category == "config", "restart config category");
    require(configured.entities.at("sys_led").category == "config", "LED config category");
    for (int power : {-26, -1, 0, 5, 20}) {
      auto powered = YAML::Clone(original);
      powered["thread_br"]["output_power"] = power;
      write(powered);
      require(otbr_host::load_config(target.string()).output_power == power, "signed requested power retained");
    }
    unsigned rejected = 0;
    auto bad = [&](YAML::Node node) {
      write(node);
      try { (void)otbr_host::load_config(target.string()); }
      catch (const std::exception &e) {
        require(std::string(e.what()).find("0011223344556677") == std::string::npos, "secret leaked in error");
        ++rejected; return;
      }
      throw std::runtime_error("invalid config accepted");
    };
    for (const char *power : {"-27", "21", "5.5", "20 dBm", "true", "", "999999999999999999999999999999"}) {
      auto invalid = YAML::Clone(original);
      invalid["thread_br"]["output_power"] = power;
      bad(invalid);
    }
    auto invalid_power = YAML::Clone(original);
    invalid_power["thread_br"]["output_power"] = YAML::Node(YAML::NodeType::Null); bad(invalid_power);
    invalid_power = YAML::Clone(original);
    invalid_power["thread_br"]["output_power"] = YAML::Node(YAML::NodeType::Map); bad(invalid_power);
    auto n = YAML::Clone(original); n["thread_br"]["thread_network_config"]["channel"] = 27; bad(n);
    n = YAML::Clone(original); n["thread_br"]["thread_network_config"]["omr_prefix"] = "fd11:2233:4455:6677::/64"; bad(n);
    n = YAML::Clone(original); n["thread_br"]["rcp"]["uart_tx"] = "GPIO18"; bad(n);
    n = YAML::Clone(original); n["api"]["encryption"]["key"] = "invalid"; bad(n);
    n = YAML::Clone(original); n["api"]["encryption"]["key"] = std::string(43, 'A') + "="; bad(n);
    n = YAML::Clone(original); n["thread_br"]["thread_network_config"]["mesh_local_prefix"] = "fd11:2233:4455:6677::1/64"; bad(n);
    n = YAML::Clone(original); n["thread_br"]["neighbor_count"]["id"] = "thread_identity"; bad(n);
    n = YAML::Clone(original); n["device"]["mac_address"] = "invalid"; bad(n);
    write(original); { std::ofstream out(target, std::ios::app); out << "\ndevice: {}\n"; }
    try { (void)otbr_host::load_config(target.string()); throw std::runtime_error("duplicate accepted"); }
    catch (const std::exception &e) { require(std::string(e.what()).find("duplicate mapping key") != std::string::npos, "duplicate rejection"); }
    require(rejected == 17, "rejection cases not executed");
    fs::remove_all(base);
    std::cout << "CONFIG_PARSER_TEST_PASS\n";
    return 0;
  } catch (const std::exception &e) {
    fs::remove_all(base); std::cerr << "TEST_FAILED: " << e.what() << '\n'; return 1;
  }
}
