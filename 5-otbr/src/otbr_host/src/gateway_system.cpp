#include "otbr_host/gateway_system.hpp"
#include "otbr_host/optimistic_switch.hpp"
#include <cJSON.h>
#include <arpa/inet.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <poll.h>
#include <spawn.h>
#include <sys/socket.h>
#include <sys/sysinfo.h>
#include <sys/wait.h>
#include <unistd.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>

extern char **environ;
namespace otbr_host {
namespace {
using Clock = std::chrono::steady_clock;
std::uint64_t steady_ms() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}
using Bytes = std::vector<unsigned char>;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
struct Socket {
  int fd{-1};
  ~Socket() { if (fd >= 0) close(fd); }
};
void require(bool value, const char *message) { if (!value) throw std::runtime_error(message); }
void mqtt_string(Bytes &b, const std::string &value) {
  require(value.size() <= 65535, "MQTT string too long");
  b.push_back(value.size() >> 8); b.push_back(value.size()); b.insert(b.end(), value.begin(), value.end());
}
class StockMiot {
 public:
  explicit StockMiot(const std::atomic<bool> &stop) : stop_(stop) {
    socket_.fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    require(socket_.fd >= 0, "MQTT socket unavailable");
    sockaddr_in addr{}; addr.sin_family = AF_INET; addr.sin_port = htons(1883); addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    int rc = connect(socket_.fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr));
    require(rc == 0 || errno == EINPROGRESS, "local MQTT connect failed");
    wait(POLLOUT, Clock::now() + std::chrono::seconds(2));
    int error = 0; socklen_t size = sizeof(error);
    require(getsockopt(socket_.fd, SOL_SOCKET, SO_ERROR, &error, &size) == 0 && !error, "local MQTT unavailable");
    Bytes body; mqtt_string(body, "MQTT"); body.insert(body.end(), {4, 2, 0, 15});
    mqtt_string(body, "otbr-system-" + std::to_string(getpid())); send(0x10, body);
    auto reply = receive(); require(reply.first == 0x20 && reply.second == Bytes({0, 0}), "MQTT connection rejected");
    body = {0, 1}; mqtt_string(body, "miio/command_ack"); body.push_back(0); send(0x82, body);
    reply = receive(); require(reply.first == 0x90 && reply.second == Bytes({0, 1, 0}), "MQTT subscription rejected");
  }
  Json request(const std::string &did, std::optional<bool> enabled) {
    // Independent IDs, below XiaomiGateway3's own command ID range.
    const unsigned id = 1 + static_cast<unsigned>(Clock::now().time_since_epoch().count() % 900000000);
    std::string json = "{\"id\":" + std::to_string(id) + ",\"method\":\"" +
        (enabled ? "set_properties" : "get_properties") + "\",\"params\":[{\"did\":\"" + did +
        "\",\"siid\":6,\"piid\":1";
    if (enabled) json += std::string(",\"value\":") + (*enabled ? "0" : "1");
    json += "}]}";
    Bytes body; mqtt_string(body, "miio/command"); body.insert(body.end(), json.begin(), json.end()); send(0x30, body);
    const auto until = Clock::now() + std::chrono::seconds(4);
    while (Clock::now() < until) {
      auto reply = receive(until); const auto &b = reply.second;
      require(reply.first == 0x30 && b.size() >= 2, "unexpected MQTT packet");
      const std::size_t topic_size = (b[0] << 8) | b[1];
      require(topic_size + 2 <= b.size(), "invalid MQTT topic");
      if (std::string(b.begin() + 2, b.begin() + 2 + topic_size) != "miio/command_ack") continue;
      const std::string payload(b.begin() + 2 + topic_size, b.end());
      Json result(cJSON_Parse(payload.c_str()), cJSON_Delete);
      if (!result) continue;
      const auto *reply_id = cJSON_GetObjectItemCaseSensitive(result.get(), "id");
      if (cJSON_IsNumber(reply_id) && reply_id->valuedouble == id) return result;
    }
    throw std::runtime_error("stock MIoT reply timeout");
  }
 private:
  void wait(short events, Clock::time_point until) {
    while (!stop_ && Clock::now() < until) {
      pollfd p{socket_.fd, events, 0}; const int rc = poll(&p, 1, 100);
      if (rc < 0 && errno == EINTR) continue;
      require(rc >= 0, "MQTT poll failed");
      if (p.revents & events) return;
      require(!(p.revents & (POLLERR | POLLHUP | POLLNVAL)), "MQTT disconnected");
    }
    throw std::runtime_error("MQTT timeout or shutdown");
  }
  void transfer(unsigned char *data, std::size_t length, bool writing, Clock::time_point until) {
    while (length) {
      wait(writing ? POLLOUT : POLLIN, until);
      const auto n = writing ? ::send(socket_.fd, data, length, MSG_NOSIGNAL) : recv(socket_.fd, data, length, 0);
      if (n < 0 && (errno == EAGAIN || errno == EINTR)) continue;
      require(n > 0, "MQTT I/O failed"); data += n; length -= n;
    }
  }
  void send(unsigned char type, const Bytes &body) {
    Bytes data{type}; auto n = body.size();
    do { unsigned char v = n % 128; n /= 128; data.push_back(v | (n ? 128 : 0)); } while (n);
    data.insert(data.end(), body.begin(), body.end());
    transfer(data.data(), data.size(), true, Clock::now() + std::chrono::seconds(2));
  }
  std::pair<unsigned char, Bytes> receive(Clock::time_point until = Clock::now() + std::chrono::seconds(2)) {
    unsigned char type = 0; transfer(&type, 1, false, until);
    std::size_t length = 0; unsigned shift = 0;
    for (;;) {
      unsigned char b = 0; transfer(&b, 1, false, until);
      length |= static_cast<std::size_t>(b & 127) << shift;
      require(length <= 16384, "MQTT packet too large");
      if (!(b & 128)) break;
      shift += 7; require(shift <= 21, "invalid MQTT length");
    }
    Bytes body(length); transfer(body.data(), body.size(), false, until); return {type, std::move(body)};
  }
  const std::atomic<bool> &stop_; Socket socket_;
};
std::string stock_did() {
  // Fixed command only. No configuration/client text is passed to a shell.
  FILE *pipe = popen("/bin/agetprop | /bin/grep 'miio_did]'", "r");
  if (!pipe) return {};
  char line[256]; std::string result;
  while (fgets(line, sizeof(line), pipe)) {
    const std::string s(line); const auto start = s.find("]: ["), end = s.find(']', start == std::string::npos ? 0 : start + 4);
    if (start != std::string::npos && end != std::string::npos) result = s.substr(start + 4, end - start - 4);
  }
  if (pclose(pipe) != 0 || result.empty() || result.size() > 32 ||
      !std::all_of(result.begin(), result.end(), [](char c) { return c >= '0' && c <= '9'; })) return {};
  return result;
}
const cJSON *led_result(const Json &reply) {
  auto *results = cJSON_GetObjectItemCaseSensitive(reply.get(), "result");
  if (!cJSON_IsArray(results)) return nullptr;
  const cJSON *item = nullptr;
  cJSON_ArrayForEach(item, results) {
    const auto *siid = cJSON_GetObjectItemCaseSensitive(item, "siid");
    const auto *piid = cJSON_GetObjectItemCaseSensitive(item, "piid");
    const auto *code = cJSON_GetObjectItemCaseSensitive(item, "code");
    if (cJSON_IsNumber(siid) && siid->valuedouble == 6 && cJSON_IsNumber(piid) && piid->valuedouble == 1 &&
        cJSON_IsNumber(code) && code->valuedouble == 0) return item;
  }
  return nullptr;
}
}
std::string format_gateway_uptime(std::uint64_t seconds) {
  std::ostringstream out;
  out << seconds / 86400 << "d:" << std::setfill('0') << std::setw(2) << seconds / 3600 % 24
      << "h:" << std::setw(2) << seconds / 60 % 60 << 'm';
  return out.str();
}
std::string gateway_firmware_version(std::istream &properties) {
  std::string line, version, build;
  while (std::getline(properties, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.rfind("ro.sys.mi_fw_ver=", 0) == 0) version = line.substr(17);
    if (line.rfind("ro.sys.mi_build_num=", 0) == 0) build = line.substr(20);
  }
  return version.empty() ? "" : version + (build.empty() ? "" : "_" + build);
}
struct GatewaySystem::Impl {
  const bool allow_control, led_enabled;
  mutable std::mutex mutex;
  std::condition_variable cv;
  std::atomic<bool> stopping{false};
  std::thread worker;
  std::optional<bool> pending_led;
  bool pending_reset{false}, reboot_requested{false};
  OptimisticSwitchState led;
  Clock::time_point last_reboot{};
  std::string firmware;
  Impl(const Config &config, bool control) : allow_control(control), led_enabled(control && config.entities.count("sys_led")) {
    std::ifstream properties("/etc/build.prop"); firmware = gateway_firmware_version(properties);
    if (led_enabled || (control && config.entities.count("reset"))) worker = std::thread([this] { loop(); });
  }
  ~Impl() { stopping = true; cv.notify_all(); if (worker.joinable()) worker.join(); }
  void loop() {
    std::string did;
    auto next_poll = Clock::now();
    while (!stopping) {
      std::optional<bool> desired; bool reboot = false;
      std::uint64_t led_revision = 0;
      {
        std::unique_lock<std::mutex> lock(mutex);
        cv.wait_until(lock, next_poll, [&] { return stopping || pending_led.has_value() || pending_reset; });
        if (stopping) return;
        desired = pending_led; pending_led.reset(); reboot = pending_reset; pending_reset = false;
        led_revision = led.revision();
      }
      if (reboot) {
        std::cerr << "[gateway-system] explicit Native API gateway reboot requested\n";
        // Permit the API packet to finish and filesystem writes to settle.
        { std::unique_lock<std::mutex> lock(mutex); cv.wait_for(lock, std::chrono::seconds(1), [&] { return stopping.load(); }); }
        if (stopping) return;
        sync();
        pid_t pid; char path[] = "/sbin/reboot"; char *argv[] = {path, nullptr};
        const int error = posix_spawn(&pid, path, nullptr, nullptr, argv, environ);
        if (!error) {
          int status = 0; pid_t waited;
          do { waited = waitpid(pid, &status, 0); } while (waited < 0 && errno == EINTR);
          if (waited < 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
            std::cerr << "[gateway-system] gateway reboot command failed\n";
        } else std::cerr << "[gateway-system] gateway reboot execution failed\n";
        { std::lock_guard<std::mutex> lock(mutex); reboot_requested = false; }
      }
      if (led_enabled && (desired.has_value() || Clock::now() >= next_poll)) {
        try {
          if (did.empty()) did = stock_did();
          require(!did.empty(), "stock device identity unavailable");
          StockMiot client(stopping);
          if (desired.has_value()) require(led_result(client.request(did, desired)) != nullptr, "stock LED write rejected");
          const auto reply = client.request(did, {}); const auto *result = led_result(reply);
          const auto *value = result ? cJSON_GetObjectItemCaseSensitive(result, "value") : nullptr;
          require(cJSON_IsNumber(value) && (value->valuedouble == 0 || value->valuedouble == 1), "stock LED readback unavailable");
          std::lock_guard<std::mutex> lock(mutex);
          led.confirm(led_revision, value->valuedouble == 0, steady_ms());
        } catch (const std::exception &) {
          std::lock_guard<std::mutex> lock(mutex); led.unavailable(led_revision);
          std::cerr << "[gateway-system] stock LED query/control unavailable; awaiting verified state\n";
        }
      }
      next_poll = Clock::now() + std::chrono::seconds(10);
    }
  }
};
GatewaySystem::GatewaySystem(const Config &config, bool allow_control) : impl_(std::make_unique<Impl>(config, allow_control)) {}
GatewaySystem::~GatewaySystem() = default;
bool GatewaySystem::command(const std::string &entity, bool state) {
  if (!impl_->allow_control) return false;
  std::lock_guard<std::mutex> lock(impl_->mutex);
  if (entity == "sys_led" && impl_->led_enabled) {
    impl_->pending_led = state;
    impl_->led.request(state, steady_ms());
  }
  else if (entity == "reset" && !impl_->reboot_requested &&
           (impl_->last_reboot == Clock::time_point{} || Clock::now() - impl_->last_reboot >= std::chrono::seconds(30))) {
    impl_->pending_reset = true; impl_->reboot_requested = true; impl_->last_reboot = Clock::now();
  }
  else return false;
  impl_->cv.notify_all(); return true;
}
Snapshot GatewaySystem::snapshot(const std::string &backbone) const {
  Snapshot result;
  auto text = [&](const char *name, std::string value) { if (!value.empty()) { EntityState s; s.available = true; s.text = std::move(value); result[name] = s; } };
  text("fw_ver", impl_->firmware);
  struct sysinfo info{};
  if (sysinfo(&info) == 0 && info.uptime >= 0) text("uptime", format_gateway_uptime(info.uptime));
  ifaddrs *addresses = nullptr;
  if (getifaddrs(&addresses) == 0) {
    for (auto *p = addresses; p; p = p->ifa_next) {
      if (!p->ifa_addr || p->ifa_addr->sa_family != AF_INET || backbone != p->ifa_name || !(p->ifa_flags & IFF_UP)) continue;
      const auto *address = reinterpret_cast<const sockaddr_in *>(p->ifa_addr);
      const auto host = ntohl(address->sin_addr.s_addr);
      if (!host || (host >> 24) == 127 || (host >> 16) == 0xa9fe) continue;
      char value[INET_ADDRSTRLEN]; if (inet_ntop(AF_INET, &address->sin_addr, value, sizeof(value))) { text("ipv4", value); break; }
    }
    freeifaddrs(addresses);
  }
  const auto led = led_state();
  if (led.available) result["sys_led"] = led;
  return result;
}
EntityState GatewaySystem::led_state() const {
  std::lock_guard<std::mutex> lock(impl_->mutex);
  return impl_->led.snapshot(steady_ms());
}
}
