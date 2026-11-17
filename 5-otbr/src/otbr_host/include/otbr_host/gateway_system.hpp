#pragma once
#include "otbr_host/native_api.hpp"
#include <memory>
#include <iosfwd>

namespace otbr_host {
// Slow stock MIoT operations run on a dedicated worker, never on OTBR's loop.
class GatewaySystem {
 public:
  GatewaySystem(const Config &config, bool allow_control);
  ~GatewaySystem();
  GatewaySystem(const GatewaySystem &) = delete;
  GatewaySystem &operator=(const GatewaySystem &) = delete;
  Snapshot snapshot(const std::string &backbone) const;
  // Fast synchronized cache read; no Linux address enumeration or stock RPC.
  EntityState led_state() const;
  bool command(const std::string &entity, bool state);
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
std::string gateway_firmware_version(std::istream &properties);
std::string format_gateway_uptime(std::uint64_t seconds);
}
