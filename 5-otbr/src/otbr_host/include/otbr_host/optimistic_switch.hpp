#pragma once
#include "otbr_host/native_api.hpp"
#include <cstdint>

namespace otbr_host {
// Caller owns synchronization. Revisions prevent a pre-command poll/write
// from rolling back a newer optimistic command when its response arrives late.
class OptimisticSwitchState {
 public:
  std::uint64_t revision() const { return revision_; }
  void request(bool value, std::uint64_t now_ms) {
    ++revision_;
    update(value, now_ms);
  }
  bool confirm(std::uint64_t revision, bool value, std::uint64_t now_ms) {
    if (revision != revision_) return false;
    update(value, now_ms);
    return true;
  }
  void unavailable(std::uint64_t revision) {
    if (revision == revision_) state_.available = false;
  }
  EntityState snapshot(std::uint64_t now_ms) const {
    return state_.available && now_ms >= updated_ms_ && now_ms - updated_ms_ < 30000 ? state_ : EntityState{};
  }
 private:
  void update(bool value, std::uint64_t now_ms) {
    state_.available = true; state_.boolean = value; updated_ms_ = now_ms;
  }
  EntityState state_;
  std::uint64_t revision_{0}, updated_ms_{0};
};
}
