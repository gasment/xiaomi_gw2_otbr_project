#include "otbr_host/discovery.hpp"
#include "otbr_host/native_api.hpp"
#include <openthread/error.h>
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <iostream>
#include <net/if.h>

namespace otbr_host {
namespace {
void txt(std::vector<std::uint8_t> &out, const std::string &key, const std::string &value) {
  const auto item = key + "=" + value;
  if (item.size() > 255) return; // Optional labels cannot exceed one DNS TXT string.
  out.push_back(static_cast<std::uint8_t>(item.size()));
  out.insert(out.end(), item.begin(), item.end());
}
}
ApiDiscovery::ApiDiscovery(otInstance *instance, const Config &config, bool proxy)
    : instance_(instance), config_(config), mac_(native_api_device_mac(config)), proxy_(proxy) {
  mac_.erase(std::remove(mac_.begin(), mac_.end(), ':'), mac_.end());
  std::transform(mac_.begin(), mac_.end(), mac_.begin(), [](unsigned char c) { return std::tolower(c); });
}
ApiDiscovery::~ApiDiscovery() { stop(); }
otMdnsService ApiDiscovery::service() {
  otMdnsService out{};
  // A null host name uses the core's local host and its current LAN A/AAAA
  // records, shared with Border Agent. No duplicate hostname/address registry.
  out.mServiceInstance = config_.device_name.c_str();
  out.mServiceType = proxy_ ? "_thread-proxy._tcp" : "_esphomelib._tcp";
  out.mPort = proxy_ ? config_.proxy.port : config_.api_port;
  out.mTxtData = txt_.data();
  out.mTxtDataLength = static_cast<std::uint16_t>(txt_.size());
  return out;
}
void ApiDiscovery::registered(otInstance *, otMdnsRequestId, otError error) {
  std::cerr << "[discovery] service registration " << otThreadErrorToString(error) << '\n';
}
void ApiDiscovery::update(const std::string &backbone, bool api_ready) {
  const auto index = backbone.empty() ? 0 : if_nametoindex(backbone.c_str());
  if (!api_ready || !index || !otMdnsIsEnabled(instance_)) {
    stop(); next_ = {}; return;
  }
  const auto now = std::chrono::steady_clock::now();
  if (backbone == backbone_ && index == index_ && now < next_) return;
  if (active_ && (backbone != backbone_ || index != index_)) stop();
  backbone_ = backbone; index_ = index;
  txt_.clear();
  if(proxy_) {
    txt(txt_,"component","thread_proxy_api");txt(txt_,"version","1");txt(txt_,"id",mac_);
    txt(txt_,"name",config_.device_name);txt(txt_,"encryption",config_.proxy.api_key.empty()?"none":"noise");
  } else {
  txt(txt_, "version", MI_OTBR_HOST_VERSION);
  txt(txt_, "mac", mac_);
  txt(txt_, "friendly_name", config_.friendly_name);
  txt(txt_, "platform", "HOST");
  txt(txt_, "board", "SSD222D-MHCZ01P");
  const bool wifi = backbone.rfind("wl", 0) == 0 ||
      std::filesystem::exists("/sys/class/net/" + backbone + "/wireless");
  txt(txt_, "network", wifi ? "wifi" : "ethernet");
  // Omission means plaintext. Do not advertise key provisioning or publish a PSK.
  if (!config_.api_key.empty()) txt(txt_, "api_encryption", "Noise_NNpsk0_25519_ChaChaPoly_SHA256");
  }
  auto record = service();
  const auto error = otMdnsRegisterService(instance_, &record, ++request_, registered);
  if (error != OT_ERROR_NONE) {
    std::cerr << "[discovery] registration request failed: " << otThreadErrorToString(error) << '\n';
    next_ = now + std::chrono::seconds(5); return;
  }
  if (!active_) std::cerr << "[discovery] Publishing " << config_.device_name
                         << (proxy_ ? "._thread-proxy._tcp.local port=" : "._esphomelib._tcp.local port=")
                         << (proxy_ ? config_.proxy.port : config_.api_port) << " backbone=" << backbone << '\n';
  active_ = true;
  // Refresh handles an independently restarted mDNS engine as well. The core
  // suppresses announcements when an already registered record is unchanged.
  next_ = now + std::chrono::seconds(30);
}
void ApiDiscovery::stop() {
  if (active_ && otMdnsIsEnabled(instance_)) {
    auto record = service(); (void)otMdnsUnregisterService(instance_, &record);
  }
  active_ = false;
}
}
