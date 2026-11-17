#include "otbr_host/config.hpp"
#include <yaml-cpp/yaml.h>
#include <arpa/inet.h>
#include <algorithm>
#include <cctype>
#include <fstream>
#include <iterator>
#include <limits>
#include <set>
#include <regex>
#include <stdexcept>
#include <utility>

namespace otbr_host {
namespace {
using YAML::Node;
[[noreturn]] void fail(const std::string &path, const std::string &reason) {
  throw std::runtime_error(path + ": " + reason);
}
Node read_yaml(const std::string &file) {
  std::ifstream input(file, std::ios::binary);
  if (!input) fail("configuration", "cannot open YAML file");
  input.seekg(0, std::ios::end);
  auto length = input.tellg();
  if (length < 0 || length > 65536) fail("configuration", "file exceeds 64 KiB");
  input.seekg(0);
  std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  try {
    auto docs = YAML::LoadAll(text);
    if (docs.size() != 1) fail("configuration", "exactly one YAML document is required");
    return docs.front();
  } catch (const YAML::Exception &) {
    // YAML exception text may quote secret input. Do not forward it to logs.
    fail("configuration", "invalid YAML syntax");
  }
}
void check_tree(const Node &node, unsigned depth = 0) {
  if (depth > 24) fail("configuration", "nesting or alias depth exceeds 24");
  if (node.IsMap()) {
    std::set<std::string> keys;
    for (const auto &entry : node) {
      if (!entry.first.IsScalar()) fail("configuration", "mapping keys must be scalar");
      if (!keys.insert(entry.first.Scalar()).second) fail("configuration", "duplicate mapping key");
      check_tree(entry.second, depth + 1);
    }
  } else if (node.IsSequence()) {
    for (const auto &entry : node) check_tree(entry, depth + 1);
  }
}
void keys(const Node &node, std::initializer_list<const char *> allowed, const std::string &path) {
  if (!node.IsMap()) fail(path, "expected a mapping");
  for (const auto &entry : node) {
    const auto name = entry.first.Scalar();
    if (std::none_of(allowed.begin(), allowed.end(), [&](const char *s) { return name == s; }))
      fail(path, "unknown or unsupported field (check the Host configuration example)");
  }
}
class Reader {
 public:
  explicit Reader(const std::string &file) : root(read_yaml(file)) {
    check_tree(root);
    auto slash = file.find_last_of('/');
    secrets_file = (slash == std::string::npos ? "" : file.substr(0, slash + 1)) + "secrets.yaml";
    if (root["substitutions"]) keys_substitutions();
  }
  Node value(const Node &node, const std::string &path) {
    if (!node.IsDefined() || node.IsNull()) fail(path, "required value is missing");
    if (node.Tag() == "!secret") {
      if (!node.IsScalar()) fail(path, "!secret expects a scalar key");
      if (!secrets_loaded) {
        secrets = read_yaml(secrets_file); check_tree(secrets);
        if (!secrets.IsMap()) fail("secrets", "expected a mapping");
        secrets_loaded = true;
      }
      Node secret = static_cast<const Node &>(secrets)[node.Scalar()];
      if (!secret || secret.IsNull() || !secret.IsScalar() || secret.Tag() == "!secret")
        fail(path, "secret is missing or is not a scalar");
      return secret;
    }
    if (!node.Tag().empty() && node.Tag()[0] == '!' && node.Tag() != "!")
      fail(path, "unsupported YAML tag");
    return node;
  }
  std::string text(const Node &node, const std::string &path) {
    Node n = value(node, path);
    if (!n.IsScalar()) fail(path, "expected a scalar");
    auto result = n.Scalar();
    if (result.find('\0') != std::string::npos) fail(path, "NUL is not allowed");
    if (node.Tag() == "!secret") return result;
    // Whole-value substitutions only; secret values are never interpolated recursively.
    if (result.size() > 3 && result.substr(0, 2) == "${" && result.back() == '}') {
      Node sub = static_cast<const Node &>(root)["substitutions"][result.substr(2, result.size() - 3)];
      if (!sub || !sub.IsScalar()) fail(path, "substitution is missing or is not scalar");
      result = value(sub, path).Scalar();
      if (result.find('\0') != std::string::npos) fail(path, "NUL is not allowed");
      if (sub.Tag() == "!secret") return result;
    }
    if (result.find("${") != std::string::npos) fail(path, "only whole-value substitutions are supported");
    return result;
  }
  std::string optional(const Node &n, const char *key, const std::string &fallback, const std::string &path) {
    return n[key] ? text(n[key], path + "." + key) : fallback;
  }
  unsigned number(const Node &node, unsigned low, unsigned high, const std::string &path) {
    auto s = text(node, path);
    int base = s.rfind("0x", 0) == 0 ? 16 : 10;
    std::string digits = base == 16 ? s.substr(2) : s;
    if (digits.empty() || !std::all_of(digits.begin(), digits.end(), [base](unsigned char c) {
          return base == 16 ? std::isxdigit(c) != 0 : std::isdigit(c) != 0;
        })) fail(path, "expected an unsigned decimal or 0x integer");
    try {
      auto v = std::stoull(digits, nullptr, base);
      if (v >= low && v <= high) return static_cast<unsigned>(v);
    } catch (const std::exception &) {}
    fail(path, "integer is outside the allowed range");
  }
  int signed_number(const Node &node, int low, int high, const std::string &path) {
    const auto s = text(node, path);
    const auto start = !s.empty() && s[0] == '-' ? 1U : 0U;
    if (s.size() <= start || !std::all_of(s.begin() + start, s.end(), [](unsigned char ch) {
          return std::isdigit(ch) != 0;
        })) fail(path, "expected an integer dBm value without units");
    try {
      const auto v = std::stoll(s);
      if (v >= low && v <= high) return static_cast<int>(v);
    } catch (const std::exception &) {}
    fail(path, "output power must be between -26 and 20 dBm");
  }
  bool boolean(const Node &node, const std::string &path) {
    auto s = text(node, path);
    if (s == "true") return true;
    if (s == "false") return false;
    fail(path, "expected true or false");
  }
  Node root;
 private:
  void keys_substitutions() {
    if (!root["substitutions"].IsMap()) fail("substitutions", "expected a mapping");
    for (const auto &entry : root["substitutions"])
      if (!entry.second.IsScalar()) fail("substitutions", "only scalar substitutions are supported");
  }
  Node secrets;
  std::string secrets_file;
  bool secrets_loaded{false};
};
bool identifier(const std::string &s, std::size_t max = 64) {
  return !s.empty() && s.size() <= max && std::all_of(s.begin(), s.end(), [](unsigned char c) {
    return std::isalnum(c) || c == '_' || c == '-' || c == '.';
  });
}
void interface_name(const std::string &s, const std::string &path) {
  if (!identifier(s, 15)) fail(path, "invalid Linux interface name");
}
std::string hex(Reader &r, const Node &n, unsigned bytes, const std::string &path) {
  auto s = r.text(n, path);
  if (s.rfind("0x", 0) == 0) s.erase(0, 2);
  if (s.empty() || s.size() > bytes * 2 || !std::all_of(s.begin(), s.end(), [](unsigned char c) { return std::isxdigit(c); }))
    fail(path, "invalid hexadecimal value");
  // Preserve the original ESPHome numeric 0x input convention and leading zeroes.
  s.insert(0, bytes * 2 - s.size(), '0');
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return s;
}
std::string prefix(Reader &r, const Node &n, const std::string &path) {
  auto s = r.text(n, path);
  if (s.size() < 4 || s.substr(s.size() - 3) != "/64") fail(path, "expected an fd00::/8 ULA /64");
  in6_addr address{};
  if (inet_pton(AF_INET6, s.substr(0, s.size() - 3).c_str(), &address) != 1 || address.s6_addr[0] != 0xfd)
    fail(path, "expected an fd00::/8 ULA /64");
  for (unsigned i = 8; i < 16; ++i) if (address.s6_addr[i]) fail(path, "prefix contains nonzero host bits");
  char formatted[INET6_ADDRSTRLEN];
  if (!inet_ntop(AF_INET6, &address, formatted, sizeof(formatted))) fail(path, "invalid IPv6 prefix");
  return std::string(formatted) + "/64";
}
unsigned duration(Reader &r, const Node &node, const std::string &path) {
  auto s = r.text(node, path);
  unsigned multiplier = 1;
  if (s.size() > 2 && s.substr(s.size() - 2) == "ms") s.resize(s.size() - 2);
  else if (s.size() > 1 && s.back() == 's') { s.pop_back(); multiplier = 1000; }
  else fail(path, "use an integer duration ending in ms or s");
  return r.number(Node(s), 1, 3600000 / multiplier, path) * multiplier;
}
EntityConfig entity(Reader &r, const Node &node, const std::string &kind) {
  keys(node, {"id", "name", "icon", "entity_category"}, kind);
  EntityConfig e;
  e.id = r.optional(node, "id", kind, kind);
  e.name = r.optional(node, "name", kind, kind);
  e.icon = r.optional(node, "icon", "", kind);
  e.category = r.optional(node, "entity_category", kind == "reset" || kind == "sys_led" ? "config" : "diagnostic", kind);
  if (!identifier(e.id)) fail(kind, "invalid entity id");
  if (e.category != "diagnostic" && e.category != "config" && !e.category.empty()) fail(kind, "invalid entity category");
  return e;
}
}
Config load_config(const std::string &filename) {
  Reader r(filename); auto root = r.root;
  keys(root, {"device", "api", "substitutions", "thread_br", "thread_proxy_api"}, "root");
  Config c;
  auto device = root["device"];
  keys(device, {"name", "friendly_name", "mac_address"}, "device");
  c.device_name = r.text(device["name"], "device.name");
  if (!identifier(c.device_name, 63)) fail("device.name", "invalid stable device name");
  c.friendly_name = r.optional(device, "friendly_name", c.device_name, "device");
  c.mac_address = r.optional(device, "mac_address", "", "device");
  if (!c.mac_address.empty()) {
    bool valid = c.mac_address.size() == 17, nonzero = false;
    for (std::size_t i = 0; i < c.mac_address.size() && valid; ++i) {
      if (i % 3 == 2) valid = c.mac_address[i] == ':';
      else { valid = std::isxdigit(static_cast<unsigned char>(c.mac_address[i])) != 0; nonzero |= c.mac_address[i] != '0'; }
    }
    if (!valid || !nonzero || (std::stoul(c.mac_address.substr(0, 2), nullptr, 16) & 1))
      fail("device.mac_address", "expected a nonzero unicast MAC in xx:xx:xx:xx:xx:xx form");
  }
  auto api = root["api"];
  keys(api, {"port", "encryption"}, "api");
  if (api["port"]) c.api_port = r.number(api["port"], 1, 65535, "api.port");
  if (api["encryption"]) {
  keys(api["encryption"], {"key"}, "api.encryption");
  c.api_key = r.text(api["encryption"]["key"], "api.encryption.key");
  const std::string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  if (c.api_key.size() != 44 || c.api_key.back() != '=' ||
      !std::all_of(c.api_key.begin(), c.api_key.end() - 1, [&](char ch) { return alphabet.find(ch) != std::string::npos; }) ||
      (alphabet.find(c.api_key[42]) & 3) != 0) fail("api.encryption.key", "expected a canonical base64-encoded 32-byte key");
  if (c.api_key == std::string(43, 'A') + "=") fail("api.encryption.key", "all-zero provisioning key is not permitted");
  }
  auto br = root["thread_br"];
  keys(br, {"id", "backbone", "backbone_config", "radio", "output_power", "rcp", "rcp_connectivity", "ha_url", "ha_token", "ha_ca_file", "commissioner", "web", "used_psram", "thread_network_config", "thread_identity", "thread_attached", "thread_role", "rcp_version", "radio_version", "rloc16", "neighbor_count", "child_count", "thread_interface", "state_directory", "update_interval", "ipv4", "uptime", "reset", "fw_ver", "sys_led"}, "thread_br");
  c.id = r.optional(br, "id", "thread_br_main", "thread_br");
  if (!identifier(c.id)) fail("thread_br.id", "invalid id");
  const bool inline_backbone = br["backbone"] && br["backbone"].IsMap();
  c.backbone = inline_backbone ? "auto" : r.optional(br, "backbone", "auto", "thread_br");
  if (c.backbone != "auto") fail("thread_br.backbone", "Host uses auto; optional candidates go under backbone_config");
  if (inline_backbone && br["backbone_config"]) fail("thread_br.backbone", "use backbone mapping or backbone_config, not both");
  if (auto b = inline_backbone ? br["backbone"] : br["backbone_config"]) {
    keys(b, {"interfaces", "policy", "switch_delay"}, "thread_br.backbone_config");
    c.backbone_policy = r.optional(b, "policy", "follow_default_route", "thread_br.backbone_config");
    if (c.backbone_policy != "follow_default_route" && c.backbone_policy != "keep_current") fail("backbone_config.policy", "unsupported policy");
    if (b["switch_delay"]) c.switch_delay_ms = duration(r, b["switch_delay"], "backbone_config.switch_delay");
    if (auto interfaces = b["interfaces"]) {
      if (!interfaces.IsSequence()) fail("backbone_config.interfaces", "expected a sequence");
      for (const auto &n : interfaces) {
        auto name = r.text(n, "backbone_config.interfaces"); interface_name(name, "backbone_config.interfaces");
        if (std::find(c.candidates.begin(), c.candidates.end(), name) != c.candidates.end()) fail("backbone_config.interfaces", "duplicate interface");
        c.candidates.push_back(name);
      }
    }
  }
  c.radio = r.optional(br, "radio", "uart_rcp", "thread_br");
  if (c.radio != "uart_rcp") fail("thread_br.radio", "this Host target requires uart_rcp");
  if (br["output_power"]) c.output_power = r.signed_number(br["output_power"], -26, 20, "thread_br.output_power");
  c.thread_interface = r.optional(br, "thread_interface", "wpan0", "thread_br"); interface_name(c.thread_interface, "thread_interface");
  if (c.thread_interface == "lo" || std::find(c.candidates.begin(), c.candidates.end(), c.thread_interface) != c.candidates.end()) fail("thread_interface", "cannot also be a backbone interface");
  c.state_directory = r.optional(br, "state_directory", "/data/otbr/state", "thread_br");
  if (c.state_directory.empty() || c.state_directory[0] != '/') fail("state_directory", "expected an absolute path");
  if (br["update_interval"]) c.update_interval_ms = duration(r, br["update_interval"], "update_interval");
  auto uart = br["rcp"];
  if (!uart.IsDefined()) uart = Node(YAML::NodeType::Map);
  keys(uart, {"device", "baud_rate", "flow_control", "rcp_connectivity"}, "thread_br.rcp (replace ESP32 GPIO fields with device/baud_rate/flow_control)");
  c.uart_device = r.optional(uart, "device", "/dev/ttyS1", "rcp");
  if (c.uart_device.rfind("/dev/", 0) != 0) fail("rcp.device", "expected an absolute /dev path");
  if (uart["baud_rate"]) c.baud_rate = r.number(uart["baud_rate"], 9600, 4000000, "rcp.baud_rate");
  c.flow_control = r.optional(uart, "flow_control", "hardware", "rcp");
  if (c.flow_control != "hardware") fail("rcp.flow_control", "validated MHCZ01P firmware requires hardware RTS/CTS");
  c.ha_url = r.optional(br, "ha_url", "", "thread_br");
  c.ha_token = r.optional(br, "ha_token", "", "thread_br");
  c.ha_ca_file = r.optional(br, "ha_ca_file", c.ha_ca_file, "thread_br");
  if (c.ha_url.empty() != c.ha_token.empty()) fail("thread_br", "ha_url and ha_token must be supplied together");
  if (!c.ha_url.empty()) {
    const std::regex pattern(R"(^(https?)://(\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+)(:([0-9]{1,5}))?(/[^?#\r\n]*)?$)");
    std::smatch match;
    if (!std::regex_match(c.ha_url, match, pattern)) fail("ha_url", "expected HTTP(S) origin with optional base path, without credentials/query/fragment");
    if (match[4].matched && (std::stoul(match[4].str()) == 0 || std::stoul(match[4].str()) > 65535)) fail("ha_url", "port outside 1..65535");
    c.ha_origin = match[1].str() + "://" + match[2].str() + match[3].str();
    c.ha_path = match[5].str();
    while (!c.ha_path.empty() && c.ha_path.back() == '/') c.ha_path.pop_back();
    c.ha_path += "/api/template";
    if (std::any_of(c.ha_token.begin(), c.ha_token.end(), [](unsigned char ch) { return ch < 32 || ch == 127; })) fail("ha_token", "control characters not allowed");
    if (c.ha_ca_file.empty() || c.ha_ca_file.front() != '/') fail("ha_ca_file", "expected an absolute certificate file path");
  }
  if (auto commissioner = br["commissioner"]) {
    keys(commissioner, {"enabled", "commissioner_id"}, "commissioner");
    if (commissioner["enabled"]) c.commissioner_enabled = r.boolean(commissioner["enabled"], "commissioner.enabled");
    c.commissioner_id = r.optional(commissioner, "commissioner_id", "", "commissioner");
    if (c.commissioner_enabled && !identifier(c.commissioner_id)) fail("commissioner_id", "required when commissioner is enabled");
  }
  auto web = br["web"];
  keys(web, {"port", "user", "passwd"}, "web");
  if (web["port"]) c.web_port = r.number(web["port"], 1, 65535, "web.port");
  c.web_user = r.optional(web, "user", "", "web"); c.web_password = r.optional(web, "passwd", "", "web");
  if (c.web_user.empty() || c.web_password.empty() || c.web_user.find(':') != std::string::npos) fail("web", "user and passwd are required; user cannot contain ':'");
  if (c.api_port == c.web_port) fail("web.port", "conflicts with Native API port");
  if (br["used_psram"]) {
    (void)r.boolean(br["used_psram"], "used_psram");
    c.warnings.push_back("used_psram is a compatibility field; Linux uses normal process memory");
  }
  auto network = br["thread_network_config"];
  keys(network, {"channel", "network_name", "network_key", "pan_id", "ext_pan_id", "pskc", "mesh_local_prefix", "omr_prefix", "force_dataset"}, "thread_network_config");
  c.channel = r.number(network["channel"], 11, 26, "network.channel");
  c.network_name = r.text(network["network_name"], "network.network_name");
  if (c.network_name.empty() || c.network_name.size() > 16) fail("network.network_name", "expected 1..16 UTF-8 bytes");
  c.network_key = hex(r, network["network_key"], 16, "network.network_key");
  c.pan_id = r.number(network["pan_id"], 0, 65534, "network.pan_id");
  c.ext_pan_id = hex(r, network["ext_pan_id"], 8, "network.ext_pan_id");
  c.pskc = hex(r, network["pskc"], 16, "network.pskc");
  c.mesh_local_prefix = prefix(r, network["mesh_local_prefix"], "network.mesh_local_prefix");
  if (network["omr_prefix"]) c.omr_prefix = prefix(r, network["omr_prefix"], "network.omr_prefix");
  if (c.omr_prefix == c.mesh_local_prefix) fail("network.omr_prefix", "must differ from mesh_local_prefix");
  if (network["force_dataset"]) c.force_dataset = r.boolean(network["force_dataset"], "network.force_dataset");
  std::set<std::string> entity_ids;
  auto add = [&](const std::string &kind, const Node &n) {
    auto e = entity(r, n, kind);
    if (!entity_ids.insert(e.id).second) fail("entities", "duplicate entity id");
    c.entities.emplace(kind, std::move(e));
  };
  if (br["rcp_connectivity"] && uart["rcp_connectivity"]) fail("rcp_connectivity", "configure once, directly under thread_br or in the legacy rcp block");
  if (br["rcp_connectivity"]) add("rcp_connectivity", br["rcp_connectivity"]);
  else if (uart["rcp_connectivity"]) add("rcp_connectivity", uart["rcp_connectivity"]);
  for (const char *kind : {"thread_identity", "thread_attached", "thread_role", "rcp_version", "radio_version", "rloc16", "neighbor_count", "child_count", "ipv4", "uptime", "reset", "fw_ver", "sys_led"})
    if (br[kind]) add(kind, br[kind]);
  if (root["thread_proxy_api"].IsDefined()) {
    const auto proxy=root["thread_proxy_api"];
    keys(proxy,{"port","max_connections","status_interval","encryption","udp"},"thread_proxy_api");
    c.proxy.enabled=true;
    if(proxy["port"])c.proxy.port=r.number(proxy["port"],1,65535,"thread_proxy_api.port");
    if(c.proxy.port==c.api_port || c.proxy.port==c.web_port)fail("thread_proxy_api.port","conflicts with Native API or Web port");
    if(proxy["max_connections"])c.proxy.max_connections=r.number(proxy["max_connections"],1,4,"thread_proxy_api.max_connections");
    if(proxy["status_interval"]) {
      auto value=r.text(proxy["status_interval"],"thread_proxy_api.status_interval");
      if(value.size()>3 && value.substr(value.size()-3)=="min")
        c.proxy.status_interval_ms=r.number(Node(value.substr(0,value.size()-3)),1,5,"thread_proxy_api.status_interval")*60000;
      else c.proxy.status_interval_ms=duration(r,proxy["status_interval"],"thread_proxy_api.status_interval");
      if(c.proxy.status_interval_ms<1000 || c.proxy.status_interval_ms>300000)fail("thread_proxy_api.status_interval","expected 1s..5min");
    }
    auto encryption_key=[&](const Node &encryption,const std::string &path) {
      keys(encryption,{"key"},path);
      const auto value=r.text(encryption["key"],path+".key");
      const std::string alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
      if(value.size()!=44 || value.back()!='=' ||
         !std::all_of(value.begin(),value.end()-1,[&](char ch){return alphabet.find(ch)!=std::string::npos;}) ||
         (alphabet.find(value[42])&3)!=0 || value==std::string(43,'A')+"=")
        fail(path+".key","expected a nonzero canonical base64-encoded 32-byte key");
      return value;
    };
    if(proxy["encryption"].IsDefined())c.proxy.api_key=encryption_key(proxy["encryption"],"thread_proxy_api.encryption");
    if(proxy["udp"].IsDefined()) {
      const auto udp=proxy["udp"];keys(udp,{"queue_groups","queue_bytes","encryption"},"thread_proxy_api.udp");
      if(udp["queue_groups"])c.proxy.queue_groups=r.number(udp["queue_groups"],1,128,"thread_proxy_api.udp.queue_groups");
      if(udp["queue_bytes"])c.proxy.queue_bytes=r.number(udp["queue_bytes"],32768,1048576,"thread_proxy_api.udp.queue_bytes");
      if(udp["encryption"].IsDefined())c.proxy.udp_key=encryption_key(udp["encryption"],"thread_proxy_api.udp.encryption");
    }
  }
  return c;
}
}
