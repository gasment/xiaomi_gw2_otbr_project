#include "otbr_host/backbone.hpp"
#include "otbr_host/bbr_transport.hpp"
#include "otbr_host/config.hpp"
#include "otbr_host/native_api.hpp"
#include "otbr_host/gateway_system.hpp"
#include "otbr_host/thread_proxy.hpp"
#include "otbr_host/discovery.hpp"
#include "otbr_host/web_ot.hpp"
#include "otbr_host/commissioner.hpp"
#include "otbr_host/ping.hpp"
#include "otbr_host/node_restart.hpp"
#include "otbr_host/topology.hpp"
#include "otbr_host/ha.hpp"
#include "agent/application.hpp"
#include "common/logging.hpp"
#include "common/mainloop_manager.hpp"
#include "host/rcp_host.hpp"
#include "otbr_host/infra_adapter.hpp"
#include <openthread/border_routing.h>
#include <openthread/dataset.h>
#include <openthread/dataset_ftd.h>
#include <openthread/error.h>
#include <openthread/ip6.h>
#include <openthread/link.h>
#include <openthread/mdns.h>
#include <openthread/platform/misc.h>
#include <openthread/platform/radio.h>
#include <openthread/thread.h>
#include <openthread/thread_ftd.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <memory>
#include <stdexcept>
#include <thread>
#include <vector>
#include <arpa/inet.h>
#include <net/if.h>
#include <sys/select.h>
#include <unistd.h>
#include <fstream>
#include <cctype>

