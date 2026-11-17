#include "otbr_host/topology.hpp"
#include <openthread/thread.h>
#include <openthread/thread_ftd.h>
#include <algorithm>
#include <cstring>
#include <stdexcept>

namespace otbr_host {
namespace {
using Clock = std::chrono::steady_clock;
constexpr std::uint8_t router_types[] = {0, 1, 2, 3, 5, 6, 8, 16};
constexpr std::uint8_t child_types[] = {0, 1, 2, 3, 8};
constexpr unsigned max_nodes = 192, max_children = 128;
constexpr std::size_t max_bytes = 256 * 1024, max_node_bytes = 16 * 1024;
}
TopologyManager *TopologyManager::current_ = nullptr;
TopologyManager::TopologyManager(otInstance *instance) : instance_(instance) {
  if (current_) throw std::runtime_error("Only one topology manager is supported");
  current_ = this;
}
void TopologyManager::request(const WebRequest &request, WebCompletion done) {
  if (request.method != "GET" && request.method != "HEAD") { done(web_error(405, "Method not allowed")); return; }
  if (completion_) { done(web_error(409, "Topology scan already in progress")); return; }
  if (otThreadGetDeviceRole(instance_) < OT_DEVICE_ROLE_CHILD) {
    done(web_error(409, "Thread is not attached")); return;
  }
  nodes_.clear(); children_.clear(); routers_.fill(false);
  bytes_ = expected_ = router_count_ = child_next_ = query_errors_ = 0;
  truncated_ = false; wrapped_ = request.path == "/topology";
  std::copy_n(otThreadGetExtendedPanId(instance_)->m8, 8, network_.begin());
  std::copy_n(otThreadGetMeshLocalPrefix(instance_)->m8, 8, mesh_prefix_.begin());
  partition_ = otThreadGetPartitionId(instance_);
  otRouterInfo info{};
  for (unsigned id = 0; id <= otThreadGetMaxRouterId(instance_); ++id)
    if (otThreadGetRouterInfo(instance_, static_cast<std::uint16_t>(id), &info) == OT_ERROR_NONE) ++expected_;
  started_ = last_response_ = last_child_ = Clock::now();
  completion_ = std::move(done);
  otIp6Address multicast{};
  if (otIp6AddressFromString("ff03::2", &multicast) != OT_ERROR_NONE) {
    finish(web_error(500, "Invalid diagnostic multicast address")); return;
  }
  const auto *local = otThreadGetRloc(instance_);
  if (!local) { finish(web_error(503, "Thread RLOC unavailable")); return; }
  // Callback gate has process lifetime. No raw manager pointer is retained by
  // OpenThread after this manager stops, including outstanding CoAP requests.
  if (otThreadSendDiagnosticGet(instance_, local, router_types, sizeof(router_types), response, nullptr) != OT_ERROR_NONE) ++query_errors_;
  if (otThreadSendDiagnosticGet(instance_, &multicast, router_types, sizeof(router_types), response, nullptr) != OT_ERROR_NONE) ++query_errors_;
  if (query_errors_ == 2) finish(web_error(503, "Failed to queue diagnostic requests"));
}
void TopologyManager::response(otError error, otMessage *message, const otMessageInfo *, void *) {
  auto *self = current_;
  if (!self || !self->completion_) return;
  if (error != OT_ERROR_NONE || !message) return;
  try { self->receive(message); }
  catch (...) { ++self->query_errors_; self->truncated_ = true; }
}
void TopologyManager::receive(otMessage *message) {
  auto node = diagnostic_node(instance_, message);
  if (node.rloc == 0xffff) { ++query_errors_; return; }
  auto existing = nodes_.find(node.rloc);
  const auto old_bytes = existing == nodes_.end() ? 0 : existing->second.size();
  if ((existing == nodes_.end() && nodes_.size() >= max_nodes) || node.json.size() > max_node_bytes ||
      bytes_ - old_bytes + node.json.size() > max_bytes) { truncated_ = true; return; }
  bytes_ = bytes_ - old_bytes + node.json.size();
  nodes_[node.rloc] = std::move(node.json); last_response_ = Clock::now();
  if ((node.rloc & 0x03ff) == 0 && !routers_[node.rloc >> 10]) {
    routers_[node.rloc >> 10] = true; ++router_count_;
    for (const auto child : node.children) {
      if (std::find(children_.begin(), children_.end(), child) != children_.end()) continue;
      if (children_.size() >= max_children) { truncated_ = true; break; }
      children_.push_back(child);
    }
  }
}
WebReply TopologyManager::result(bool timed_out) {
  if (nodes_.empty()) return web_error(504, "No diagnostic response received");
  unsigned missing_children = 0;
  for (auto child : children_) if (nodes_.find(child) == nodes_.end()) ++missing_children;
  const bool incomplete = truncated_ || query_errors_ || missing_children || router_count_ < expected_ || child_next_ < children_.size();
  std::string list = "[";
  for (const auto &node : nodes_) { if (list.size() > 1) list += ','; list += node.second; }
  list += ']';
  if (!wrapped_) return {incomplete ? 206 : 200, std::move(list)};
  std::string metadata = "{\"expected_routers\":" + std::to_string(expected_) +
      ",\"responding_routers\":" + std::to_string(router_count_) +
      ",\"queued_child_queries\":" + std::to_string(children_.size()) +
      ",\"sent_child_queries\":" + std::to_string(child_next_) +
      ",\"missing_child_responses\":" + std::to_string(missing_children) +
      ",\"query_errors\":" + std::to_string(query_errors_) +
      ",\"truncated\":" + (truncated_ ? "true" : "false") +
      ",\"timed_out\":" + (timed_out ? "true" : "false") +
      ",\"complete\":" + (incomplete ? "false" : "true") + '}';
  return {incomplete ? 206 : 200, "{\"error\":0,\"result\":" + list +
      ",\"message\":\"" + (incomplete ? "Partial diagnostic results" : "OK") + "\",\"diagnostics\":" + metadata + '}'};
}
void TopologyManager::finish(WebReply reply) {
  auto done = std::move(completion_);
  nodes_.clear(); children_.clear(); bytes_ = 0;
  if (done) done(std::move(reply));
}
void TopologyManager::tick() {
  if (!completion_) return;
  if (otThreadGetDeviceRole(instance_) < OT_DEVICE_ROLE_CHILD || otThreadGetPartitionId(instance_) != partition_ ||
      std::memcmp(network_.data(), otThreadGetExtendedPanId(instance_)->m8, 8) ||
      std::memcmp(mesh_prefix_.data(), otThreadGetMeshLocalPrefix(instance_)->m8, 8)) {
    finish(web_error(409, "Thread network changed during topology scan")); return;
  }
  const auto now = Clock::now();
  if (now - started_ >= std::chrono::seconds(30)) { finish(result(true)); return; }
  if (child_next_ < children_.size() && now - last_child_ >= std::chrono::milliseconds(500)) {
    const auto child = children_[child_next_++];
    auto address = *otThreadGetRloc(instance_);
    address.mFields.m8[14] = static_cast<std::uint8_t>(child >> 8);
    address.mFields.m8[15] = static_cast<std::uint8_t>(child);
    if (otThreadSendDiagnosticGet(instance_, &address, child_types, sizeof(child_types), response, nullptr) != OT_ERROR_NONE) ++query_errors_;
    last_child_ = last_response_ = now;
  }
  if (now - started_ >= std::chrono::seconds(2) && now - last_response_ >= std::chrono::seconds(3) &&
      router_count_ >= expected_ && child_next_ >= children_.size()) finish(result(false));
}
void TopologyManager::stop() {
  if (current_ == this) current_ = nullptr;
  if (completion_) finish(web_error(503, "Host stopping"));
}
}
