#pragma once
#include <cstdint>
#include <string>
#include <utility>
#include <vector>
namespace otbr_host {
struct Link {
  std::string name;
  bool ready{false};
  bool default_route{false};
  unsigned route_metric{0xffffffffu};
};
class BackboneSelector {
 public:
  explicit BackboneSelector(std::string policy, std::uint64_t delay_ms, std::string initial = {})
      : policy_(std::move(policy)), current_(std::move(initial)), delay_ms_(delay_ms) {}
  // Pure decision logic. Empty means no usable infrastructure link; never clears Dataset.
  std::string update(const std::vector<Link> &links, std::uint64_t monotonic_ms);
  const std::string &current() const { return current_; }
 private:
  std::string policy_, current_, pending_;
  std::uint64_t delay_ms_, pending_since_{0};
  bool waiting_{false};
};
// Read-only snapshot. Candidates empty: discover eligible Linux interfaces.
// Loopback, Thread/TUN, point-to-point, enslaved ports and non-multicast links excluded.
std::vector<Link> snapshot_links(const std::vector<std::string> &candidates,
                                 const std::string &thread_interface);
}
