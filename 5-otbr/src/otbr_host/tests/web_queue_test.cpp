#include "otbr_host/web.hpp"
#include <chrono>
#include <future>
#include <iostream>
#include <stdexcept>
#include <thread>
using namespace otbr_host;
using namespace std::chrono_literals;
void require(bool value, const char *message) { if (!value) throw std::runtime_error(message); }
int main() {
  WebQueue queue;
  std::future<WebReply> slow, fast, closing;
  try {
    slow = std::async(std::launch::async, [&] { return queue.request({"POST", "/ping", "{}"}); });
    fast = std::async(std::launch::async, [&] { return queue.request({"GET", "/node/state", ""}); });
    WebCompletion pending;
    auto deadline = std::chrono::steady_clock::now() + 2s;
    while (std::chrono::steady_clock::now() < deadline) {
      queue.pump_async([&](const WebRequest &r, WebCompletion done) {
        if (r.path == "/ping") pending = std::move(done);
        else done({200, "disabled"});
      });
      if (pending && fast.wait_for(0s) == std::future_status::ready) break;
      std::this_thread::sleep_for(1ms);
    }
    require(static_cast<bool>(pending), "Deferred request was not dispatched");
    require(fast.wait_for(0s) == std::future_status::ready, "Immediate query blocked behind deferred request");
    require(fast.get().body == "disabled", "Incorrect immediate reply");
    require(slow.wait_for(0s) == std::future_status::timeout, "Deferred request completed prematurely");
    pending({200, "pong"}); pending({500, "duplicate callback"});
    require(slow.get().body == "pong", "Deferred reply lost or delivered twice");
    std::cout << "PASS: deferred request leaves owner free for immediate queries; completion delivered once\n";
    closing = std::async(std::launch::async, [&] { return queue.request({"POST", "/ping", "{}"}); });
    WebCompletion late;
    deadline = std::chrono::steady_clock::now() + 2s;
    while (!late && std::chrono::steady_clock::now() < deadline) {
      queue.pump_async([&](const WebRequest &, WebCompletion done) { late = std::move(done); });
      std::this_thread::sleep_for(1ms);
    }
    require(static_cast<bool>(late), "Shutdown test was not dispatched");
    queue.close();
    require(closing.get().status == 503, "Shutdown did not release deferred HTTP worker");
    late({200, "late callback"});
    require(queue.request({"GET", "/", ""}).status == 503, "Closed queue accepted new work");
    std::cout << "WEB_ASYNC_QUEUE_PASS (no OTBR instance or radio)\n";
    return 0;
  } catch (const std::exception &e) {
    queue.close();
    for (auto *future : {&slow, &fast, &closing}) if (future->valid()) future->wait();
    std::cerr << "WEB_ASYNC_QUEUE_FAIL: " << e.what() << '\n'; return 1;
  }
}
