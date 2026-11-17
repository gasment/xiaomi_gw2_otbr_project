#include "otbr_host/native_api.hpp"
#include <atomic>
#include <csignal>
#include <exception>
#include <iostream>
namespace { static_assert(std::atomic<bool>::is_always_lock_free); std::atomic<bool> stop{false}; void shutdown(int) { stop.store(true); } }
int main(int argc, char **argv) {
  if (argc != 2) { std::cerr << "Usage: otbr-native-api-check config.yaml\n"; return 2; }
  std::signal(SIGINT, shutdown); std::signal(SIGTERM, shutdown);
  try {
    const auto config = otbr_host::load_config(argv[1]);
    std::cout << "PROTOCOL_ONLY: no OTBR instance, UART access, Web listener or Thread network. Entity states are missing until a real backend is connected.\n";
    otbr_host::run_native_api(config, [] { return otbr_host::Snapshot{}; }, stop, nullptr,
      [](const std::string &entity, bool state) {
        std::cout << "PROTOCOL_ONLY_COMMAND_REJECTED " << entity << ' ' << (state ? "on" : "off") << std::endl;
        return false; // Observe dispatch only. Never access LEDs or reboot.
      });
    return 0;
  } catch (const std::exception &e) {
    if (stop) return 0;
    std::cerr << "API_ERROR: " << e.what() << '\n'; return 1;
  }
}
