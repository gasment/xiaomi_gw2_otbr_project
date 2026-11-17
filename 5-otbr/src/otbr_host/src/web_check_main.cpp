#include "otbr_host/config.hpp"
#include "otbr_host/web.hpp"
#include <atomic>
#include <csignal>
#include <exception>
#include <iostream>
namespace {
std::atomic<bool> stopped{false};
void shutdown(int) { stopped = true; }
}
int main(int argc, char **argv) {
  if (argc != 2) { std::cerr << "Usage: otbr-web-http-check config.yaml\n"; return 2; }
  std::signal(SIGINT, shutdown); std::signal(SIGTERM, shutdown);
  try {
    const auto config = otbr_host::load_config(argv[1]);
    std::cerr << "HTTP_TRANSPORT_ONLY: no UART, OTBR instance or Thread network; dynamic endpoints return 503\n";
    otbr_host::run_web(config, [](const auto &) { return otbr_host::web_error(503, "No OTBR backend in transport check"); }, stopped, "127.0.0.1");
    return 0;
  } catch (const std::exception &e) { std::cerr << "WEB_ERROR: " << e.what() << '\n'; return 1; }
}
