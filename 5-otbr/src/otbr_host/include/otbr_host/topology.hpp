#pragma once
#include "otbr_host/web.hpp"
#include <openthread/netdiag.h>
#include <array>
#include <chrono>
#include <map>
#include <vector>

namespace otbr_host {
struct TopologyNode {
  std::uint16_t rloc{0xffff};
  std::string json;
  std::vector<std::uint16_t> children;
};
TopologyNode diagnostic_node(otInstance *instance, const otMessage *message);
class TopologyManager {
 public:
  explicit TopologyManager(otInstance *instance);
  ~TopologyManager() { stop(); }
  TopologyManager(const TopologyManager &) = delete;
  TopologyManager &operator=(const TopologyManager &) = delete;
  void request(const WebRequest &request, WebCompletion done);
  void tick();
  void stop();
 private:
  static TopologyManager *current_;
  static void response(otError, otMessage *, const otMessageInfo *, void *);
  otInstance *instance_;
  WebCompletion completion_;
  std::map<std::uint16_t, std::string> nodes_;
  std::vector<std::uint16_t> children_;
  std::array<bool, 64> routers_{};
  std::array<std::uint8_t, 8> network_{}, mesh_prefix_{};
  std::uint32_t partition_{0};
  unsigned expected_{0}, router_count_{0}, child_next_{0}, query_errors_{0};
  std::size_t bytes_{0};
  bool wrapped_{true}, truncated_{false};
  std::chrono::steady_clock::time_point started_, last_response_, last_child_;
  void receive(otMessage *message);
  void finish(WebReply reply);
  WebReply result(bool timed_out);
};
}
