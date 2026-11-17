#pragma once
#include "esphome/core/component.h"
#ifdef USE_ESP32
#include <openthread/instance.h>
#include <openthread/udp.h>
#include <array>
#include <string>

namespace esphome { namespace thread_multicast_test {
class ThreadMulticastTest : public PollingComponent {
 public:
  void set_group(const std::string &group) { group_text_ = group; }
  void set_port(uint16_t port) { port_ = port; }
  void set_send_interval(uint32_t interval) { interval_ = interval; }
  void set_send_count(unsigned count) { limit_ = count; }
  void setup() override;
  void update() override;
  void on_shutdown() override;
  void dump_config() override;
 private:
  struct Received {
    otIp6Address source{};
    uint16_t port{0};
    char payload[128]{};
  };
  static void receive_(void *, otMessage *, const otMessageInfo *);
  void close_(otInstance *current);
  bool source_(otInstance *, otIp6Address &);
  std::string group_text_{"ff15::1234"};
  uint16_t port_{18515};
  uint32_t interval_{5000}, last_send_{0}, session_{0}, source_report_at_{0};
  unsigned limit_{10}, sent_{0};
  otInstance *instance_{nullptr};
  otIp6Address group_{};
  otUdpSocket socket_{};
  bool opened_{false}, own_group_{false};
  std::array<Received,8> queue_{};
  unsigned head_{0}, tail_{0}, dropped_{0};
};
}}
#endif
