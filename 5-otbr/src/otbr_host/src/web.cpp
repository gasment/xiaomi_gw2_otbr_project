#include "otbr_host/web.hpp"
#include "web_assets.hpp"
#include <httplib.h>
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <thread>

namespace otbr_host {
WebReply web_error(int status, const char *message) {
  // Messages are fixed internal strings, never request bodies or credentials.
  return {status, "{\"error\":" + std::to_string(status) + ",\"result\":null,\"message\":\"" + message + "\"}"};
}
WebReply WebQueue::request(const WebRequest &request) {
  auto job = std::make_shared<Job>(); job->request = request;
  auto result = job->promise.get_future();
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_) return web_error(503, "Host stopping");
    if (jobs_.size() + active_.size() >= 16) return web_error(503, "Web request queue full");
    jobs_.push_back(job);
  }
  const unsigned timeout = request.path == "/node_restart" ? 50 : request.path == "/ping" ? 20 :
      (request.path == "/topology" || request.path == "/diagnostics") ? 35 : 5;
  if (result.wait_for(std::chrono::seconds(timeout)) != std::future_status::ready) {
    job->cancelled = true;
    return web_error(504, "OpenThread request timed out");
  }
  return result.get();
}
void WebQueue::pump(const WebHandler &handler) {
  pump_async([&](const WebRequest &request, WebCompletion done) { done(handler(request)); });
}
void WebQueue::complete(const std::shared_ptr<Job> &job, WebReply reply) {
  if (!job->delivered.exchange(true)) job->promise.set_value(std::move(reply));
}
void WebQueue::pump_async(const WebAsyncHandler &handler) {
  {
    std::lock_guard<std::mutex> lock(mutex_);
    for (auto it = active_.begin(); it != active_.end();) {
      if ((*it)->cancelled) complete(*it, web_error(504, "OpenThread request timed out"));
      if ((*it)->delivered) it = active_.erase(it); else ++it;
    }
  }
  for (unsigned i = 0; i < 4; ++i) {
    std::shared_ptr<Job> job;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (jobs_.empty()) return;
      job = jobs_.front(); jobs_.pop_front();
      active_.push_back(job);
    }
    if (job->cancelled) { complete(job, web_error(504, "OpenThread request timed out")); continue; }
    try { handler(job->request, [job](WebReply reply) { complete(job, std::move(reply)); }); }
    catch (...) { complete(job, web_error(500, "OpenThread query failed")); }
  }
}
void WebQueue::close() {
  std::lock_guard<std::mutex> lock(mutex_); closed_ = true;
  for (const auto &job : jobs_) complete(job, web_error(503, "Host stopping"));
  for (const auto &job : active_) complete(job, web_error(503, "Host stopping"));
  jobs_.clear(); active_.clear();
}
namespace {
std::string base64(const std::string &value) {
  static const char table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string out;
  for (std::size_t i = 0; i < value.size(); i += 3) {
    unsigned n = static_cast<unsigned char>(value[i]) << 16;
    if (i + 1 < value.size()) n |= static_cast<unsigned char>(value[i + 1]) << 8;
    if (i + 2 < value.size()) n |= static_cast<unsigned char>(value[i + 2]);
    out += table[(n >> 18) & 63]; out += table[(n >> 12) & 63];
    out += i + 1 < value.size() ? table[(n >> 6) & 63] : '=';
    out += i + 2 < value.size() ? table[n & 63] : '=';
  }
  return out;
}
bool authorized(const std::string &supplied, const std::string &expected) {
  if (supplied.size() != expected.size()) return false;
  unsigned mismatch = 0;
  for (std::size_t i = 0; i < expected.size(); ++i) mismatch |= supplied[i] ^ expected[i];
  return mismatch == 0;
}
}
void run_web(const Config &config, const WebHandler &handler, std::atomic<bool> &stop,
             const std::string &listen_address) {
  httplib::Server server;
  server.new_task_queue = [] { return new httplib::ThreadPool(4, 16); };
  server.set_payload_max_length(1024);
  server.set_read_timeout(5, 0); server.set_write_timeout(5, 0);
  server.set_keep_alive_max_count(16); server.set_keep_alive_timeout(2);
  const auto expected = "Basic " + base64(config.web_user + ":" + config.web_password);
  auto dispatch = [&](const httplib::Request &request, httplib::Response &response) {
    response.set_header("Cache-Control", "no-store");
    response.set_header("X-Content-Type-Options", "nosniff");
    if (!authorized(request.get_header_value("Authorization"), expected)) {
      response.status = 401;
      response.set_header("WWW-Authenticate", "Basic realm=\"ThreadBR\", charset=\"UTF-8\"");
      response.set_content(web_error(401, "Authentication required").body, "application/json");
      return;
    }
    auto path = request.path;
    if (path == "/") path = "/index.html";
    if (path == "/commissioner") path = "/commissioner.html";
    if (!config.commissioner_enabled && path.find("/commissioner") == 0) {
      response.status = 404; response.set_content(web_error(404, "Commissioner disabled").body, "application/json"); return;
    }
    if (request.method == "GET" || request.method == "HEAD") {
      for (const auto &asset : web_assets) if (path == asset.path) {
        response.set_header("Content-Encoding", "gzip");
        response.set_content(reinterpret_cast<const char *>(asset.data), asset.size, asset.type);
        return;
      }
    }
    const auto reply = handler({request.method, path, request.body});
    response.status = reply.status; response.set_content(reply.body, "application/json");
  };
  server.Get("/.*", dispatch); server.Post("/.*", dispatch);
  if (!server.bind_to_port(listen_address, config.web_port)) throw std::runtime_error("Web bind failed");
  std::atomic<bool> finished{false};
  std::thread watcher([&] {
    // stop() before listen_after_bind() starts is a no-op in this pinned
    // httplib. Retry until the listener acknowledges shutdown.
    while (!finished) {
      if (stop && server.is_running()) server.stop();
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
  });
  std::cerr << "[web] Basic-auth listener started on port " << config.web_port << '\n';
  bool ok = false;
  try { if (!stop) ok = server.listen_after_bind(); }
  catch (...) { finished = true; watcher.join(); throw; }
  finished = true; watcher.join();
  if (!ok && !stop) throw std::runtime_error("Web listener failed");
}
}