namespace {
using namespace otbr_host;
using Clock = std::chrono::steady_clock;
static_assert(std::atomic<bool>::is_always_lock_free);
std::atomic<bool> stop{false};
void shutdown(int) { stop.store(true); }
void check(otError e, const char *operation) {
  if (e != OT_ERROR_NONE) throw std::runtime_error(std::string(operation) + ": " + otThreadErrorToString(e));
}
std::uint64_t millis() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}
void from_hex(const std::string &text, std::uint8_t *out, std::size_t size) {
  if (text.size() != 2 * size) throw std::runtime_error("invalid normalized Dataset field length");
  for (std::size_t i = 0; i < size; ++i) out[i] = static_cast<std::uint8_t>(std::stoul(text.substr(2 * i, 2), nullptr, 16));
}
bool network_matches(const otOperationalDataset &d, const Config &c) {
  std::uint8_t key[16], ext[8], pskc[16]; in6_addr prefix{};
  from_hex(c.network_key, key, sizeof(key)); from_hex(c.ext_pan_id, ext, sizeof(ext)); from_hex(c.pskc, pskc, sizeof(pskc));
  if (inet_pton(AF_INET6, c.mesh_local_prefix.substr(0, c.mesh_local_prefix.size() - 3).c_str(), &prefix) != 1) return false;
  return d.mComponents.mIsNetworkKeyPresent && d.mComponents.mIsNetworkNamePresent &&
         d.mComponents.mIsExtendedPanIdPresent && d.mComponents.mIsPskcPresent &&
         d.mComponents.mIsMeshLocalPrefixPresent && d.mComponents.mIsChannelPresent && d.mComponents.mIsPanIdPresent &&
         d.mChannel == c.channel && d.mPanId == c.pan_id && c.network_name == d.mNetworkName.m8 &&
         std::memcmp(d.mNetworkKey.m8, key, 16) == 0 && std::memcmp(d.mExtendedPanId.m8, ext, 8) == 0 &&
         std::memcmp(d.mPskc.m8, pskc, 16) == 0 && std::memcmp(d.mMeshLocalPrefix.m8, prefix.s6_addr, 8) == 0;
}
void apply_dataset(otInstance *instance, const Config &c) {
  otOperationalDataset saved{};
  const bool have_saved = otDatasetGetActive(instance, &saved) == OT_ERROR_NONE && otDatasetIsCommissioned(instance);
  if (have_saved && (!c.force_dataset || network_matches(saved, c))) {
    std::cerr << "[host] Preserving saved Dataset" << (c.force_dataset ? " (YAML matches)" : " (force_dataset=false)") << '\n';
    return;
  }
  otOperationalDataset d{};
  check(otDatasetCreateNewNetwork(instance, &d), "create Dataset defaults");
  d.mChannel = static_cast<std::uint16_t>(c.channel); d.mPanId = static_cast<otPanId>(c.pan_id);
  std::memset(d.mNetworkName.m8, 0, sizeof(d.mNetworkName.m8));
  std::memcpy(d.mNetworkName.m8, c.network_name.data(), c.network_name.size());
  from_hex(c.network_key, d.mNetworkKey.m8, 16); from_hex(c.ext_pan_id, d.mExtendedPanId.m8, 8); from_hex(c.pskc, d.mPskc.m8, 16);
  in6_addr prefix{};
  if (inet_pton(AF_INET6, c.mesh_local_prefix.substr(0, c.mesh_local_prefix.size() - 3).c_str(), &prefix) != 1) throw std::runtime_error("invalid normalized Mesh-Local prefix");
  std::memcpy(d.mMeshLocalPrefix.m8, prefix.s6_addr, 8);
  d.mComponents.mIsNetworkKeyPresent = d.mComponents.mIsNetworkNamePresent = d.mComponents.mIsExtendedPanIdPresent = true;
  d.mComponents.mIsPskcPresent = d.mComponents.mIsMeshLocalPrefixPresent = d.mComponents.mIsChannelPresent = d.mComponents.mIsPanIdPresent = true;
  check(otDatasetSetActive(instance, &d), "apply YAML Dataset");
  std::cerr << "[host] YAML Dataset applied; credentials are not logged\n";
}
const char *role_name(otDeviceRole role) {
  switch (role) {
    case OT_DEVICE_ROLE_DISABLED: return "disabled";
    case OT_DEVICE_ROLE_DETACHED: return "detached";
    case OT_DEVICE_ROLE_CHILD: return "child";
    case OT_DEVICE_ROLE_ROUTER: return "router";
    case OT_DEVICE_ROLE_LEADER: return "leader";
  }
  return "unknown";
}
std::string identity(otInstance *instance) {
  char text[44]; const auto *pan = otThreadGetExtendedPanId(instance); const auto *ext = otLinkGetExtendedAddress(instance);
  char *p = text; p += std::sprintf(p, "ot1:");
  for (unsigned i = 0; i < 8; ++i) p += std::sprintf(p, "%02x", pan->m8[i]);
  *p++ = ':';
  for (unsigned i = 0; i < 8; ++i) p += std::sprintf(p, "%02x", ext->m8[i]);
  std::sprintf(p, ":%04x", otThreadGetRloc16(instance));
  return text;
}
Snapshot sample(otInstance *instance) {
  Snapshot result;
  const auto role = otThreadGetDeviceRole(instance);
  const bool attached = role >= OT_DEVICE_ROLE_CHILD;
  std::int8_t power = 0;
  const bool healthy = otPlatRadioGetTransmitPower(instance, &power) == OT_ERROR_NONE;
  auto boolean = [&](const char *key, bool value) { EntityState s; s.available = true; s.boolean = value; result[key] = s; };
  auto text = [&](const char *key, const std::string &value) { EntityState s; s.available = true; s.text = value; result[key] = s; };
  auto number = [&](const char *key, unsigned value) { EntityState s; s.available = true; s.number = static_cast<float>(value); result[key] = s; };
  boolean("rcp_connectivity", healthy); boolean("thread_attached", attached);
  text("thread_role", role_name(role));
  const char *version = otPlatRadioGetVersionString(instance);
  if (version) { text("rcp_version", version); text("radio_version", version); }
  char rloc[7]; std::snprintf(rloc, sizeof(rloc), "0x%04x", otThreadGetRloc16(instance)); text("rloc16", rloc);
  if (attached) text("thread_identity", identity(instance));
  unsigned neighbors = 0, children = 0;
  otNeighborInfoIterator it = OT_NEIGHBOR_INFO_ITERATOR_INIT; otNeighborInfo neighbor{};
  while (otThreadGetNextNeighborInfo(instance, &it, &neighbor) == OT_ERROR_NONE) ++neighbors;
  otChildInfo child{};
  for (std::uint16_t i = 0; i < otThreadGetMaxAllowedChildren(instance); ++i)
    if (otThreadGetChildInfoByIndex(instance, i, &child) == OT_ERROR_NONE && !child.mIsStateRestoring) ++children;
  number("neighbor_count", neighbors); number("child_count", children);
  return result;
}
std::string initial_interface(const Config &config, const std::vector<Link> &links) {
  BackboneSelector choose(config.backbone_policy, 0);
  auto selected = choose.update(links, millis());
  if (!selected.empty()) return selected;
  // Fixed gateway interfaces still exist while unplugged. Bind an existing
  // eligible interface in its down state so local Thread need not await LAN.
  for (const auto &link : links) if (if_nametoindex(link.name.c_str())) return link.name;
  throw std::runtime_error("no eligible Linux backbone interface exists");
}
class InfraBinding {
 public:
  InfraBinding(otInstance *instance, std::string name, std::string omr)
      : instance_(instance), name_(std::move(name)), omr_(std::move(omr)), index_(if_nametoindex(name_.c_str())) {}
  void update(const std::string &desired) {
    if (active_ && desired == name_ && if_nametoindex(name_.c_str()) == index_) return;
    if (active_) {
#if OPENTHREAD_CONFIG_MULTICAST_DNS_ENABLE
      restore_mdns_ = restore_mdns_ || otMdnsIsEnabled(instance_);
      if (otMdnsIsEnabled(instance_)) check(otMdnsSetEnabled(instance_, false, 0), "suspend mDNS for backbone change");
#endif
      mi_infra_teardown(); active_ = false;
    }
    if (desired.empty()) {
      std::cerr << "[host] No usable backbone; Thread instance retained, border routing suspended\n";
      return;
    }
    check(mi_infra_bind(desired.c_str()), "bind infrastructure interface");
    active_ = true; name_ = desired;
    index_ = if_nametoindex(desired.c_str());
    if (!omr_.empty()) {
      otIp6Prefix prefix{};
      check(otIp6PrefixFromString(omr_.c_str(), &prefix), "parse OMR after backbone switch");
      check(otBorderRoutingSetOmrConfig(instance_, OT_BORDER_ROUTING_OMR_CONFIG_CUSTOM, &prefix, OT_ROUTE_PREFERENCE_MED), "restore configured OMR after backbone switch");
    }
#if OPENTHREAD_CONFIG_MULTICAST_DNS_ENABLE
    if (restore_mdns_ && !otMdnsIsEnabled(instance_)) check(otMdnsSetEnabled(instance_, true, if_nametoindex(desired.c_str())), "resume mDNS on new backbone");
#endif
    std::cerr << "[host] Backbone bound to " << desired << "; RCP and Thread instance retained\n";
  }
 private:
  otInstance *instance_; std::string name_, omr_; unsigned index_;
  bool active_{true}, restore_mdns_{false};
};
}

