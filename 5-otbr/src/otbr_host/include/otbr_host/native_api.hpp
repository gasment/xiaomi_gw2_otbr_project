#pragma once
#include "otbr_host/config.hpp"
#include <atomic>
#include <functional>
#include <map>
#include <string>
namespace otbr_host {
struct EntityState {
  bool available{false};
  bool boolean{false};
  float number{0};
  std::string text;
};
using Snapshot = std::map<std::string, EntityState>;
using SnapshotProvider = std::function<Snapshot()>;
// Queues a validated command; the callback must not block the API connection.
using EntityCommandHandler = std::function<bool(const std::string &, bool)>;
// Runs until stop is set. Provider must return a thread-safe cached snapshot;
// no callback may directly perform blocking OpenThread/RCP operations.
std::string native_api_device_mac(const Config &config);
void run_native_api(const Config &config, const SnapshotProvider &provider, std::atomic<bool> &stop,
                    std::atomic<bool> *ready = nullptr, const EntityCommandHandler &command = {});
}
