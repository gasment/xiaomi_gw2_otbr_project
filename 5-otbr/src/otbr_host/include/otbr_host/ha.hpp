#pragma once
#include "otbr_host/config.hpp"
#include "otbr_host/web.hpp"
#include <memory>
namespace otbr_host {
class HaNames {
 public:
  explicit HaNames(const Config &config);
  ~HaNames();
  HaNames(const HaNames &) = delete;
  HaNames &operator=(const HaNames &) = delete;
  void stop();
  std::string status() const;
  WebReply annotate(WebReply reply, const std::string &extended_pan) const;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
