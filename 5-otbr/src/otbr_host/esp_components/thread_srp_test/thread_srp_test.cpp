#include "thread_srp_test.h"
#ifdef USE_ESP32
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include <esp_openthread.h>
#include <esp_openthread_lock.h>
#include <openthread/error.h>
#include <openthread/srp_client.h>
#include <openthread/thread.h>
#include <cstring>

namespace esphome { namespace thread_srp_test {
static const char *const TAG = "thread_srp_test";
namespace {
struct Lock {
  bool owns{false};
  Lock() { if (esp_openthread_get_instance()) owns = esp_openthread_lock_acquire(0); }
  ~Lock() { if (owns) esp_openthread_lock_release(); }
};
const char *state_name(otSrpClientItemState state) {
  switch (state) {
    case OT_SRP_CLIENT_ITEM_STATE_TO_ADD: return "to-add";
    case OT_SRP_CLIENT_ITEM_STATE_ADDING: return "adding";
    case OT_SRP_CLIENT_ITEM_STATE_TO_REFRESH: return "to-refresh";
    case OT_SRP_CLIENT_ITEM_STATE_REFRESHING: return "refreshing";
    case OT_SRP_CLIENT_ITEM_STATE_TO_REMOVE: return "to-remove";
    case OT_SRP_CLIENT_ITEM_STATE_REMOVING: return "removing";
    case OT_SRP_CLIENT_ITEM_STATE_REGISTERED: return "registered";
    case OT_SRP_CLIENT_ITEM_STATE_REMOVED: return "removed";
    default: return "unknown";
  }
}
}
void ThreadSrpTest::setup() {
  if (!server_.mPort || otIp6AddressFromString(server_text_.c_str(), &server_.mAddress) != OT_ERROR_NONE) {
    ESP_LOGE(TAG, "Invalid test SRP server");
    mark_failed();
  }
}
void ThreadSrpTest::dump_config() {
  ESP_LOGCONFIG(TAG, "SRP test target=[%s]:%u", server_text_.c_str(), unsigned(server_.mPort));
  ESP_LOGCONFIG(TAG, "  Overrides automatic server selection while installed; retains ESPHome services and callback");
}
void ThreadSrpTest::update() {
  std::string report;
  bool waiting = false, start_sent = false, registered = false;
  otError start_error = OT_ERROR_NONE;
  {
    Lock lock;
    if (!lock.owns) return;
    auto *instance = esp_openthread_get_instance();
    if (!instance || otThreadGetDeviceRole(instance) < OT_DEVICE_ROLE_CHILD) {
      instance_ = nullptr;
      started_ = attempted_ = false;
      return;
    }
    if (instance_ != instance) {
      instance_ = instance;
      started_ = attempted_ = false;
      last_report_.clear();
    }
    const auto *host = otSrpClientGetHostInfo(instance);
    const auto *services = otSrpClientGetServices(instance);
    // Wait until ESPHome has installed its own host, services, TXT and callback.
    // Never replace its callback or allocate/clear the framework's service buffers.
    if (!host || !host->mName || !host->mName[0] || !services) {
      waiting = true;
    } else {
      const auto *current = otSrpClientGetServerAddress(instance);
      bool target_matches = otSrpClientIsRunning(instance) && current &&
                            current->mPort == server_.mPort &&
                            std::memcmp(&current->mAddress, &server_.mAddress, sizeof(server_.mAddress)) == 0;
      const auto now = millis();
      if ((!started_ || !target_matches) && (!attempted_ || uint32_t(now - last_attempt_) >= 5000)) {
        attempted_ = true;
        last_attempt_ = now;
        // Stop disables auto-start but preserves host and services, marking them
        // for re-registration. Starting with a target pins this server explicitly.
        otSrpClientStop(instance);
        start_error = otSrpClientStart(instance, &server_);
        started_ = start_error == OT_ERROR_NONE;
        start_sent = true;
        current = otSrpClientGetServerAddress(instance);
        target_matches = started_ && current && current->mPort == server_.mPort &&
                         std::memcmp(&current->mAddress, &server_.mAddress, sizeof(server_.mAddress)) == 0;
      }
      host = otSrpClientGetHostInfo(instance);
      services = otSrpClientGetServices(instance);
      char address[OT_IP6_ADDRESS_STRING_SIZE]{};
      if (current) otIp6AddressToString(&current->mAddress, address, sizeof(address));
      report = "server=[" + std::string(address) + "]:" + std::to_string(current ? current->mPort : 0);
      report += " host=" + std::string(host && host->mName ? host->mName : "-");
      report += " host_state=" + std::string(host ? state_name(host->mState) : "missing");
      report += host && host->mAutoAddress ? " addresses=auto" :
                " addresses=" + std::to_string(host ? host->mNumAddresses : 0);
      bool api_registered = false;
      unsigned count = 0;
      for (const auto *service = services; service && count < 16; service = service->mNext, ++count) {
        report += " service=" + std::string(service->mName ? service->mName : "-") + ":" +
                  std::to_string(service->mPort) + "/" + state_name(service->mState);
        if (service->mName && std::strcmp(service->mName, "_esphomelib._tcp") == 0 &&
            service->mState == OT_SRP_CLIENT_ITEM_STATE_REGISTERED) api_registered = true;
      }
      registered = target_matches && host && host->mState == OT_SRP_CLIENT_ITEM_STATE_REGISTERED && api_registered;
    }
  }
  // Log outside the OpenThread critical section.
  if (waiting) {
    if (uint32_t(millis() - last_wait_log_) >= 10000) {
      last_wait_log_ = millis();
      ESP_LOGW(TAG, "WAIT_ESPHOME_SRP: host/services not initialized; retain the existing api and openthread configuration");
    }
    return;
  }
  if (start_sent) {
    if (start_error == OT_ERROR_NONE)
      ESP_LOGI(TAG, "TARGET_STARTED [%s]:%u; request started, registration not yet proven", server_text_.c_str(), unsigned(server_.mPort));
    else ESP_LOGW(TAG, "TARGET_START_FAILED: %s", otThreadErrorToString(start_error));
  }
  const auto complete = std::string(registered ? "SRP_TARGET_REGISTERED " : "SRP_TARGET_PENDING ") + report;
  if (complete != last_report_) {
    last_report_ = complete;
    ESP_LOGI(TAG, "%s", complete.c_str());
  }
}
}}
#endif
