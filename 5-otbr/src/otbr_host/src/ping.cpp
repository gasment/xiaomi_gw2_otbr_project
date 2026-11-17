#include "otbr_host/ping.hpp"
#include <openthread/thread.h>
#include <cJSON.h>
#include <cmath>
#include <cstring>
#include <memory>
#include <set>

namespace otbr_host {
void PingManager::request(const WebRequest &request, WebCompletion done) {
  if (request.method != "POST") { done(web_error(405, "Method not allowed")); return; }
  if (request.body.size() > 1024 || request.body.find('\0') != std::string::npos ||
      request.body.find("\\u0000") != std::string::npos) { done(web_error(400, "Invalid JSON request")); return; }
  std::unique_ptr<cJSON, decltype(&cJSON_Delete)> json(
      cJSON_ParseWithLengthOpts(request.body.c_str(), request.body.size() + 1, nullptr, true), cJSON_Delete);
  if (!cJSON_IsObject(json.get())) { done(web_error(400, "Expected JSON object")); return; }
  std::set<std::string> keys; const cJSON *member;
  cJSON_ArrayForEach(member, json.get()) {
    if (!member->string || !keys.insert(member->string).second) { done(web_error(400, "Duplicate JSON field")); return; }
    if (std::strcmp(member->string, "address") && std::strcmp(member->string, "count") && std::strcmp(member->string, "size")) {
      done(web_error(400, "Unknown Ping field")); return;
    }
  }
  const auto *address = cJSON_GetObjectItemCaseSensitive(json.get(), "address");
  otPingSenderConfig config{};
  if (!cJSON_IsString(address) || !address->valuestring || std::strlen(address->valuestring) > 45 ||
      otIp6AddressFromString(address->valuestring, &config.mDestination) != OT_ERROR_NONE) {
    done(web_error(400, "Expected IPv6 address")); return;
  }
  auto integer = [&](const char *key, unsigned fallback, unsigned low, unsigned high, std::uint16_t &out) {
    const auto *field = cJSON_GetObjectItemCaseSensitive(json.get(), key);
    if (!field) { out = static_cast<std::uint16_t>(fallback); return true; }
    if (!cJSON_IsNumber(field) || !std::isfinite(field->valuedouble) || field->valuedouble < low ||
        field->valuedouble > high || std::floor(field->valuedouble) != field->valuedouble) return false;
    out = static_cast<std::uint16_t>(field->valuedouble); return true;
  };
  if (!integer("count", 4, 1, 10, config.mCount) || !integer("size", 32, 4, 512, config.mSize)) {
    done(web_error(400, "count must be 1..10 and size 4..512, both integers")); return;
  }
  if (completion_) { done(web_error(409, "Ping already in progress")); return; }
  if (otThreadGetDeviceRole(instance_) < OT_DEVICE_ROLE_CHILD) {
    done(web_error(409, "Thread is not attached")); return;
  }
  config.mReplyCallback = reply_callback; config.mStatisticsCallback = statistics_callback;
  config.mCallbackContext = this; config.mInterval = 1000; config.mTimeout = 3000;
  reply_count_ = 0; finished_ = truncated_ = false; statistics_ = {};
  deadline_ = std::chrono::steady_clock::now() + std::chrono::milliseconds(config.mCount * 1000 + 5000);
  completion_ = std::move(done);
  const auto error = otPingSenderPing(instance_, &config);
  if (error != OT_ERROR_NONE) {
    // A failed start may belong to another CLI Ping: never stop that operation.
    auto complete = std::move(completion_);
    complete(web_error(error == OT_ERROR_BUSY ? 409 : 503, "OpenThread Ping start failed"));
  }
}
void PingManager::reply_callback(const otPingSenderReply *reply, void *context) {
  auto &self = *static_cast<PingManager *>(context);
  if (!self.completion_) return;
  if (self.reply_count_ < self.replies_.size()) self.replies_[self.reply_count_++] = *reply;
  else self.truncated_ = true;
}
void PingManager::statistics_callback(const otPingSenderStatistics *statistics, void *context) {
  auto &self = *static_cast<PingManager *>(context);
  if (self.completion_) { self.statistics_ = *statistics; self.finished_ = true; }
}
void PingManager::finish(WebReply result, bool cancel_sender) {
  if (cancel_sender) otPingSenderStop(instance_);
  auto done = std::move(completion_); finished_ = false;
  if (done) done(std::move(result));
}
void PingManager::tick() {
  if (!completion_) return;
  if (finished_) finish(ping_result(replies_.data(), reply_count_, statistics_, truncated_), false);
  else if (otThreadGetDeviceRole(instance_) < OT_DEVICE_ROLE_CHILD) finish(web_error(409, "Thread detached during Ping"));
  else if (std::chrono::steady_clock::now() >= deadline_) finish(web_error(504, "Ping statistics timed out"));
}
void PingManager::stop() {
  if (completion_) finish(web_error(503, "Host stopping"));
}
}
