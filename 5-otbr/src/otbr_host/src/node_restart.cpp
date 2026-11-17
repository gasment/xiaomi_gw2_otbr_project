#include "otbr_host/node_restart.hpp"
#include <openthread/thread.h>
#include <openthread/ip6.h>
#include <openthread/random_crypto.h>
#include <openthread/message.h>
#include <cJSON.h>
#include <cmath>
#include <cstring>
#include <set>

namespace otbr_host {
namespace {
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
bool parse_ext(const char *value, std::array<std::uint8_t, 8> &out) {
  if (!value || std::strlen(value) != 16) return false;
  auto digit = [](char c) -> int {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
  };
  for (unsigned n = 0; n < out.size(); ++n) {
    const int a = digit(value[2*n]), b = digit(value[2*n+1]);
    if (a < 0 || b < 0) return false;
    out[n] = static_cast<std::uint8_t>((a << 4) | b);
  }
  return true;
}
WebReply outcome(bool accepted) {
  return {200, std::string("{\"error\":0,\"result\":{\"accepted\":") +
      (accepted ? "true,\"message\":\"Node accepted restart request\"}" :
                  "false,\"message\":\"No node acknowledgement within 15 seconds\"}") +
      ",\"message\":\"OK\"}"};
}
}
bool NodeRestartManager::same_network() const {
  return otThreadGetDeviceRole(instance_) >= OT_DEVICE_ROLE_CHILD &&
      partition_ == otThreadGetPartitionId(instance_) &&
      std::memcmp(network_.data(), otThreadGetExtendedPanId(instance_)->m8, 8) == 0 &&
      std::memcmp(prefix_.data(), otThreadGetMeshLocalPrefix(instance_)->m8, 8) == 0;
}
void NodeRestartManager::request(const WebRequest &request, WebCompletion done) {
  if (request.method != "POST") { done(web_error(405, "Method not allowed")); return; }
  if (request.body.empty() || request.body.size() > 1024 || request.body.find('\0') != std::string::npos ||
      request.body.find("\\u0000") != std::string::npos) { done(web_error(400, "Invalid restart JSON")); return; }
  Json json(cJSON_ParseWithLengthOpts(request.body.c_str(), request.body.size()+1, nullptr, true), cJSON_Delete);
  if (!cJSON_IsObject(json.get())) { done(web_error(400, "Expected restart JSON object")); return; }
  std::set<std::string> keys; const cJSON *field;
  cJSON_ArrayForEach(field, json.get()) {
    if (!field->string || !keys.insert(field->string).second) { done(web_error(400, "Duplicate restart field")); return; }
    if (keys.size() > 3 || (std::strcmp(field->string, "address") && std::strcmp(field->string, "ext_address") &&
                          std::strcmp(field->string, "rloc16"))) { done(web_error(400, "Unknown restart field")); return; }
  }
  const auto *address = cJSON_GetObjectItemCaseSensitive(json.get(), "address");
  const auto *identity = cJSON_GetObjectItemCaseSensitive(json.get(), "ext_address");
  const auto *rloc = cJSON_GetObjectItemCaseSensitive(json.get(), "rloc16");
  otIp6Address destination{}; std::array<std::uint8_t, 8> ext{};
  if (!cJSON_IsString(address) || !address->valuestring || std::strlen(address->valuestring) > 45 ||
      otIp6AddressFromString(address->valuestring, &destination) != OT_ERROR_NONE ||
      !cJSON_IsString(identity) || !parse_ext(identity->valuestring, ext) || !cJSON_IsNumber(rloc) ||
      !std::isfinite(rloc->valuedouble) || rloc->valuedouble < 0 || rloc->valuedouble > 65534 ||
      std::floor(rloc->valuedouble) != rloc->valuedouble) {
    done(web_error(400, "Expected node IPv6 address, 16-digit ext_address and integer rloc16")); return;
  }
  if (completion_) { done(web_error(409, "Another node restart is in progress")); return; }
  if (otThreadGetDeviceRole(instance_) < OT_DEVICE_ROLE_CHILD) { done(web_error(409, "Thread is not attached")); return; }
  destination_ = destination; ext_ = ext; rloc_ = static_cast<std::uint16_t>(rloc->valuedouble);
  partition_ = otThreadGetPartitionId(instance_);
  std::copy_n(otThreadGetExtendedPanId(instance_)->m8, 8, network_.begin());
  std::copy_n(otThreadGetMeshLocalPrefix(instance_)->m8, 8, prefix_.begin());
  sent_ = accepted_ = false;
  deadline_ = std::chrono::steady_clock::now() + std::chrono::seconds(47);
  completion_ = std::move(done);
  const auto token = ++generation_;
  std::weak_ptr<int> lifetime = lifetime_;
  // Fresh diagnostics bind the submitted IPv6 address, extended address and
  // RLOC before any reboot command is sent. Reuse the existing async collector.
  topology_.request({"GET", "/diagnostics", ""}, [this, lifetime, token](WebReply reply) {
    if (lifetime.expired() || token != generation_ || !completion_) return;
    diagnosed(std::move(reply));
  });
}
void NodeRestartManager::diagnosed(WebReply reply) {
  if (reply.status != 200 && reply.status != 206) { finish(std::move(reply)); return; }
  if (!same_network()) { finish(web_error(409, "Thread network changed before restart")); return; }
  Json nodes(cJSON_ParseWithLengthOpts(reply.body.c_str(), reply.body.size()+1, nullptr, true), cJSON_Delete);
  bool belongs = false; const cJSON *node;
  cJSON_ArrayForEach(node, nodes.get()) {
    const auto *rloc = cJSON_GetObjectItemCaseSensitive(node, "Rloc16");
    const auto *identity = cJSON_GetObjectItemCaseSensitive(node, "ExtAddress");
    std::array<std::uint8_t, 8> actual{};
    if (!cJSON_IsNumber(rloc) || rloc->valuedouble != rloc_ || !cJSON_IsString(identity) ||
        !parse_ext(identity->valuestring, actual) || actual != ext_) continue;
    const cJSON *address;
    cJSON_ArrayForEach(address, cJSON_GetObjectItemCaseSensitive(node, "IP6AddressList")) {
      otIp6Address candidate{};
      if (cJSON_IsString(address) && address->valuestring &&
          otIp6AddressFromString(address->valuestring, &candidate) == OT_ERROR_NONE &&
          std::memcmp(&candidate, &destination_, sizeof(candidate)) == 0) belongs = true;
    }
    auto rloc_address = *otThreadGetRloc(instance_);
    rloc_address.mFields.m8[14] = static_cast<std::uint8_t>(rloc_ >> 8);
    rloc_address.mFields.m8[15] = static_cast<std::uint8_t>(rloc_);
    belongs = belongs || std::memcmp(&rloc_address, &destination_, sizeof(destination_)) == 0;
    break;
  }
  if (!belongs) { finish(web_error(409, "Selected address no longer belongs to this node; refresh topology")); return; }
  send();
}
void NodeRestartManager::send() {
  std::array<std::uint8_t, 8> nonce{};
  if (otRandomCryptoFillBuffer(nonce.data(), static_cast<std::uint16_t>(nonce.size())) != OT_ERROR_NONE) {
    finish(web_error(503, "Could not create restart nonce")); return;
  }
  packet_ = restart_packet(ext_, nonce);
  if (otUdpOpen(instance_, &socket_, receive, this) != OT_ERROR_NONE) {
    finish(web_error(503, "Could not open node restart socket")); return;
  }
  opened_ = true;
  otSockAddr local{}; // Port zero requests an ephemeral source port.
  if (otUdpBind(instance_, &socket_, &local, OT_NETIF_THREAD_INTERNAL) != OT_ERROR_NONE) {
    finish(web_error(503, "Could not bind node restart socket")); return;
  }
  auto *message = otUdpNewMessage(instance_, nullptr);
  if (!message) { finish(web_error(503, "Could not allocate restart packet")); return; }
  otMessageInfo info{};
  info.mPeerAddr = destination_; info.mPeerPort = kNodeRestartPort;
  info.mSockAddr = *otThreadGetMeshLocalEid(instance_); info.mHopLimit = 64;
  auto error = otMessageAppend(message, packet_.data(), static_cast<std::uint16_t>(packet_.size()));
  if (error == OT_ERROR_NONE) error = otUdpSend(instance_, &socket_, message, &info);
  if (error != OT_ERROR_NONE) {
    otMessageFree(message); finish(web_error(503, "Could not submit node restart request")); return;
  }
  sent_ = true;
  deadline_ = std::chrono::steady_clock::now() + std::chrono::seconds(15);
}
void NodeRestartManager::receive(void *context, otMessage *message, const otMessageInfo *info) {
  auto &self = *static_cast<NodeRestartManager *>(context);
  if (!self.completion_ || !self.sent_ || !self.same_network()) return;
  RestartPacket reply{};
  const auto offset = otMessageGetOffset(message);
  if (otMessageGetLength(message) - offset != reply.size() ||
      otMessageRead(message, offset, reply.data(), static_cast<std::uint16_t>(reply.size())) != reply.size()) return;
  if (restart_reply_matches(self.packet_, reply.data(), reply.size(), info->mPeerPort)) self.accepted_ = true;
}
void NodeRestartManager::finish(WebReply reply) {
  ++generation_;
  if (opened_) { (void)otUdpClose(instance_, &socket_); opened_ = false; }
  sent_ = false;
  auto done = std::move(completion_);
  if (done) done(std::move(reply));
}
void NodeRestartManager::tick() {
  if (!completion_) return;
  if (!same_network()) finish(web_error(409, "Thread network changed during node restart"));
  else if (accepted_) finish(outcome(true));
  else if (std::chrono::steady_clock::now() >= deadline_)
    finish(sent_ ? outcome(false) : web_error(504, "Node identity verification timed out"));
}
void NodeRestartManager::stop() {
  if (completion_) finish(web_error(503, "Host stopping"));
}
}
