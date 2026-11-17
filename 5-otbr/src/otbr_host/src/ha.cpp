#include "otbr_host/ha.hpp"
#include <httplib.h>
#include <cJSON.h>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>
#include <algorithm>
#include <cctype>
#include <stdexcept>
namespace otbr_host {
namespace {
using Clock = std::chrono::steady_clock;
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
const char *query =
 "{% set ns = namespace(rows=[]) %}"
 "{% for s in states.sensor | selectattr('state', 'match', '^ot1:[0-9a-f]{16}:[0-9a-f]{16}:[0-9a-f]{4}$') %}"
 "{% set d = device_id(s.entity_id) %}"
 "{% set n = device_attr(s.entity_id, 'name_by_user') or device_attr(s.entity_id, 'name') %}"
 "{% if d and n %}{% set ns.rows = ns.rows + [[s.state, n, d]] %}{% endif %}"
 "{% endfor %}{{ ns.rows | to_json }}";
bool identity_valid(const std::string &s) {
  if (s.size() != 42 || s.substr(0, 4) != "ot1:" || s[20] != ':' || s[37] != ':') return false;
  for (unsigned i = 4; i < 42; ++i) if (i != 20 && i != 37 && !((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return false;
  return std::stoul(s.substr(38), nullptr, 16) < 0xfffe;
}
std::string normalized(const char *s) {
  std::string result;
  for (; s && *s; ++s) {
    if (*s == ':' || *s == '-' || *s == ' ') continue;
    if (!std::isxdigit(static_cast<unsigned char>(*s))) return {};
    result += static_cast<char>(std::tolower(static_cast<unsigned char>(*s)));
  }
  return result.size() == 16 ? result : std::string{};
}
}
struct HaNames::Impl {
  struct Row { std::string identity, name, device; };
  Config config;
  mutable std::mutex mutex;
  std::condition_variable wake;
  bool stopping{false};
  std::shared_ptr<httplib::Client> active;
  std::thread worker;
  std::vector<Row> rows;
  Clock::time_point success{};
  std::string status{"Lookup disabled"};
  explicit Impl(const Config &c) : config(c) {
    if (!config.ha_url.empty()) { status = "Waiting for HA response"; worker = std::thread([this] { loop(); }); }
  }
  void loop() {
    unsigned retry = 30;
    for (;;) {
      bool ok = false; int http_status = 0;
      try {
        auto client = std::make_shared<httplib::Client>(config.ha_origin);
        client->set_connection_timeout(3); client->set_read_timeout(3); client->set_write_timeout(3);
        client->set_follow_location(false);
        if (config.ha_origin.rfind("https://", 0) == 0) {
          client->set_ca_cert_path(config.ha_ca_file);
          client->enable_server_certificate_verification(true);
        }
        { std::lock_guard<std::mutex> lock(mutex); if (stopping) return; active = client; }
        Json request(cJSON_CreateObject(), cJSON_Delete);
        if (!request || !cJSON_AddStringToObject(request.get(), "template", query)) throw std::bad_alloc();
        std::unique_ptr<char, decltype(&cJSON_free)> body(cJSON_PrintUnformatted(request.get()), cJSON_free);
        if (!body) throw std::bad_alloc();
        std::string response; const auto started = Clock::now();
        httplib::Request http;
        http.method = "POST"; http.path = config.ha_path; http.body = body.get();
        http.headers = {{"Authorization", "Bearer " + config.ha_token}, {"Content-Type", "application/json"}};
        http.response_handler = [&](const httplib::Response &res) { http_status = res.status; return res.status == 200; };
        http.content_receiver = [&](const char *data, std::size_t size, std::uint64_t, std::uint64_t) {
              if (response.size() + size > 65536 || Clock::now() - started > std::chrono::seconds(10)) return false;
              response.append(data, size); return true;
            };
        auto result = client->send(http);
        if (result) http_status = result->status;
        if (result && http_status == 200 && response.find('\0') == std::string::npos) {
          Json parsed(cJSON_ParseWithLengthOpts(response.c_str(), response.size() + 1, nullptr, true), cJSON_Delete);
          if (!cJSON_IsArray(parsed.get()) || cJSON_GetArraySize(parsed.get()) > 256) throw std::runtime_error("Invalid identity response");
          std::vector<Row> fresh; const cJSON *row;
          cJSON_ArrayForEach(row, parsed.get()) {
            if (!cJSON_IsArray(row) || cJSON_GetArraySize(row) != 3) throw std::runtime_error("Invalid identity row");
            const auto *id = cJSON_GetArrayItem(row, 0), *name = cJSON_GetArrayItem(row, 1), *device = cJSON_GetArrayItem(row, 2);
            if (!cJSON_IsString(id) || !cJSON_IsString(name) || !cJSON_IsString(device) || !identity_valid(id->valuestring) ||
                !name->valuestring[0] || std::strlen(name->valuestring) > 512 || !device->valuestring[0] || std::strlen(device->valuestring) > 128)
              throw std::runtime_error("Invalid identity fields");
            fresh.push_back({id->valuestring, name->valuestring, device->valuestring});
          }
          std::lock_guard<std::mutex> lock(mutex); rows = std::move(fresh); success = Clock::now(); ok = true;
        }
      } catch (...) { /* Never log HA response bodies, bearer tokens or URLs. */ }
      std::unique_lock<std::mutex> lock(mutex); active.reset();
      if (stopping) return;
      status = ok ? "HA identity names synchronized; identities=" + std::to_string(rows.size()) : "HA name refresh failed; HTTP=" + std::to_string(http_status);
      std::cerr << "[ha] " << status << '\n';
      retry = ok ? 30 : std::min(retry * 2, 300u);
      if (wake.wait_for(lock, std::chrono::seconds(retry), [&] { return stopping; })) return;
    }
  }
  std::string lookup(const std::string &pan, unsigned rloc, const std::string &ext) const {
    const Row *found = nullptr;
    for (const auto &row : rows) {
      if (row.identity.compare(4, 16, pan) || std::stoul(row.identity.substr(38), nullptr, 16) != rloc ||
          (!ext.empty() && row.identity.compare(21, 16, ext))) continue;
      if (found && (found->identity != row.identity || found->device != row.device)) return {};
      found = &row;
    }
    return found ? found->name : std::string{};
  }
};
HaNames::HaNames(const Config &c) : impl_(new Impl(c)) {}
HaNames::~HaNames() { stop(); }
void HaNames::stop() {
  std::shared_ptr<httplib::Client> active;
  { std::lock_guard<std::mutex> lock(impl_->mutex); impl_->stopping = true; active = impl_->active; }
  if (active) active->stop();
  impl_->wake.notify_all();
  if (impl_->worker.joinable()) impl_->worker.join();
}
std::string HaNames::status() const { std::lock_guard<std::mutex> lock(impl_->mutex); return impl_->status; }
WebReply HaNames::annotate(WebReply reply, const std::string &pan) const {
  if (reply.status != 200 && reply.status != 206) return reply;
  Json json(cJSON_Parse(reply.body.c_str()), cJSON_Delete); if (!json) return reply;
  auto *nodes = cJSON_GetObjectItemCaseSensitive(json.get(), "result"); if (!nodes) nodes = json.get();
  std::lock_guard<std::mutex> lock(impl_->mutex);
  const bool usable = !impl_->rows.empty() && Clock::now() - impl_->success < std::chrono::minutes(5);
  auto annotate_node = [&](cJSON *node) {
    const auto *rloc = cJSON_GetObjectItemCaseSensitive(node, "Rloc16"), *ext = cJSON_GetObjectItemCaseSensitive(node, "ExtAddress");
    if (!cJSON_IsNumber(rloc)) return;
    const auto name = usable ? impl_->lookup(pan, rloc->valueint, cJSON_IsString(ext) ? normalized(ext->valuestring) : "") : "";
    cJSON_AddStringToObject(node, "NodeName", name.c_str()); cJSON_AddStringToObject(node, "NameSource", "ha_identity");
    cJSON *child;
    cJSON_ArrayForEach(child, cJSON_GetObjectItemCaseSensitive(node, "ChildTable")) {
      const auto *id = cJSON_GetObjectItemCaseSensitive(child, "ChildId");
      const auto child_name = usable && cJSON_IsNumber(id) ? impl_->lookup(pan, (rloc->valueint & 0xfc00) | (id->valueint & 0x3ff), "") : "";
      cJSON_AddStringToObject(child, "NodeName", child_name.c_str());
    }
  };
  if (cJSON_IsArray(nodes)) { cJSON *node; cJSON_ArrayForEach(node, nodes) annotate_node(node); }
  else if (cJSON_IsObject(nodes)) annotate_node(nodes);
  std::unique_ptr<char, decltype(&cJSON_free)> text(cJSON_PrintUnformatted(json.get()), cJSON_free);
  if (text) reply.body = text.get();
  return reply;
}
}
