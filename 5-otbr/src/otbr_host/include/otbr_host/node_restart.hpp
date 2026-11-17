#pragma once
#include "otbr_host/restart_protocol.hpp"
#include "otbr_host/topology.hpp"
#include <openthread/udp.h>
#include <memory>
namespace otbr_host {
// Remote EHR1 node restart only. Never resets the BR or its Thread interface.
// Every method/callback runs on the OpenThread owner thread.
class NodeRestartManager {
 public:
  NodeRestartManager(otInstance *instance, TopologyManager &topology)
      : instance_(instance), topology_(topology) {}
  ~NodeRestartManager() { lifetime_.reset(); stop(); }
  NodeRestartManager(const NodeRestartManager &) = delete;
  NodeRestartManager &operator=(const NodeRestartManager &) = delete;
  void request(const WebRequest &, WebCompletion);
  void tick();
  void stop();
 private:
  void diagnosed(WebReply);
  void send();
  void finish(WebReply);
  bool same_network() const;
  static void receive(void *, otMessage *, const otMessageInfo *);
  otInstance *instance_;
  TopologyManager &topology_;
  WebCompletion completion_;
  otUdpSocket socket_{};
  otIp6Address destination_{};
  RestartPacket packet_{};
  std::array<std::uint8_t, 8> ext_{}, network_{}, prefix_{};
  std::shared_ptr<int> lifetime_{std::make_shared<int>(0)};
  std::uint64_t generation_{0};
  std::uint32_t partition_{0};
  std::uint16_t rloc_{0};
  bool opened_{false}, sent_{false}, accepted_{false};
  std::chrono::steady_clock::time_point deadline_;
};
}
