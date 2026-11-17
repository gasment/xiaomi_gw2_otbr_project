#pragma once
#include "otbr_host/config.hpp"
#include <openthread/instance.h>
#include <memory>
#include <string>
namespace otbr_host {
// Construct only when the runtime YAML block exists. All methods/cleanup run
// on the OpenThread owner thread, before Application::Deinit().
class ThreadProxy {
 public:
  ThreadProxy(otInstance *instance,const Config &config,bool allow_thread);
  ~ThreadProxy();
  void tick(const std::string &backbone);
  void stop();
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
