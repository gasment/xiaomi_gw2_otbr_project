// Linux Web and OpenThread adapter. See web/SOURCE.md.
#include "otbr_host/web_ot.hpp"
#include "otbr_host/system_metrics.hpp"
#include "otbr_host/ping.hpp"
#include "otbr_host/topology.hpp"
#include <cJSON.h>
#include <openthread/border_agent.h>
#include <openthread/dataset.h>
#include <openthread/instance.h>
#include <openthread/ip6.h>
#include <openthread/link.h>
#include <openthread/netdata.h>
#include <openthread/border_router.h>
#include <openthread/platform/radio.h>
#include <openthread/srp_server.h>
#include <openthread/thread.h>
#include <openthread/thread_ftd.h>
#if defined(MI_BBR_USERSPACE) && MI_BBR_USERSPACE
#include <openthread/backbone_router.h>
#include <openthread/backbone_router_ftd.h>
#include "otbr_host/bbr_packet_api.hpp"
#endif
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <new>
#include <iterator>

namespace otbr_host {
namespace {
// Monotonic per-process timer, independent of system boot time and Thread role.
const auto host_started = std::chrono::steady_clock::now();
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
Json own(cJSON *value) { if (!value) throw std::bad_alloc(); return Json(value, cJSON_Delete); }
Json object() { return own(cJSON_CreateObject()); }
Json array() { return own(cJSON_CreateArray()); }
void add(cJSON *parent, const char *key, Json value) {
  if (!cJSON_AddItemToObject(parent, key, value.get())) throw std::bad_alloc();
  value.release();
}
void push(cJSON *parent, Json value) {
  if (!cJSON_AddItemToArray(parent, value.get())) throw std::bad_alloc();
  value.release();
}
void str(cJSON *o, const char *key, const std::string &value) { add(o, key, own(cJSON_CreateString(value.c_str()))); }
void num(cJSON *o, const char *key, double value) { add(o, key, own(cJSON_CreateNumber(value))); }
void boolean(cJSON *o, const char *key, bool value) { add(o, key, own(cJSON_CreateBool(value))); }
std::string hex(const std::uint8_t *bytes, std::size_t count) {
  static const char chars[] = "0123456789abcdef";
  std::string s; s.reserve(count * 2);
  for (std::size_t i = 0; i < count; ++i) { s += chars[bytes[i] >> 4]; s += chars[bytes[i] & 15]; }
  return s;
}
std::string ip(const otIp6Address *addr) {
  if (!addr) return {};
  char text[OT_IP6_ADDRESS_STRING_SIZE]; otIp6AddressToString(addr, text, sizeof(text)); return text;
}
WebReply reply(Json root, bool wrapped) {
  if (wrapped) {
    auto wrapper = object(); num(wrapper.get(), "error", 0);
    add(wrapper.get(), "result", std::move(root)); str(wrapper.get(), "message", "OK"); root = std::move(wrapper);
  }
  std::unique_ptr<char, decltype(&cJSON_free)> text(cJSON_PrintUnformatted(root.get()), cJSON_free);
  if (!text) throw std::bad_alloc();
  return {200, text.get()};
}
Json leader(otInstance *instance) {
  otLeaderData data{};
  if (otThreadGetLeaderData(instance, &data) != OT_ERROR_NONE) return own(cJSON_CreateNull());
  auto out = object();
  num(out.get(), "PartitionId", data.mPartitionId); num(out.get(), "Weighting", data.mWeighting);
  num(out.get(), "DataVersion", data.mDataVersion); num(out.get(), "StableDataVersion", data.mStableDataVersion);
  num(out.get(), "LeaderRouterId", data.mLeaderRouterId); return out;
}
unsigned router_count(otInstance *instance) {
  unsigned count = 0; otRouterInfo info{};
  for (unsigned id = 0; id <= otThreadGetMaxRouterId(instance); ++id)
    if (otThreadGetRouterInfo(instance, static_cast<std::uint16_t>(id), &info) == OT_ERROR_NONE) ++count;
  return count;
}
Json node(otInstance *i) {
  auto o = object(); str(o.get(), "NetworkName", otThreadGetNetworkName(i));
  str(o.get(), "ExtPanId", hex(otThreadGetExtendedPanId(i)->m8, 8));
  str(o.get(), "ExtAddress", hex(otLinkGetExtendedAddress(i)->m8, 8));
  str(o.get(), "RlocAddress", ip(otThreadGetRloc(i))); add(o.get(), "LeaderData", leader(i));
  num(o.get(), "State", otThreadGetDeviceRole(i)); num(o.get(), "Rloc16", otThreadGetRloc16(i));
  num(o.get(), "NumOfRouter", router_count(i)); return o;
}
Json addresses(otInstance *i) {
  auto out = array();
  for (auto *a = otIp6GetUnicastAddresses(i); a; a = a->mNext) {
    auto o = object(); str(o.get(), "address", ip(&a->mAddress)); num(o.get(), "prefixLength", a->mPrefixLength);
    const char *origin = "unknown";
    switch (a->mAddressOrigin) {
      case OT_ADDRESS_ORIGIN_THREAD: origin = "thread"; break;
      case OT_ADDRESS_ORIGIN_SLAAC: origin = "slaac"; break;
      case OT_ADDRESS_ORIGIN_DHCPV6: origin = "dhcpv6"; break;
      case OT_ADDRESS_ORIGIN_MANUAL: origin = "manual"; break;
    }
    str(o.get(), "origin", origin); boolean(o.get(), "preferred", a->mPreferred);
    boolean(o.get(), "meshLocal", a->mMeshLocal); boolean(o.get(), "rloc", a->mRloc); push(out.get(), std::move(o));
  }
  return out;
}
Json bbr_status(otInstance *i) {
  auto out = object();
#if defined(MI_BBR_USERSPACE) && MI_BBR_USERSPACE
  const auto state = otBackboneRouterGetState(i);
  str(out.get(), "backend", "userspace-af-packet");
  boolean(out.get(), "experimental", true);
  str(out.get(), "state", state == OT_BACKBONE_ROUTER_STATE_PRIMARY ? "primary" :
      state == OT_BACKBONE_ROUTER_STATE_SECONDARY ? "secondary" : "disabled");
  otBackboneRouterConfig primary{};
  if (otBackboneRouterGetPrimary(i, &primary) == OT_ERROR_NONE) {
    auto p = object(); num(p.get(), "rloc16", primary.mServer16);
    num(p.get(), "sequence", primary.mSequenceNumber); num(p.get(), "mlr_timeout", primary.mMlrTimeout);
    add(out.get(), "primary", std::move(p));
  } else add(out.get(), "primary", own(cJSON_CreateNull()));
  auto listeners = array();
  otBackboneRouterMulticastListenerIterator iterator = OT_BACKBONE_ROUTER_MULTICAST_LISTENER_ITERATOR_INIT;
  otBackboneRouterMulticastListenerInfo entry{};
  unsigned count = 0;
  while (count++ < 256 && otBackboneRouterMulticastListenerGetNext(i, &iterator, &entry) == OT_ERROR_NONE) {
    auto row = object(); str(row.get(), "address", ip(&entry.mAddress)); num(row.get(), "timeout", entry.mTimeout);
    push(listeners.get(), std::move(row));
  }
  add(out.get(), "listeners", std::move(listeners));
  const auto counters = mi_bbr_packet_counters();
  boolean(out.get(), "forwarder_ready", state == OT_BACKBONE_ROUTER_STATE_PRIMARY && counters.open_taps == 2);
  auto c = object(); num(c.get(), "open_taps", counters.open_taps);
  num(c.get(), "captured_thread", counters.captured_thread); num(c.get(), "captured_lan", counters.captured_lan);
  num(c.get(), "injected_thread", counters.injected_thread); num(c.get(), "injected_lan", counters.injected_lan);
  num(c.get(), "errors", counters.errors); add(out.get(), "packet_counters", std::move(c));
#else
  (void)i;
  str(out.get(), "backend", "disabled"); str(out.get(), "state", "disabled");
  boolean(out.get(), "experimental", false); boolean(out.get(), "forwarder_ready", false);
#endif
  return out;
}

Json srp(otInstance *i) {
  auto out = object(); auto state = otSrpServerGetState(i);
  str(out.get(), "state", state == OT_SRP_SERVER_STATE_RUNNING ? "running" : state == OT_SRP_SERVER_STATE_STOPPED ? "stopped" : "disabled");
  str(out.get(), "domain", otSrpServerGetDomain(i)); num(out.get(), "port", otSrpServerGetPort(i));
  num(out.get(), "desired_unicast_servers", OPENTHREAD_CONFIG_NETDATA_PUBLISHER_DESIRED_NUM_UNICAST_DNS_SRP_SERVICE_ENTRIES);
  auto hosts = array(); bool truncated = false; unsigned nhosts = 0;
  const otSrpServerHost *host = nullptr;
  while ((host = otSrpServerGetNextHost(i, host))) {
    if (++nhosts > 64) { truncated = true; break; }
    auto entry = object(); str(entry.get(), "name", otSrpServerHostGetFullName(host));
    boolean(entry.get(), "deleted", otSrpServerHostIsDeleted(host));
    auto ips = array(), services = array(); std::uint8_t count = 0;
    const auto *list = otSrpServerHostGetAddresses(host, &count);
    for (unsigned n = 0; n < count && n < 16; ++n) push(ips.get(), own(cJSON_CreateString(ip(list + n).c_str())));
    if (count > 16) truncated = true;
    const otSrpServerService *service = nullptr; unsigned nservices = 0;
    while ((service = otSrpServerHostGetNextService(host, service))) {
      if (++nservices > 32) { truncated = true; break; }
      auto s = object(); str(s.get(), "instance", otSrpServerServiceGetInstanceName(service));
      str(s.get(), "type", otSrpServerServiceGetServiceName(service));
      num(s.get(), "port", otSrpServerServiceGetPort(service)); boolean(s.get(), "deleted", otSrpServerServiceIsDeleted(service));
      push(services.get(), std::move(s));
    }
    add(entry.get(), "addresses", std::move(ips)); add(entry.get(), "services", std::move(services)); push(hosts.get(), std::move(entry));
  }
  add(out.get(), "hosts", std::move(hosts)); boolean(out.get(), "truncated", truncated); return out;
}
Json properties(otInstance *i, const Config &) {
  auto o = object();
  str(o.get(), "IPv6:LinkLocalAddress", ip(otThreadGetLinkLocalIp6Address(i)));
  str(o.get(), "IPv6:RoutingLocalAddress", ip(otThreadGetRloc(i)));
  str(o.get(), "IPv6:MeshLocalAddress", ip(otThreadGetMeshLocalEid(i)));
  otIp6Prefix prefix{}; prefix.mLength = 64;
  std::copy_n(otThreadGetMeshLocalPrefix(i)->m8, 8, prefix.mPrefix.mFields.m8);
  char prefix_text[OT_IP6_PREFIX_STRING_SIZE]; otIp6PrefixToString(&prefix, prefix_text, sizeof(prefix_text));
  str(o.get(), "IPv6:MeshLocalPrefix", prefix_text);
  str(o.get(), "Network:Name", otThreadGetNetworkName(i)); char pan[8]; std::snprintf(pan, sizeof(pan), "0x%x", otLinkGetPanId(i));
  str(o.get(), "Network:PANID", pan); str(o.get(), "Network:PartitionID", std::to_string(otThreadGetPartitionId(i)));
  str(o.get(), "Network:XPANID", hex(otThreadGetExtendedPanId(i)->m8, 8));
  otBorderAgentId ba{};
  if (otBorderAgentGetId(i, &ba) == OT_ERROR_NONE) str(o.get(), "Network:BorderAgentID", hex(ba.mId, sizeof(ba.mId)));
  str(o.get(), "OpenThread:Version", otGetVersionString()); str(o.get(), "OpenThread:Version API", std::to_string(OPENTHREAD_API_VERSION));
  const auto role = otThreadGetDeviceRole(i); str(o.get(), "Thread:Role", otThreadDeviceRoleToString(role));
  str(o.get(), "WPAN service", role == OT_DEVICE_ROLE_DISABLED ? "offline" : role == OT_DEVICE_ROLE_DETACHED ? "associating" : "associated");
  otPskc pskc{};
  otThreadGetPskc(i, &pskc);
  str(o.get(), "OpenThread:PSKc", hex(pskc.m8, sizeof(pskc.m8)));
  str(o.get(), "RCP:Channel", std::to_string(otLinkGetChannel(i)));
  otExtAddress eui{}; otLinkGetFactoryAssignedIeeeEui64(i, &eui); str(o.get(), "RCP:EUI64", hex(eui.m8, 8));
  std::int8_t power{};
  // Display only the live RCP reading. Never substitute YAML's requested power.
  if (otPlatRadioGetTransmitPower(i, &power) == OT_ERROR_NONE) str(o.get(), "RCP:TxPower", std::to_string(power) + " dBm");
  const char *version = otPlatRadioGetVersionString(i);
  str(o.get(), "RCP:Version", version ? version : "unavailable"); str(o.get(), "Radio:Version", version ? version : "unavailable");
  str(o.get(), "Radio:Mode", "uart_rcp");
  str(o.get(), "App:Version", MI_OTBR_HOST_VERSION); str(o.get(), "App:ProjectName", "Xiaomi GW2 OTBR"); str(o.get(), "App:CompileTime", __DATE__ " " __TIME__);
  const auto metrics = read_system_metrics();
  str(o.get(), "System:Uptime", metrics.uptime);
  str(o.get(), "System:AvailableMemory", metrics.available_memory);
  if (metrics.available_bytes) num(o.get(), "System:AvailableMemoryBytes", *metrics.available_bytes);
  const auto host_seconds = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::seconds>(
      std::chrono::steady_clock::now() - host_started).count());
  str(o.get(), "App:Uptime", format_system_uptime(host_seconds));
  num(o.get(), "App:UptimeSeconds", static_cast<double>(host_seconds));
  return o;
}
Json dataset(const otOperationalDataset &d) {
  auto o = object(); const auto &c = d.mComponents;
  if (c.mIsActiveTimestampPresent) {
    auto t = object(); num(t.get(), "Seconds", static_cast<double>(d.mActiveTimestamp.mSeconds));
    num(t.get(), "Ticks", d.mActiveTimestamp.mTicks); boolean(t.get(), "Authoritative", d.mActiveTimestamp.mAuthoritative);
    add(o.get(), "ActiveTimestamp", std::move(t));
  }
  if (c.mIsNetworkKeyPresent) str(o.get(), "NetworkKey", hex(d.mNetworkKey.m8, sizeof(d.mNetworkKey.m8)));
  if (c.mIsNetworkNamePresent) str(o.get(), "NetworkName", d.mNetworkName.m8);
  if (c.mIsExtendedPanIdPresent) str(o.get(), "ExtPanId", hex(d.mExtendedPanId.m8, sizeof(d.mExtendedPanId.m8)));
  if (c.mIsMeshLocalPrefixPresent) {
    otIp6Prefix prefix{}; prefix.mLength = 64;
    std::copy_n(d.mMeshLocalPrefix.m8, 8, prefix.mPrefix.mFields.m8);
    char text[OT_IP6_PREFIX_STRING_SIZE]; otIp6PrefixToString(&prefix, text, sizeof(text));
    str(o.get(), "MeshLocalPrefix", text);
  }
  if (c.mIsPanIdPresent) num(o.get(), "PanId", d.mPanId);
  if (c.mIsChannelPresent) num(o.get(), "Channel", d.mChannel);
  if (c.mIsPskcPresent) str(o.get(), "PSKc", hex(d.mPskc.m8, sizeof(d.mPskc.m8)));
  if (c.mIsChannelMaskPresent) num(o.get(), "ChannelMask", d.mChannelMask);
  if (c.mIsSecurityPolicyPresent) {
    const auto &s = d.mSecurityPolicy; auto p = object();
    num(p.get(), "RotationTime", s.mRotationTime); boolean(p.get(), "ObtainNetworkKey", s.mObtainNetworkKeyEnabled);
    boolean(p.get(), "NativeCommissioning", s.mNativeCommissioningEnabled); boolean(p.get(), "Routers", s.mRoutersEnabled);
    boolean(p.get(), "ExternalCommissioning", s.mExternalCommissioningEnabled);
    boolean(p.get(), "CommercialCommissioning", s.mCommercialCommissioningEnabled);
    boolean(p.get(), "AutonomousEnrollment", s.mAutonomousEnrollmentEnabled);
    boolean(p.get(), "NetworkKeyProvisioning", s.mNetworkKeyProvisioningEnabled);
    boolean(p.get(), "TobleLink", s.mTobleLinkEnabled); boolean(p.get(), "NonCcmRouters", s.mNonCcmRoutersEnabled);
    add(o.get(), "SecurityPolicy", std::move(p));
  }
  return o;
}
}
WebReply ping_result(const otPingSenderReply *replies, unsigned count,
                     const otPingSenderStatistics &statistics, bool truncated) {
  auto result = object(), list = array(), stats = object();
  for (unsigned i = 0; i < count; ++i) {
    const auto &r = replies[i]; auto entry = object(); str(entry.get(), "from", ip(&r.mSenderAddress));
    num(entry.get(), "seq", r.mSequenceNumber); num(entry.get(), "size", r.mSize);
    num(entry.get(), "rtt", r.mRoundTripTime); num(entry.get(), "hlim", r.mHopLimit);
    push(list.get(), std::move(entry));
  }
  num(stats.get(), "sent", statistics.mSentCount); num(stats.get(), "received", statistics.mReceivedCount);
  const unsigned lost = statistics.mSentCount > statistics.mReceivedCount ? statistics.mSentCount - statistics.mReceivedCount : 0;
  num(stats.get(), "loss_percent", statistics.mSentCount ? lost * 100.0 / statistics.mSentCount : 0);
  if (statistics.mReceivedCount) {
    num(stats.get(), "rtt_min", statistics.mMinRoundTripTime);
    num(stats.get(), "rtt_avg", static_cast<double>(statistics.mTotalRoundTripTime) / statistics.mReceivedCount);
    num(stats.get(), "rtt_max", statistics.mMaxRoundTripTime);
  }
  boolean(result.get(), "truncated", truncated);
  add(result.get(), "replies", std::move(list)); add(result.get(), "statistics", std::move(stats));
  return reply(std::move(result), true);
}
TopologyNode diagnostic_node(otInstance *instance, const otMessage *message) {
  TopologyNode out; auto o = object();
  std::vector<std::uint16_t> child_ids;
  auto mode = [&](const otLinkModeConfig &m) {
    auto v = object(); num(v.get(), "RxOnWhenIdle", m.mRxOnWhenIdle);
    num(v.get(), "DeviceType", m.mDeviceType); num(v.get(), "NetworkData", m.mNetworkData); return v;
  };
  otNetworkDiagIterator iterator = OT_NETWORK_DIAGNOSTIC_ITERATOR_INIT;
  otNetworkDiagTlv tlv{}; otError error;
  while ((error = otThreadGetNextDiagnosticTlv(message, &iterator, &tlv)) == OT_ERROR_NONE) {
    const auto &d = tlv.mData;
    switch (tlv.mType) {
      case OT_NETWORK_DIAGNOSTIC_TLV_EXT_ADDRESS: str(o.get(), "ExtAddress", hex(d.mExtAddress.m8, 8)); break;
      case OT_NETWORK_DIAGNOSTIC_TLV_SHORT_ADDRESS: out.rloc = d.mAddr16; num(o.get(), "Rloc16", out.rloc); break;
      case OT_NETWORK_DIAGNOSTIC_TLV_MODE: add(o.get(), "Mode", mode(d.mMode)); break;
      case OT_NETWORK_DIAGNOSTIC_TLV_TIMEOUT: num(o.get(), "Timeout", d.mTimeout); break;
      case OT_NETWORK_DIAGNOSTIC_TLV_LEADER_DATA: {
        const auto &l = d.mLeaderData; auto v = object();
        num(v.get(), "PartitionId", l.mPartitionId); num(v.get(), "Weighting", l.mWeighting);
        num(v.get(), "DataVersion", l.mDataVersion); num(v.get(), "StableDataVersion", l.mStableDataVersion);
        num(v.get(), "LeaderRouterId", l.mLeaderRouterId); add(o.get(), "LeaderData", std::move(v)); break;
      }
      case OT_NETWORK_DIAGNOSTIC_TLV_ROUTE: {
        if (d.mRoute.mRouteCount > std::size(d.mRoute.mRouteData)) throw std::runtime_error("Invalid diagnostic route count");
        auto v = object(), routes = array(); num(v.get(), "IdSequence", d.mRoute.mIdSequence);
        for (unsigned n = 0; n < d.mRoute.mRouteCount; ++n) {
          const auto &r = d.mRoute.mRouteData[n]; auto row = object();
          num(row.get(), "RouteId", r.mRouterId); num(row.get(), "LinkQualityOut", r.mLinkQualityOut);
          num(row.get(), "LinkQualityIn", r.mLinkQualityIn); num(row.get(), "RouteCost", r.mRouteCost);
          push(routes.get(), std::move(row));
        }
        add(v.get(), "RouteData", std::move(routes)); add(o.get(), "Route", std::move(v)); break;
      }
      case OT_NETWORK_DIAGNOSTIC_TLV_IP6_ADDR_LIST: {
        if (d.mIp6AddrList.mCount > std::size(d.mIp6AddrList.mList)) throw std::runtime_error("Invalid diagnostic address count");
        auto ips = array(), omr = array();
        for (unsigned n = 0; n < d.mIp6AddrList.mCount; ++n) {
          const auto &address = d.mIp6AddrList.mList[n]; const auto text = ip(&address);
          push(ips.get(), own(cJSON_CreateString(text.c_str())));
          otNetworkDataIterator it = OT_NETWORK_DATA_ITERATOR_INIT; otBorderRouterConfig prefix{};
          while (otNetDataGetNextOnMeshPrefix(instance, &it, &prefix) == OT_ERROR_NONE) {
            if (prefix.mPrefix.mLength == 64 && prefix.mStable && prefix.mOnMesh && prefix.mSlaac &&
                !std::equal(prefix.mPrefix.mPrefix.mFields.m8, prefix.mPrefix.mPrefix.mFields.m8 + 8, otThreadGetMeshLocalPrefix(instance)->m8) &&
                std::equal(prefix.mPrefix.mPrefix.mFields.m8, prefix.mPrefix.mPrefix.mFields.m8 + 8, address.mFields.m8)) {
              push(omr.get(), own(cJSON_CreateString(text.c_str()))); break;
            }
          }
        }
        add(o.get(), "IP6AddressList", std::move(ips)); add(o.get(), "OMRAddressList", std::move(omr)); break;
      }
      case OT_NETWORK_DIAGNOSTIC_TLV_CHILD_TABLE: {
        if (d.mChildTable.mCount > std::size(d.mChildTable.mTable)) throw std::runtime_error("Invalid diagnostic child count");
        auto children = array();
        for (unsigned n = 0; n < d.mChildTable.mCount; ++n) {
          const auto &child = d.mChildTable.mTable[n]; auto row = object();
          num(row.get(), "ChildId", child.mChildId); num(row.get(), "Timeout", child.mTimeout);
          add(row.get(), "Mode", mode(child.mMode)); push(children.get(), std::move(row)); child_ids.push_back(child.mChildId);
        }
        add(o.get(), "ChildTable", std::move(children)); break;
      }
      default: break;
    }
  }
  if (error != OT_ERROR_NOT_FOUND) throw std::runtime_error("Malformed diagnostic TLV response");
  if (out.rloc != 0xffff && !(out.rloc & 0x03ff))
    for (auto id : child_ids) out.children.push_back(static_cast<std::uint16_t>(out.rloc | id));
  out.json = reply(std::move(o), false).body; return out;
}
std::string commissioner_network_config(const Config &c) {
  auto o = object(); num(o.get(), "channel", c.channel); num(o.get(), "pan_id", c.pan_id);
  str(o.get(), "network_name", c.network_name); str(o.get(), "network_key", c.network_key);
  str(o.get(), "ext_pan_id", c.ext_pan_id); str(o.get(), "pskc", c.pskc);
  str(o.get(), "mesh_local_prefix", c.mesh_local_prefix); str(o.get(), "omr_prefix", c.omr_prefix);
  return reply(std::move(o), false).body;
}
WebReply query_web(otInstance *i, const Config &c, const WebRequest &r) {
  if (r.method == "POST") {
    if (r.path == "/ping" || r.path == "/node_restart" || r.path == "/commissioner/api/control")
      return web_error(501, "Asynchronous control migration pending");
    return web_error(405, "Network parameters are defined by YAML");
  }
  if (r.method != "GET" && r.method != "HEAD") return web_error(405, "Method not allowed");
  if (r.path == "/get_properties") return reply(properties(i, c), true);
  if (r.path == "/node_information" || r.path == "/node") return reply(node(i), r.path == "/node_information");
  if (r.path == "/ipaddr") return reply(addresses(i), true);
  if (r.path == "/srp") return reply(srp(i), true);
  if (r.path == "/bbr") return reply(bbr_status(i), true);
  if (r.path == "/node/dataset/active") {
    otOperationalDataset active{};
    const auto error = otDatasetGetActive(i, &active);
    if (error == OT_ERROR_NOT_FOUND) return web_error(404, "Active Dataset unavailable");
    if (error != OT_ERROR_NONE) return web_error(503, "Active Dataset read failed");
    return reply(dataset(active), false);
  }
  if (r.path == "/node/state") return reply(own(cJSON_CreateString(otThreadDeviceRoleToString(otThreadGetDeviceRole(i)))), false);
  if (r.path == "/node/rloc") return reply(own(cJSON_CreateString(ip(otThreadGetRloc(i)).c_str())), false);
  if (r.path == "/node/rloc16") return reply(own(cJSON_CreateNumber(otThreadGetRloc16(i))), false);
  if (r.path == "/node/ext-address") return reply(own(cJSON_CreateString(hex(otLinkGetExtendedAddress(i)->m8, 8).c_str())), false);
  if (r.path == "/node/network-name") return reply(own(cJSON_CreateString(otThreadGetNetworkName(i))), false);
  if (r.path == "/node/leader-data") return reply(leader(i), false);
  if (r.path == "/node/num-of-router") return reply(own(cJSON_CreateNumber(router_count(i))), false);
  if (r.path == "/node/ext-panid") return reply(own(cJSON_CreateString(hex(otThreadGetExtendedPanId(i)->m8, 8).c_str())), false);
  if (r.path == "/node/ba-id") {
    otBorderAgentId ba{};
    if (otBorderAgentGetId(i, &ba) != OT_ERROR_NONE) return web_error(503, "Border Agent ID unavailable");
    return reply(own(cJSON_CreateString(hex(ba.mId, sizeof(ba.mId)).c_str())), false);
  }
  if (r.path == "/topology" || r.path == "/diagnostics" || r.path == "/commissioner/api/status")
    return web_error(501, "Endpoint migration pending");
  return web_error(404, "Not found");
}
}