// No in-process longjmp/re-exec across live C++ worker threads. A future service
// supervisor may restart after this explicit reset exit code.
extern "C" void otPlatReset(otInstance *) {
  std::fputs("[host] OpenThread requested platform reset; exiting with code 8\n", stderr);
  std::fflush(stderr); std::_Exit(8);
}

int main(int argc, char **argv) {
  if (argc != 3 || (std::string(argv[2]) != "--no-attach" && std::string(argv[2]) != "--run" && std::string(argv[2]) != "--check-config")) {
    std::cerr << "Usage: mi-otbr-host config.yaml --check-config|--no-attach|--run\n"; return 2;
  }
  if (std::string(argv[2]) == "--check-config") {
    try { return otbr_host::report_config(std::cout, otbr_host::load_config(argv[1])); }
    catch (const std::exception &e) { std::cerr << "CONFIG_ERROR: " << e.what() << '\n'; return 1; }
  }
  if (geteuid() != 0) { std::cerr << "Run Host with root privileges on the gateway\n"; return 2; }
  const bool attach = std::string(argv[2]) == "--run";
  std::signal(SIGINT, shutdown); std::signal(SIGTERM, shutdown);
  std::thread api, web;
  std::exception_ptr api_error, web_error;
  try {
    auto config = otbr_host::load_config(argv[1]);
    std::cerr << "[host] OTBR_HOST_VERSION=" MI_OTBR_HOST_VERSION "\n";
    for (const auto &warning : config.warnings) std::cerr << "[config] " << warning << '\n';
    std::filesystem::create_directories(config.state_directory);
    const auto first_links = snapshot_links(config.candidates, config.thread_interface);
    const auto initial = initial_interface(config, first_links);
    auto url = "spinel+hdlc+uart://" + config.uart_device + "?uart-baudrate=" + std::to_string(config.baud_rate) + "&uart-flow-control&uart-exclusive";
    // Use Spinel's power setter so its RCP recovery path also restores this request.
    if (config.output_power) url += "&tx-power=" + std::to_string(*config.output_power);
    std::vector<const char *> urls{url.c_str()};
    otbrLogInit("mi-otbr-host", OTBR_LOG_INFO, true, true);
    otbr::Host::RcpHost host(config.thread_interface.c_str(), urls, initial.c_str(), false, false, config.state_directory.c_str());
    otbr::Application app(host, config.thread_interface, initial);
    bool initialized = false;
    std::mutex snapshot_mutex; Snapshot snapshot;
    std::atomic<bool> api_ready{false};
    WebQueue web_queue;
    std::unique_ptr<GatewaySystem> gateway_system;
    std::unique_ptr<ThreadProxy> thread_proxy;
    try {
      app.Init("127.0.0.1", 0); initialized = true;
      auto *instance = host.GetInstance();
      config.runtime_web = true;
      // The service restores sysctls on stop; the Thread TUN never learns LAN RAs.
      if (attach) {
        std::ofstream ra("/proc/sys/net/ipv6/conf/" + config.thread_interface + "/accept_ra");
        if (ra) ra << "0\n";
      }
      BbrTransport bbr(instance, config.thread_interface);
      ApiDiscovery discovery(instance, config);
      HaNames names(config);
      PingManager ping(instance);
      TopologyManager topology(instance);
      NodeRestartManager node_restart(instance, topology);
      std::unique_ptr<CommissionerManager> commissioner;
      if (config.commissioner_enabled) {
        commissioner = std::make_unique<CommissionerManager>(instance);
        commissioner->configure(config.commissioner_id, commissioner_network_config(config));
        commissioner->setup();
        commissioner->loop(true);
      }
      if (attach) {
        apply_dataset(instance, config);
        if (!config.omr_prefix.empty()) {
          otIp6Prefix prefix{};
          check(otIp6PrefixFromString(config.omr_prefix.c_str(), &prefix), "parse OMR");
          check(otBorderRoutingSetOmrConfig(instance, OT_BORDER_ROUTING_OMR_CONFIG_CUSTOM, &prefix, OT_ROUTE_PREFERENCE_MED), "configure OMR");
        }
        check(otIp6SetEnabled(instance, true), "enable Thread IPv6");
        check(otThreadSetEnabled(instance, true), "enable Thread");
      } else {
        std::cerr << "[host] NO_ATTACH: YAML Dataset not applied; Thread auto-attach disabled; TUN and full Host initialized\n";
      }
      if (config.output_power) {
        std::int8_t actual_power = 0;
        const auto error = otPlatRadioGetTransmitPower(instance, &actual_power);
        std::cerr << "[host] RCP output_power requested=" << *config.output_power << " dBm; ";
        if (error == OT_ERROR_NONE) std::cerr << "readback=" << static_cast<int>(actual_power) << " dBm\n";
        else std::cerr << "readback unavailable: " << otThreadErrorToString(error) << '\n';
      }
      bbr.update(initial, attach);
      if(config.proxy.enabled){thread_proxy=std::make_unique<ThreadProxy>(instance,config,attach);thread_proxy->tick(initial);}
      gateway_system = std::make_unique<GatewaySystem>(config, attach);
      std::cerr << "[host] GATEWAY_SYSTEM_ENTITIES_READY (stock firmware, Linux uptime, active-backbone IPv4; controls "
                << (attach ? "enabled" : "disabled in no-attach mode") << ")\n";
      snapshot = sample(instance);
      for (auto &item : gateway_system->snapshot(initial)) snapshot[item.first] = std::move(item.second);
      api = std::thread([&] {
        try { run_native_api(config, [&] {
                              Snapshot current;
                              { std::lock_guard<std::mutex> guard(snapshot_mutex); current = snapshot; }
                              // Bypass the periodic OTBR snapshot for LED command/readback changes.
                              current["sys_led"] = gateway_system->led_state();
                              return current;
                            }, stop, &api_ready,
                            [&](const std::string &entity, bool state) { return gateway_system->command(entity, state); }); }
        catch (...) { if (!stop) api_error = std::current_exception(); stop = true; }
      });
      web = std::thread([&] {
        try { run_web(config, [&](const WebRequest &request) { return web_queue.request(request); }, stop); }
        catch (...) { if (!stop) web_error = std::current_exception(); stop = true; }
      });
      BackboneSelector selector(config.backbone_policy, config.switch_delay_ms, initial);
      InfraBinding infra(instance, initial, attach ? config.omr_prefix : "");
      auto last_sample = millis(), last_links = last_sample;
      bool had_backbone = true;
      std::string current_backbone = initial;
      std::cerr << "[host] CORE_RUNTIME_READY mode=" << (attach ? "run" : "no-attach") << " thread_if=" << config.thread_interface << " initial_backbone=" << initial << '\n';
      std::cerr << "[host] ASYNC_PING_DATASET_BACKEND_READY\n";
      std::cerr << "[host] ASYNC_TOPOLOGY_BACKEND_READY\n";
      std::cerr << "[host] REMOTE_NODE_RESTART_EHR1_READY\n";
      std::cerr << "[host] YAML_RUNTIME_DEPLOY_READY; HA identity mapping connected\n";
      std::cerr << "[host] SRP_UNICAST_PUBLICATION_TARGET="
                << OPENTHREAD_CONFIG_NETDATA_PUBLISHER_DESIRED_NUM_UNICAST_DNS_SRP_SERVICE_ENTRIES
                << " (normal unicast selection; not a client limit)\n";
      if (commissioner) std::cerr << "[host] COMMISSIONER_BACKEND_READY (idle until explicit control request)\n";
      while (!stop) {
        if(thread_proxy)thread_proxy->tick(current_backbone);
        otbr::MainloopContext context{}; context.mMaxFd = -1; context.mTimeout.tv_sec = 0; context.mTimeout.tv_usec = 250000;
        FD_ZERO(&context.mReadFdSet); FD_ZERO(&context.mWriteFdSet); FD_ZERO(&context.mErrorFdSet);
        otbr::MainloopManager::GetInstance().Update(context);
        int rc = select(context.mMaxFd + 1, &context.mReadFdSet, &context.mWriteFdSet, &context.mErrorFdSet, &context.mTimeout);
        if (rc < 0) { if (errno == EINTR) continue; throw std::runtime_error("OTBR mainloop select failed"); }
        otbr::MainloopManager::GetInstance().Process(context);
        if (commissioner) commissioner->loop(true);
        discovery.update(current_backbone, api_ready.load());
        ping.tick();
        topology.tick();
        node_restart.tick();
        web_queue.pump_async([&](const WebRequest &request, WebCompletion done) {
          if (request.path == "/ping") { ping.request(request, std::move(done)); return; }
          if (request.path == "/topology" || request.path == "/diagnostics") {
            const auto *pan = otThreadGetExtendedPanId(instance);
            char text[17]; for (unsigned i = 0; i < 8; ++i) std::sprintf(text + 2 * i, "%02x", pan->m8[i]);
            topology.request(request, [&, done = std::move(done), pan_text = std::string(text)](WebReply reply) {
              done(names.annotate(std::move(reply), pan_text));
            }); return;
          }
          if (request.path.rfind("/commissioner/api/", 0) == 0) {
            done(commissioner ? commissioner->request(request) : otbr_host::web_error(404, "Commissioner disabled")); return;
          }
          if (request.path == "/ha/status" && request.method == "GET") {
            done({200, "{\"error\":0,\"result\":{\"status\":\"" + names.status() + "\"},\"message\":\"OK\"}"}); return;
          }
          if (request.path == "/node_restart") {
            if (!attach) { done(otbr_host::web_error(409, "Thread is disabled by no-attach mode")); return; }
            node_restart.request(request, std::move(done)); return;
          }
          done(query_web(instance, config, request));
        });
        const auto now = millis();
        if (now - last_sample >= config.update_interval_ms) {
          auto updated = sample(instance);
          for (auto &item : gateway_system->snapshot(current_backbone)) updated[item.first] = std::move(item.second);
          { std::lock_guard<std::mutex> guard(snapshot_mutex);
            if (updated["thread_role"].text != snapshot["thread_role"].text)
              std::cerr << "[host] THREAD_STATE role=" << updated["thread_role"].text << " neighbors=" << updated["neighbor_count"].number << '\n';
            snapshot = std::move(updated);
          }
          last_sample = now;
        }
        if (now - last_links >= 1000) {
          const auto links = snapshot_links(config.candidates, config.thread_interface);
          const auto desired = selector.update(links, now);
          if (!desired.empty() || had_backbone) infra.update(desired);
          current_backbone = desired;
          bbr.update(current_backbone, attach);
          discovery.update(current_backbone, api_ready.load());
          had_backbone = !desired.empty(); last_links = now;
        }
      }
      bbr.stop();
      if(thread_proxy)thread_proxy->stop();
      discovery.stop();
      stop = true; web_queue.close();
      if (web.joinable()) web.join();
      if (api.joinable()) api.join();
      ping.stop();
      node_restart.stop();
      topology.stop();
      names.stop();
      if (commissioner) commissioner->on_shutdown();
      app.Deinit(); initialized = false;
      if (api_error) std::rethrow_exception(api_error);
      if (web_error) std::rethrow_exception(web_error);
    } catch (...) {
      stop = true; web_queue.close();
      if(thread_proxy)thread_proxy->stop();
      if (web.joinable()) web.join();
      if (api.joinable()) api.join();
      if (initialized) app.Deinit();
      throw;
    }
    otbrLogDeinit();
    return 0;
  } catch (const std::exception &e) {
    stop = true;
    if (web.joinable()) web.join();
    if (api.joinable()) api.join();
    std::cerr << "HOST_ERROR: " << e.what() << '\n'; return 1;
  }
}
