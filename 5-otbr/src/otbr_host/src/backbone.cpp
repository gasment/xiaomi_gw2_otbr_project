#include "otbr_host/backbone.hpp"
#include <algorithm>
#include <fstream>
#include <ifaddrs.h>
#include <map>
#include <memory>
#include <net/if.h>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
namespace otbr_host {
std::string BackboneSelector::update(const std::vector<Link> &links, std::uint64_t now) {
  const Link *old = nullptr, *best = nullptr;
  for (const auto &link : links) {
    if (!link.ready) continue;
    if (link.name == current_) old = &link;
    if (!best || (link.default_route && !best->default_route) ||
        (link.default_route == best->default_route && link.route_metric < best->route_metric) ||
        (link.default_route == best->default_route && link.route_metric == best->route_metric && link.name < best->name)) best = &link;
  }
  if (old && (policy_ == "keep_current" || !best ||
      (old->default_route == best->default_route && old->route_metric == best->route_metric))) best = old;
  const std::string desired = best ? best->name : "";
  if (desired == current_) { waiting_ = false; return current_; }
  // A dead interface is immediately withdrawn. Failover publication is debounced.
  if (!old && !current_.empty()) current_.clear();
  if (desired.empty()) { waiting_ = false; current_.clear(); return current_; }
  if (!waiting_ || pending_ != desired || now < pending_since_) {
    pending_ = desired; pending_since_ = now; waiting_ = true;
  }
  if (now - pending_since_ >= delay_ms_) { current_ = desired; waiting_ = false; }
  return current_;
}
std::vector<Link> snapshot_links(const std::vector<std::string> &candidates, const std::string &thread_interface) {
  ifaddrs *raw = nullptr;
  if (getifaddrs(&raw) != 0) throw std::runtime_error("cannot enumerate Linux network interfaces");
  std::unique_ptr<ifaddrs, decltype(&freeifaddrs)> addresses(raw, freeifaddrs);
  struct Info { unsigned flags{}; bool ipv4{false}, link_local_v6{false}; };
  std::map<std::string, Info> info;
  const std::set<std::string> allowed(candidates.begin(), candidates.end());
  for (auto *p = raw; p; p = p->ifa_next) {
    if (!p->ifa_name || !p->ifa_addr) continue;
    std::string name = p->ifa_name;
    if (name == thread_interface || name == "lo" || (!allowed.empty() && !allowed.count(name))) continue;
    if (name.find('/') != std::string::npos) continue;
    const std::string sys = "/sys/class/net/" + name;
    if (access((sys + "/tun_flags").c_str(), F_OK) == 0 || access((sys + "/master").c_str(), F_OK) == 0) continue;
    auto &i = info[name]; i.flags = p->ifa_flags;
    if (p->ifa_addr->sa_family == AF_INET) {
      const auto *a = reinterpret_cast<const sockaddr_in *>(p->ifa_addr);
      i.ipv4 = i.ipv4 || a->sin_addr.s_addr != INADDR_ANY;
    }
    if (p->ifa_addr->sa_family == AF_INET6) {
      const auto *a = reinterpret_cast<const sockaddr_in6 *>(p->ifa_addr);
      i.link_local_v6 = i.link_local_v6 || IN6_IS_ADDR_LINKLOCAL(&a->sin6_addr);
    }
  }
  std::map<std::string, unsigned> defaults;
  std::ifstream ipv4("/proc/net/route"); std::string line;
  std::getline(ipv4, line);
  while (std::getline(ipv4, line)) {
    std::istringstream row(line); std::string name, destination, gateway, flags, mask;
    unsigned refs{}, use{}, metric{};
    if (!(row >> name >> destination >> gateway >> flags >> refs >> use >> metric >> mask)) continue;
    if (destination != "00000000" || mask != "00000000") continue;
    try {
      if ((std::stoul(flags, nullptr, 16) & 1) == 0) continue;
      auto old = defaults.find(name);
      if (old == defaults.end() || metric < old->second) defaults[name] = metric;
    } catch (const std::exception &) {}
  }
  // Prefer a kernel IPv4 default route when present (matches this gateway's LAN).
  // If absent, consider IPv6 defaults. Metrics from the two families aren't compared.
  if (defaults.empty()) {
    std::ifstream ipv6("/proc/net/ipv6_route");
    while (std::getline(ipv6, line)) {
      std::istringstream row(line); std::string dst, plen, src, splen, hop, metric, refs, use, flags, name;
      if (!(row >> dst >> plen >> src >> splen >> hop >> metric >> refs >> use >> flags >> name)) continue;
      if (dst != std::string(32, '0') || plen != "00") continue;
      try {
        auto f = std::stoul(flags, nullptr, 16); auto m = std::stoul(metric, nullptr, 16);
        if ((f & 1) == 0 || (f & 0x200) != 0) continue; // RTF_UP, !RTF_REJECT
        auto old = defaults.find(name);
        if (old == defaults.end() || m < old->second) defaults[name] = static_cast<unsigned>(m);
      } catch (const std::exception &) {}
    }
  }
  std::vector<Link> result;
  for (const auto &entry : info) {
    const auto &i = entry.second;
    Link link; link.name = entry.first;
    link.ready = (i.flags & IFF_UP) && (i.flags & IFF_RUNNING) && (i.flags & IFF_MULTICAST) &&
                 !(i.flags & IFF_LOOPBACK) && !(i.flags & IFF_POINTOPOINT) && i.link_local_v6;
    const auto route = defaults.find(link.name);
    if (route != defaults.end()) { link.default_route = true; link.route_metric = route->second; }
    result.push_back(std::move(link));
  }
  return result;
}
}
