#pragma once
#include "otbr_host/web.hpp"
#include <openthread/ping_sender.h>
#include <array>
#include <chrono>
namespace otbr_host {
// All methods and callbacks run on the OpenThread owner thread.
class PingManager {
 public:
  explicit PingManager(otInstance *instance) : instance_(instance) {}
  ~PingManager() { stop(); }
  PingManager(const PingManager &) = delete;
  PingManager &operator=(const PingManager &) = delete;
  void request(const WebRequest &request, WebCompletion done);
  void tick();
  void stop();
 private:
  static void reply_callback(const otPingSenderReply *, void *);
  static void statistics_callback(const otPingSenderStatistics *, void *);
  otInstance *instance_;
  WebCompletion completion_;
  std::array<otPingSenderReply, 32> replies_{};
  unsigned reply_count_{0};
  otPingSenderStatistics statistics_{};
  bool finished_{false}, truncated_{false};
  std::chrono::steady_clock::time_point deadline_;
  void finish(WebReply result, bool cancel_sender = true);
};
WebReply ping_result(const otPingSenderReply *replies, unsigned count,
                     const otPingSenderStatistics &statistics, bool truncated);
}
