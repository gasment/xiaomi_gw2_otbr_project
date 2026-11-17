#include "otbr_host/system_metrics.hpp"
#include <iostream>
#include <sstream>
#include <stdexcept>

int main() {
  using namespace otbr_host;
  auto require = [](bool ok) { if (!ok) throw std::runtime_error("Linux system metric check failed"); };
  require(format_system_uptime(0) == "00d:00h:00m");
  require(format_system_uptime(90061) == "01d:01h:01m");
  require(format_system_uptime(100ULL * 86400 + 23 * 3600 + 59 * 60 + 59) == "100d:23h:59m");
  std::istringstream valid("MemFree: 1 kB\nMemAvailable: 24576 kB\nCached: 888 kB\n");
  require(read_available_memory(valid) == 24ULL * 1048576);
  std::istringstream zero("MemAvailable: 0 kB\n");
  require(read_available_memory(zero) == 0);
  for (const char *line : {"MemFree: 100 kB\n", "MemAvailable: -1 kB\n", "MemAvailable: junk kB\n",
                          "MemAvailable: 4 MB\n", "MemAvailable: 18446744073709551615 kB\n", ""}) {
    std::istringstream invalid(line);
    require(!read_available_memory(invalid));
  }
  std::cout << "SYSTEM_METRICS_PASS\n";
}
