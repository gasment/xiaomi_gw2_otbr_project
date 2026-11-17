#include "otbr_host/native_api.hpp"
#include <noise/protocol.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cctype>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>
#include <dirent.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

namespace otbr_host {
namespace {
using Bytes = std::vector<std::uint8_t>;
using Clock = std::chrono::steady_clock;
constexpr std::size_t kMaxFrame = 4096, kMaxClients = 4;
std::mutex log_mutex;
void log(const std::string &message) {
  std::lock_guard<std::mutex> guard(log_mutex);
  std::cerr << "[native-api] " << message << std::endl;
}
[[noreturn]] void fail(const char *why) { throw std::runtime_error(why); }
void noise_check(int code) { if (code != 0) fail("Noise operation rejected"); }
struct Fd {
  int value;
  explicit Fd(int fd) : value(fd) {}
  ~Fd() { if (value >= 0) close(value); }
  Fd(const Fd &) = delete;
  Fd &operator=(const Fd &) = delete;
};
struct HandshakeDeleter { void operator()(NoiseHandshakeState *p) const { if (p) noise_handshakestate_free(p); } };
struct CipherDeleter { void operator()(NoiseCipherState *p) const { if (p) noise_cipherstate_free(p); } };
using Handshake = std::unique_ptr<NoiseHandshakeState, HandshakeDeleter>;
using Cipher = std::unique_ptr<NoiseCipherState, CipherDeleter>;

bool wait_socket(int fd, short events, int milliseconds, const std::atomic<bool> &stop) {
  auto end = Clock::now() + std::chrono::milliseconds(milliseconds);
  while (!stop.load()) {
    auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(end - Clock::now()).count();
    if (remaining <= 0) return false;
    pollfd item{fd, events, 0};
    int rc = poll(&item, 1, static_cast<int>(std::min<std::int64_t>(remaining, 250)));
    if (rc < 0) { if (errno == EINTR) continue; fail("socket poll failed"); }
    if (rc == 0) continue;
    if (item.revents & events) return true;
    if (item.revents & (POLLERR | POLLHUP | POLLNVAL)) fail("connection closed");
  }
  fail("server stopping");
}
void transfer(int fd, std::uint8_t *data, std::size_t size, bool writing, const std::atomic<bool> &stop) {
  const auto deadline = Clock::now() + std::chrono::seconds(10);
  while (size) {
    auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
    if (remaining <= 0 || !wait_socket(fd, writing ? POLLOUT : POLLIN, static_cast<int>(remaining), stop)) fail("frame timeout");
    ssize_t count = writing ? send(fd, data, size, MSG_NOSIGNAL) : recv(fd, data, size, 0);
    if (count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
    if (count <= 0) fail("connection closed");
    data += count; size -= static_cast<std::size_t>(count);
  }
}
Bytes read_frame(int fd, std::size_t limit, const std::atomic<bool> &stop) {
  std::array<std::uint8_t, 3> header{};
  transfer(fd, header.data(), header.size(), false, stop);
  if (header[0] != 1) fail("encrypted Native API framing required");
  const auto length = (static_cast<unsigned>(header[1]) << 8) | header[2];
  if (length > limit) fail("Native API frame too large");
  Bytes result(length);
  transfer(fd, result.data(), result.size(), false, stop);
  return result;
}
void write_frame(int fd, Bytes payload, const std::atomic<bool> &stop) {
  if (payload.size() > kMaxFrame) fail("outgoing frame too large");
  Bytes frame{1, static_cast<std::uint8_t>(payload.size() >> 8), static_cast<std::uint8_t>(payload.size())};
  frame.insert(frame.end(), payload.begin(), payload.end());
  transfer(fd, frame.data(), frame.size(), true, stop);
}
std::array<std::uint8_t, 32> decode_key(const std::string &text) {
  const std::string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  if (text.size() != 44 || text.back() != '=') fail("invalid configured Noise key");
  std::array<std::uint8_t, 32> result{};
  unsigned bits = 0, accumulator = 0; std::size_t count = 0;
  for (char c : text) {
    if (c == '=') break;
    auto value = alphabet.find(c);
    if (value == std::string::npos) fail("invalid configured Noise key");
    accumulator = (accumulator << 6) | static_cast<unsigned>(value); bits += 6;
    if (bits >= 8) { bits -= 8; if (count >= result.size()) fail("invalid key length"); result[count++] = static_cast<std::uint8_t>(accumulator >> bits); }
  }
  if (count != 32 || std::all_of(result.begin(), result.end(), [](auto b) { return b == 0; })) fail("Noise key must be 32 bytes and not all zeroes");
  return result;
}
bool mac_valid(const std::string &s) {
  if (s.size() != 17) return false;
  bool nonzero = false;
  for (std::size_t i = 0; i < s.size(); ++i) {
    if (i % 3 == 2) { if (s[i] != ':') return false; }
    else { if (!std::isxdigit(static_cast<unsigned char>(s[i]))) return false; if (s[i] != '0') nonzero = true; }
  }
  const unsigned first = static_cast<unsigned>(std::stoul(s.substr(0, 2), nullptr, 16));
  return nonzero && !(first & 1);
}
std::string device_mac(const Config &config) {
  if (!config.mac_address.empty()) {
    if (!mac_valid(config.mac_address)) fail("invalid device.mac_address");
    return config.mac_address;
  }
  // Read a fixed hardware interface independent of whichever backbone is active.
  std::vector<std::string> names{"eth0", "wlan0", "wlan1"};
  if (DIR *dir = opendir("/sys/class/net")) {
    std::vector<std::string> extra;
    while (auto *item = readdir(dir)) if (item->d_name[0] != '.') extra.emplace_back(item->d_name);
    closedir(dir); std::sort(extra.begin(), extra.end()); names.insert(names.end(), extra.begin(), extra.end());
  }
  for (const auto &name : names) {
    if (name == config.thread_interface || name == "lo") continue;
    std::ifstream in("/sys/class/net/" + name + "/address"); std::string mac;
    if (in >> mac && mac_valid(mac)) return mac;
  }
  fail("cannot determine stable MAC; configure device.mac_address");
}
void varint(Bytes &out, std::uint64_t value) {
  while (value >= 128) { out.push_back(static_cast<std::uint8_t>(value) | 128); value >>= 7; }
  out.push_back(static_cast<std::uint8_t>(value));
}
void integer(Bytes &out, unsigned field, std::uint64_t value) { varint(out, field << 3); varint(out, value); }
void string(Bytes &out, unsigned field, const std::string &value) {
  if (value.empty()) return;
  varint(out, (field << 3) | 2); varint(out, value.size()); out.insert(out.end(), value.begin(), value.end());
}
void fixed32(Bytes &out, unsigned field, std::uint32_t value) {
  varint(out, (field << 3) | 5);
  for (unsigned i = 0; i < 4; ++i) out.push_back(static_cast<std::uint8_t>(value >> (8 * i)));
}
std::uint64_t read_varint(const Bytes &in, std::size_t &at) {
  std::uint64_t v = 0;
  for (unsigned shift = 0; shift < 70; shift += 7) {
    if (at >= in.size()) fail("truncated protobuf varint");
    const auto b = in[at++];
    if (shift == 63 && b > 1) fail("protobuf varint overflow");
    v |= static_cast<std::uint64_t>(b & 127) << shift;
    if (!(b & 128)) return v;
  }
  fail("protobuf varint overflow");
}
std::map<unsigned, std::uint64_t> validate_pb(const Bytes &in) {
  std::map<unsigned, std::uint64_t> numbers;
  std::size_t at = 0;
  while (at < in.size()) {
    const auto tag = read_varint(in, at);
    if (tag > 0xffffffffu) fail("invalid protobuf tag");
    const auto field = static_cast<unsigned>(tag >> 3), wire = static_cast<unsigned>(tag & 7);
    if (field == 0 || field > 0x1fffffff) fail("invalid protobuf field");
    std::uint64_t skip = 0;
    switch (wire) {
      case 0: numbers[field] = read_varint(in, at); break;
      case 1: skip = 8; break;
      case 2: skip = read_varint(in, at); break;
      case 5: skip = 4; break;
      default: fail("unsupported protobuf wire type");
    }
    if (skip > in.size() - at) fail("truncated protobuf field");
    at += static_cast<std::size_t>(skip);
  }
  return numbers;
}
std::uint32_t entity_key(const std::string &id) {
  std::uint32_t h = 2166136261u;
  for (unsigned char c : id) { h ^= c; h *= 16777619u; }
  return h ? h : 1;
}
int kind(const std::string &s) {
  if (s == "reset") return 61;
  if (s == "sys_led") return 17;
  if (s == "rcp_connectivity" || s == "thread_attached") return 12;
  if (s == "neighbor_count" || s == "child_count") return 16;
  return 18;
}
unsigned category(const EntityConfig &e) { return e.category == "diagnostic" ? 2 : e.category == "config" ? 1 : 0; }
Bytes entity_info(const std::string &type, const EntityConfig &e) {
  Bytes out;
  string(out, 1, e.id); fixed32(out, 2, entity_key(e.id)); string(out, 3, e.name);
  if (kind(type) == 12) { string(out, 5, "connectivity"); string(out, 8, e.icon); integer(out, 9, category(e)); }
  else if (kind(type) == 16) { string(out, 5, e.icon); integer(out, 7, 0); integer(out, 13, category(e)); }
  else if (kind(type) == 17) { string(out, 5, e.icon); integer(out, 8, category(e)); }
  else if (kind(type) == 61) { string(out, 5, e.icon); integer(out, 7, category(e)); string(out, 8, "restart"); }
  else { string(out, 5, e.icon); integer(out, 7, category(e)); }
  return out;
}
Bytes entity_state(const std::string &type, const EntityConfig &e, const EntityState &s) {
  Bytes out; fixed32(out, 1, entity_key(e.id));
  if (!s.available) { integer(out, kind(type) == 17 ? 4 : 3, 1); return out; }
  if (kind(type) == 12 || kind(type) == 17) integer(out, 2, s.boolean ? 1 : 0);
  else if (kind(type) == 16) { std::uint32_t raw; static_assert(sizeof(raw) == sizeof(s.number)); std::memcpy(&raw, &s.number, sizeof(raw)); fixed32(out, 2, raw); }
  else string(out, 2, s.text);
  return out;
}
class Connection {
 public:
  Connection(int socket, const Config &c, const std::string &mac, const SnapshotProvider &provider, std::atomic<bool> &stop,
             const EntityCommandHandler &command)
      : socket_(socket), config_(c), mac_(mac), provider_(provider), stop_(stop), command_(command) {}
  void run() {
    if (!config_.api_key.empty()) handshake();
    log(config_.api_key.empty() ? "plaintext client connected" : "encrypted client connected");
    bool hello = false, subscribed = false;
    auto last_rx = Clock::now(), last_ping = last_rx, last_states = last_rx;
    std::map<std::string, Bytes> previous;
    while (!stop_) {
      if (wait_socket(socket_, POLLIN, 250, stop_)) {
        auto packet = receive(); auto values = validate_pb(packet.second); last_rx = Clock::now();
        if (!hello) {
          if (packet.first != 1 || values[2] != 1) fail("Native API Hello/version required");
          Bytes response; integer(response, 1, 1); integer(response, 2, 14);
          string(response, 3, std::string("Standalone-OTBR/") + MI_OTBR_HOST_VERSION); string(response, 4, config_.device_name);
          send_packet(2, response); hello = true; continue;
        }
        switch (packet.first) {
          case 3: send_packet(4, {}); break; // Legacy passwordless authentication.
          case 5: send_packet(6, {}); return;
          case 7: send_packet(8, {}); break;
          case 8: break;
          case 9: {
            Bytes info; string(info, 2, config_.device_name); string(info, 3, mac_);
            string(info, 4, MI_OTBR_HOST_VERSION); string(info, 6, "mi_gateway2_otbr");
            // Omit project_name/project_version: HA otherwise overrides the
            // manufacturer and appends "(ESPHome ...)" to the firmware label.
            string(info, 12, "Xiaomi"); string(info, 13, config_.friendly_name);
            if (config_.runtime_web) integer(info, 10, config_.web_port);
            // No key provisioning, Bluetooth proxy or OTA capability is advertised.
            send_packet(10, info); break;
          }
          case 11:
            for (const auto &item : config_.entities) send_packet(kind(item.first), entity_info(item.first, item.second));
            send_packet(19, {}); break;
          case 20: subscribed = true; previous.clear(); publish(previous); last_states = Clock::now(); break;
          case 28: break; // Protocol-only stage does not stream log payloads.
          case 33: case 62: {
            // Commands are accepted only for a configured entity of the exact
            // domain. A forged text-sensor key must never become a reboot.
            std::size_t at = 0; std::uint32_t key = 0; bool have_key = false, state = false;
            bool have_state = false, have_device = false;
            while (at < packet.second.size()) {
              const auto tag = read_varint(packet.second, at);
              if (tag == 13 && !have_key && at + 4 <= packet.second.size()) {
                have_key = true;
                for (unsigned n = 0; n < 4; ++n) key |= static_cast<std::uint32_t>(packet.second[at++]) << (8 * n);
              } else if (packet.first == 33 && tag == 16 && !have_state) {
                have_state = true; const auto v = read_varint(packet.second, at);
                if (v > 1) fail("invalid switch state");
                state = v != 0;
              } else if (tag == (packet.first == 33 ? 24u : 16u) && !have_device) {
                have_device = true;
                if (read_varint(packet.second, at) != 0) fail("unsupported command device");
              } else fail("invalid entity command");
            }
            if (!have_key) fail("entity command key required");
            const std::string type = packet.first == 33 ? "sys_led" : "reset";
            const auto entry = config_.entities.find(type);
            if (entry != config_.entities.end() && entity_key(entry->second.id) == key && command_) {
              if (!command_(type, state)) log("entity command rejected or backend unavailable");
              else if (subscribed && type == "sys_led") publish(previous, true);
            }
            break;
          }
          case 149: send_packet(150, {}); break;
          default: break; // Unsupported optional messages are ignored, never executed as shell commands.
        }
      }
      auto now = Clock::now();
      // LED optimistic updates and actual feedback are independent of the
      // relatively slow OTBR metrics interval. Unchanged states are suppressed.
      if (subscribed && config_.entities.count("sys_led")) publish(previous, true);
      if (!hello && now - last_rx > std::chrono::seconds(10)) fail("Native API Hello timeout");
      if (subscribed && now - last_states >= std::chrono::milliseconds(config_.update_interval_ms)) { publish(previous); last_states = now; }
      if (hello && now - last_ping >= std::chrono::seconds(30)) { send_packet(7, {}); last_ping = now; }
      if (now - last_rx > std::chrono::seconds(90)) fail("client keepalive timeout");
    }
  }
 private:
  void handshake() {
    auto client_hello = read_frame(socket_, 256, stop_);
    const char init[] = "NoiseAPIInit";
    static_assert(sizeof(init) - 1 == 12, "ESPHome Noise prologue prefix length");
    // The prefix excludes C's terminating NUL. Only the following two bytes
    // encode ClientHello length: an empty hello yields exactly 14 bytes.
    Bytes prologue(init, init + sizeof(init) - 1);
    prologue.push_back(static_cast<std::uint8_t>(client_hello.size() >> 8)); prologue.push_back(static_cast<std::uint8_t>(client_hello.size()));
    prologue.insert(prologue.end(), client_hello.begin(), client_hello.end());
    Bytes server{1}; server.insert(server.end(), config_.device_name.begin(), config_.device_name.end()); server.push_back(0);
    server.insert(server.end(), mac_.begin(), mac_.end()); server.push_back(0);
    write_frame(socket_, server, stop_);
    NoiseHandshakeState *raw = nullptr;
    noise_check(noise_handshakestate_new_by_name(&raw, "Noise_NNpsk0_25519_ChaChaPoly_SHA256", NOISE_ROLE_RESPONDER));
    Handshake state(raw);
    auto psk = decode_key(config_.api_key);
    noise_check(noise_handshakestate_set_pre_shared_key(raw, psk.data(), psk.size()));
    noise_check(noise_handshakestate_set_prologue(raw, prologue.data(), prologue.size()));
    noise_check(noise_handshakestate_start(raw));
    while (noise_handshakestate_get_action(raw) != NOISE_ACTION_SPLIT) {
      auto action = noise_handshakestate_get_action(raw);
      if (action == NOISE_ACTION_READ_MESSAGE) {
        auto frame = read_frame(socket_, 256, stop_);
        if (frame.empty() || frame[0] != 0) fail("invalid Noise handshake status");
        NoiseBuffer b; noise_buffer_init(b); noise_buffer_set_input(b, frame.data() + 1, frame.size() - 1);
        const int result = noise_handshakestate_read_message(raw, &b, nullptr);
        if (result != 0) {
          const std::string reason = result == NOISE_ERROR_MAC_FAILURE ? "Handshake MAC failure" : "Noise handshake rejected";
          Bytes rejection{1}; rejection.insert(rejection.end(), reason.begin(), reason.end());
          write_frame(socket_, rejection, stop_); fail("Noise authentication failed");
        }
      } else if (action == NOISE_ACTION_WRITE_MESSAGE) {
        Bytes frame(257); frame[0] = 0;
        NoiseBuffer b; noise_buffer_init(b); noise_buffer_set_output(b, frame.data() + 1, frame.size() - 1);
        noise_check(noise_handshakestate_write_message(raw, &b, nullptr)); frame.resize(b.size + 1); write_frame(socket_, frame, stop_);
      } else fail("unexpected Noise handshake action");
    }
    NoiseCipherState *tx = nullptr, *rx = nullptr;
    noise_check(noise_handshakestate_split(raw, &tx, &rx));
    tx_.reset(tx); rx_.reset(rx);
  }
  void send_packet(unsigned type, const Bytes &payload) {
    if (type > 65535 || payload.size() + 20 > kMaxFrame) fail("invalid outgoing API packet");
    if (config_.api_key.empty()) {
      Bytes frame{0}; varint(frame, payload.size()); varint(frame, type);
      frame.insert(frame.end(), payload.begin(), payload.end());
      transfer(socket_, frame.data(), frame.size(), true, stop_); return;
    }
    Bytes body{static_cast<std::uint8_t>(type >> 8), static_cast<std::uint8_t>(type), static_cast<std::uint8_t>(payload.size() >> 8), static_cast<std::uint8_t>(payload.size())};
    body.insert(body.end(), payload.begin(), payload.end()); const auto size = body.size(); body.resize(size + 16);
    NoiseBuffer b; noise_buffer_init(b); noise_buffer_set_inout(b, body.data(), size, body.size());
    noise_check(noise_cipherstate_encrypt(tx_.get(), &b)); body.resize(b.size); write_frame(socket_, body, stop_);
  }
  std::pair<unsigned, Bytes> receive() {
    if (config_.api_key.empty()) {
      std::uint8_t preamble;
      transfer(socket_, &preamble, 1, false, stop_);
      if (preamble != 0) fail("plaintext Native API framing required");
      auto read_varint = [&]() -> unsigned {
        unsigned value = 0;
        for (unsigned shift = 0; shift < 21; shift += 7) {
          std::uint8_t byte; transfer(socket_, &byte, 1, false, stop_);
          value |= static_cast<unsigned>(byte & 0x7f) << shift;
          if (!(byte & 0x80)) return value;
        }
        fail("Native API header varint too large");
      };
      const unsigned size = read_varint();
      if (size > kMaxFrame) fail("Native API frame too large");
      const unsigned type = read_varint();
      if (type > 65535) fail("Native API message type too large");
      Bytes payload(size); transfer(socket_, payload.data(), payload.size(), false, stop_);
      return {type, std::move(payload)};
    }
    auto body = read_frame(socket_, kMaxFrame, stop_);
    NoiseBuffer b; noise_buffer_init(b); noise_buffer_set_inout(b, body.data(), body.size(), body.size());
    noise_check(noise_cipherstate_decrypt(rx_.get(), &b));
    if (b.size < 4) fail("short API payload");
    const unsigned type = (static_cast<unsigned>(body[0]) << 8) | body[1];
    const unsigned length = (static_cast<unsigned>(body[2]) << 8) | body[3];
    if (length != b.size - 4) fail("API length mismatch");
    return {type, Bytes(body.begin() + 4, body.begin() + 4 + length)};
  }
  void publish(std::map<std::string, Bytes> &previous, bool led_only = false) {
    const auto states = provider_();
    for (const auto &item : config_.entities) {
      if (led_only && item.first != "sys_led") continue;
      if (kind(item.first) == 61) continue; // Buttons have no state message.
      const auto found = states.find(item.first);
      const auto body = entity_state(item.first, item.second, found == states.end() ? EntityState{} : found->second);
      if (!previous.count(item.first) || previous[item.first] != body) {
        unsigned response = kind(item.first) == 12 ? 21 : kind(item.first) == 16 ? 25 : kind(item.first) == 17 ? 26 : 27;
        send_packet(response, body); previous[item.first] = body;
      }
    }
  }
  int socket_; const Config &config_; const std::string &mac_; const SnapshotProvider &provider_; std::atomic<bool> &stop_;
  const EntityCommandHandler &command_;
  Cipher tx_, rx_;
};
}
std::string native_api_device_mac(const Config &config) { return device_mac(config); }
void run_native_api(const Config &config, const SnapshotProvider &provider, std::atomic<bool> &stop,
                    std::atomic<bool> *ready, const EntityCommandHandler &command) {
  if (ready) ready->store(false);
  struct ReadyReset {
    std::atomic<bool> *value;
    ~ReadyReset() { if (value) value->store(false); }
  } reset{ready};
  if (config.device_name.size() > 31) fail("Native API device name exceeds 31 bytes");
  if (!config.api_key.empty()) (void)decode_key(config.api_key);
  const auto mac = device_mac(config);
  std::map<std::uint32_t, bool> used;
  for (const auto &e : config.entities) {
    if (used[entity_key(e.second.id)]) fail("Native API entity key collision");
    used[entity_key(e.second.id)] = true;
  }
  // Discovery publishes LAN A and AAAA records. Accept both address families
  // through a dual-stack socket when supported, with an IPv4-only fallback.
  int socket_fd = socket(AF_INET6, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
  if (socket_fd >= 0) {
    int only_v6 = 0;
    if (setsockopt(socket_fd, IPPROTO_IPV6, IPV6_V6ONLY, &only_v6, sizeof(only_v6)) != 0) {
      close(socket_fd); socket_fd = -1;
    }
  }
  const bool dual_stack = socket_fd >= 0;
  if (!dual_stack) socket_fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
  Fd listener(socket_fd);
  if (listener.value < 0) fail("cannot create Native API listener");
  int reuse = 1; (void)setsockopt(listener.value, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
  sockaddr_storage address{};
  socklen_t address_size;
  if (dual_stack) {
    auto &v6 = reinterpret_cast<sockaddr_in6 &>(address);
    v6.sin6_family = AF_INET6; v6.sin6_addr = in6addr_any; v6.sin6_port = htons(config.api_port);
    address_size = sizeof(v6);
  } else {
    auto &v4 = reinterpret_cast<sockaddr_in &>(address);
    v4.sin_family = AF_INET; v4.sin_addr.s_addr = htonl(INADDR_ANY); v4.sin_port = htons(config.api_port);
    address_size = sizeof(v4);
  }
  if (bind(listener.value, reinterpret_cast<const sockaddr *>(&address), address_size) != 0 || listen(listener.value, 4) != 0) fail("cannot bind Native API port");
  if (ready) ready->store(true);
  struct Worker { std::thread thread; std::shared_ptr<std::atomic<bool>> done; };
  std::vector<Worker> workers;
  workers.reserve(kMaxClients);
  log(std::string(config.api_key.empty() ? "Plaintext" : "Noise-only") + " listener started on port " + std::to_string(config.api_port));
  try {
    while (!stop) {
      for (auto i = workers.begin(); i != workers.end();) {
        if (*i->done) { i->thread.join(); i = workers.erase(i); } else ++i;
      }
      if (!wait_socket(listener.value, POLLIN, 250, stop)) continue;
      int fd = accept(listener.value, nullptr, nullptr);
      if (fd < 0) { if (errno == EAGAIN || errno == EINTR) continue; fail("Native API accept failed"); }
      if (workers.size() >= kMaxClients) { close(fd); continue; }
      if (fcntl(fd, F_SETFD, FD_CLOEXEC) != 0 || fcntl(fd, F_SETFL, O_NONBLOCK) != 0) { close(fd); continue; }
      auto done = std::make_shared<std::atomic<bool>>(false);
      workers.push_back(Worker{std::thread([&, fd, done] {
        Fd socket(fd);
        try { Connection(fd, config, mac, provider, stop, command).run(); }
        catch (const std::exception &e) { log(e.what()); }
        *done = true;
      }), done});
    }
  } catch (...) {
    stop = true;
    for (auto &w : workers) w.thread.join();
    throw;
  }
  for (auto &w : workers) w.thread.join();
}
}
