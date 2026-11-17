#pragma once
#include "otbr_host/config.hpp"
#include <atomic>
#include <deque>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <string>

namespace otbr_host {
struct WebRequest { std::string method, path, body; };
struct WebReply { int status{200}; std::string body; };
using WebHandler = std::function<WebReply(const WebRequest &)>;
using WebCompletion = std::function<void(WebReply)>;
using WebAsyncHandler = std::function<void(const WebRequest &, WebCompletion)>;
WebReply web_error(int status, const char *message);
// Only HTTP workers wait. The owner pumps jobs without waiting for workers.
class WebQueue {
 public:
  WebReply request(const WebRequest &request);
  void pump(const WebHandler &handler);
  void pump_async(const WebAsyncHandler &handler);
  void close();
 private:
  struct Job {
    WebRequest request;
    std::promise<WebReply> promise;
    std::atomic<bool> cancelled{false};
    std::atomic<bool> delivered{false};
  };
  std::mutex mutex_;
  std::deque<std::shared_ptr<Job>> jobs_;
  std::deque<std::shared_ptr<Job>> active_;
  static void complete(const std::shared_ptr<Job> &job, WebReply reply);
  bool closed_{false};
};
void run_web(const Config &config, const WebHandler &handler, std::atomic<bool> &stop,
             const std::string &listen_address = "0.0.0.0");
}
