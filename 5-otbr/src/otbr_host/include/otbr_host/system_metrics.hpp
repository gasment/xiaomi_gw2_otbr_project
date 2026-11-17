#pragma once
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <istream>
#include <limits>
#include <optional>
#include <sstream>
#include <string>
#include <sys/sysinfo.h>

namespace otbr_host {
inline std::string format_system_uptime(std::uint64_t seconds) {
  std::ostringstream value;
  value << std::setfill('0') << std::setw(2) << seconds / 86400 << "d:"
        << std::setw(2) << seconds / 3600 % 24 << "h:" << std::setw(2) << seconds / 60 % 60 << 'm';
  return value.str();
}

// MemAvailable includes reclaimable cache; MemFree alone understates usable RAM.
// Missing or malformed readings stay unavailable instead of displaying a false zero.
inline std::optional<std::uint64_t> read_available_memory(std::istream &input) {
  std::string line;
  while (std::getline(input, line)) {
    std::istringstream fields(line);
    std::string name, amount, unit, extra;
    fields >> name;
    if (name != "MemAvailable:") continue;
    if (!(fields >> amount >> unit) || unit != "kB" || (fields >> extra) || amount.empty()) return {};
    std::uint64_t kb = 0;
    for (char c : amount) {
      if (c < '0' || c > '9' || kb > (std::numeric_limits<std::uint64_t>::max() - (c - '0')) / 10) return {};
      kb = kb * 10 + (c - '0');
    }
    if (kb > std::numeric_limits<std::uint64_t>::max() / 1024) return {};
    return kb * 1024;
  }
  return {};
}

struct SystemMetrics {
  std::string uptime = "-";
  std::string available_memory = "-";
  std::optional<std::uint64_t> available_bytes;
};
inline SystemMetrics read_system_metrics() {
  SystemMetrics metrics;
  struct sysinfo info {};
  if (::sysinfo(&info) == 0 && info.uptime >= 0)
    metrics.uptime = format_system_uptime(static_cast<std::uint64_t>(info.uptime));
  std::ifstream meminfo("/proc/meminfo");
  metrics.available_bytes = read_available_memory(meminfo);
  if (metrics.available_bytes) {
    std::ostringstream value;
    value << std::fixed << std::setprecision(1) << *metrics.available_bytes / 1048576.0 << " MiB";
    metrics.available_memory = value.str();
  }
  return metrics;
}
} // namespace otbr_host
