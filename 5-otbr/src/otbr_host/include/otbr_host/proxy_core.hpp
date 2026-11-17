#pragma once
#include "otbr_host/config.hpp"
#include <array>
#include <atomic>
#include <cstdint>
#include <cstddef>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace otbr_host {
using ProxyBytes = std::vector<std::uint8_t>;
using ProxyHeader = std::array<std::uint8_t, 48>;
struct ProxyPeer {
  std::array<std::uint8_t, 16> address{}, local{};
  std::uint16_t port{6064};
  bool operator==(const ProxyPeer &b) const { return address == b.address && local == b.local && port == b.port; }
};
struct ProxyDatagram {
  ProxyPeer peer;
  std::array<std::uint8_t, 832> bytes{};
  std::uint16_t size{0};
};
struct ProxyOutgoing { ProxyPeer peer; ProxyBytes bytes; };
struct ProxyGroup { ProxyHeader header{}; ProxyBytes body; std::string delivery; };
struct ProxyStatus {
  bool available{false}, attached{false}, ready{false};
  std::string network_id, partition_id, role{"disabled"};
  unsigned nodes{0}, queued{0};
};
std::string proxy_hex(const std::uint8_t *data, std::size_t size);
// Wire codec shared by runtime and deterministic protocol tests. Plaintext is
// accepted only in plaintext mode. Nonce=header[12:24], AAD=entire 48-byte header.
bool proxy_decode(const ProxyBytes &packet, const std::string &base64_key, ProxyHeader &header, ProxyBytes &body);
ProxyBytes proxy_encode(const ProxyHeader &header, const ProxyBytes &body, const std::string &base64_key);
class ProxyCore {
 public:
  ProxyCore(const ProxyConfig &config, std::function<void()> wakeup = {});
  ~ProxyCore();
  ProxyCore(const ProxyCore &) = delete;
  ProxyCore &operator=(const ProxyCore &) = delete;
  bool ingest(const ProxyDatagram &packet); // Bounded nonblocking callback handoff.
  bool request_schema(const std::string &mac);
  std::vector<ProxyOutgoing> outgoing();
  std::shared_ptr<const ProxyGroup> head() const;
  bool acknowledge(const std::string &delivery);
  bool claim(std::uint64_t client);
  void release(std::uint64_t client);
  void set_status(ProxyStatus status);
  ProxyStatus status() const;
  void stop();
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
void run_proxy_tcp(const Config &config, ProxyCore &core, std::atomic<bool> &stop, std::atomic<bool> &ready);
}
