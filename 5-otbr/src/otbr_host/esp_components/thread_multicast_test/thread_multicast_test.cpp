#include "thread_multicast_test.h"
#ifdef USE_ESP32
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include <esp_openthread.h>
#include <esp_openthread_lock.h>
#include <esp_random.h>
#include <openthread/ip6.h>
#include <openthread/thread.h>
#include <openthread/message.h>
#include <cstdio>
#include <cstring>

namespace esphome { namespace thread_multicast_test {
static const char *const TAG = "thread_multicast_test";
static const char MAGIC[] = "MI-BBR-TEST/1;";
namespace {
struct Lock {
  bool owns{false};
  Lock() { if (esp_openthread_get_instance()) owns = esp_openthread_lock_acquire(0); }
  ~Lock() { if (owns) esp_openthread_lock_release(); }
};
}
void ThreadMulticastTest::setup() {
  session_ = esp_random();
  if (otIp6AddressFromString(group_text_.c_str(), &group_) != OT_ERROR_NONE ||
      group_.mFields.m8[0] != 0xff || (group_.mFields.m8[1] & 15) < 4) {
    ESP_LOGE(TAG, "Invalid multicast test group"); mark_failed();
  }
}
void ThreadMulticastTest::dump_config() {
  ESP_LOGCONFIG(TAG, "Thread multicast test: group=%s port=%u", group_text_.c_str(), unsigned(port_));
  ESP_LOGCONFIG(TAG, "  Finite TX: count=%u interval=%ums; no Dataset or SRP changes", limit_, unsigned(interval_));
}
bool ThreadMulticastTest::source_(otInstance *instance, otIp6Address &source) {
  const auto *prefix = otThreadGetMeshLocalPrefix(instance)->m8;
  for (const auto *a = otIp6GetUnicastAddresses(instance); a; a = a->mNext) {
    const auto *bytes = a->mAddress.mFields.m8;
    if (!a->mPreferred || !a->mValid || bytes[0] == 0xff ||
        (bytes[0] == 0xfe && (bytes[1] & 0xc0) == 0x80) ||
        std::memcmp(bytes, prefix, 8) == 0) continue;
    // Require a normal ULA/global unicast source, never :: or loopback.
    if ((bytes[0] & 0xe0) != 0x20 && (bytes[0] & 0xfe) != 0xfc) continue;
    source = a->mAddress; return true;
  }
  return false;
}
void ThreadMulticastTest::close_(otInstance *current) {
  if (current && current == instance_) {
    if (opened_) otUdpClose(current, &socket_);
    if (own_group_) otIp6UnsubscribeMulticastAddress(current, &group_);
  }
  opened_ = own_group_ = false; instance_ = nullptr; socket_ = {};
  head_ = tail_ = 0;
}
void ThreadMulticastTest::receive_(void *context, otMessage *message, const otMessageInfo *info) {
  auto &self = *static_cast<ThreadMulticastTest *>(context);
  if (std::memcmp(&info->mSockAddr, &self.group_, sizeof(self.group_)) != 0) return;
  const unsigned length = otMessageGetLength(message) - otMessageGetOffset(message);
  const unsigned next = (self.head_ + 1) % self.queue_.size();
  if (length < sizeof(MAGIC)-1 || length >= sizeof(Received::payload) || next == self.tail_) { ++self.dropped_; return; }
  auto &entry = self.queue_[self.head_];
  if (otMessageRead(message, otMessageGetOffset(message), entry.payload, length) != int(length) ||
      std::memcmp(entry.payload, MAGIC, sizeof(MAGIC)-1) != 0) return;
  entry.payload[length] = 0;
  for (unsigned i=0; i<length; ++i) if (entry.payload[i] < 32 || entry.payload[i] > 126) entry.payload[i]='.';
  entry.source = info->mPeerAddr; entry.port = info->mPeerPort;
  self.head_ = next; // Callback only copies data; no logging or network response.
}
void ThreadMulticastTest::update() {
  std::array<Received,8> received{}; unsigned count=0, drops=0;
  bool ready=false, sent=false, waiting_source=false; otError error=OT_ERROR_NONE; otIp6Address source{};
  struct ErrorReport {
    otError &value;
    ~ErrorReport() { if (value != OT_ERROR_NONE) ESP_LOGW(TAG, "Test socket/group/send error=%s", otThreadErrorToString(value)); }
  } report{error};
  char payload[128]{}; unsigned sequence=0;
  {
    Lock lock;
    if (!lock.owns) return;
    auto *instance = esp_openthread_get_instance();
    if (!instance || otThreadGetDeviceRole(instance) < OT_DEVICE_ROLE_CHILD) { close_(instance); return; }
    if (instance_ && instance_ != instance) close_(instance);
    if (!opened_) {
      instance_ = instance;
      error = otIp6SubscribeMulticastAddress(instance, &group_);
      if (error != OT_ERROR_NONE && error != OT_ERROR_ALREADY) return;
      own_group_ = error == OT_ERROR_NONE;
      error = otUdpOpen(instance, &socket_, receive_, this);
      if (error != OT_ERROR_NONE) { close_(instance); return; }
      opened_ = true;
      otSockAddr local{}; local.mPort = port_;
      error = otUdpBind(instance, &socket_, &local, OT_NETIF_THREAD_INTERNAL);
      if (error != OT_ERROR_NONE) { close_(instance); return; }
      ready = true; last_send_ = millis();
    }
    while (tail_ != head_ && count < received.size()) {
      received[count++] = queue_[tail_]; tail_ = (tail_+1) % queue_.size();
    }
    drops = dropped_; dropped_ = 0;
    const auto now = millis();
    if (sent_ < limit_ && uint32_t(now-last_send_) >= interval_ && source_(instance, source)) {
      last_send_ = now; sequence = sent_ + 1;
      std::snprintf(payload, sizeof(payload), "MI-BBR-TEST/1;source=node;session=%08x;seq=%u", unsigned(session_), sequence);
      auto *out = otUdpNewMessage(instance, nullptr);
      if (!out) error = OT_ERROR_NO_BUFS;
      else {
        otMessageInfo info{}; info.mPeerAddr = group_; info.mPeerPort = port_;
        info.mSockAddr = source; info.mHopLimit = 16;
        error = otMessageAppend(out, payload, std::strlen(payload));
        if (error == OT_ERROR_NONE) error = otUdpSend(instance, &socket_, out, &info);
        if (error != OT_ERROR_NONE) otMessageFree(out);
      }
      if (error == OT_ERROR_NONE) { ++sent_; sent=true; }
    } else if (sent_ < limit_ && uint32_t(now-last_send_) >= interval_) waiting_source = true;
  }
  if (ready) ESP_LOGI(TAG, "SUBSCRIBED group=%s port=%u; verify MLR on Primary BBR", group_text_.c_str(), unsigned(port_));
  for (unsigned i=0; i<count; ++i) {
    char address[OT_IP6_ADDRESS_STRING_SIZE]; otIp6AddressToString(&received[i].source, address, sizeof(address));
    ESP_LOGI(TAG, "RX from=[%s]:%u payload=%s", address, unsigned(received[i].port), received[i].payload);
  }
  if (drops) ESP_LOGW(TAG, "RX queue/length drops=%u", drops);
  if (sent) {
    char address[OT_IP6_ADDRESS_STRING_SIZE]; otIp6AddressToString(&source, address, sizeof(address));
    ESP_LOGI(TAG, "TX source=%s payload=%s", address, payload);
  }
  if (waiting_source && uint32_t(millis()-source_report_at_) >= 10000) {
    source_report_at_ = millis();
    ESP_LOGW(TAG, "WAIT_SOURCE: no preferred OMR/global IPv6 source; mesh-local is not used across BBR");
  }
}
void ThreadMulticastTest::on_shutdown() {
  Lock lock;
  if (lock.owns) close_(esp_openthread_get_instance());
}
}}
#endif
