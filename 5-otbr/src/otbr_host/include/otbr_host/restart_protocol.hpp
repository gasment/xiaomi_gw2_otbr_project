#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
namespace otbr_host {
constexpr std::uint16_t kNodeRestartPort = 18514;
using RestartPacket = std::array<std::uint8_t, 21>;
inline RestartPacket restart_packet(const std::array<std::uint8_t, 8> &ext,
                                    const std::array<std::uint8_t, 8> &nonce) {
  RestartPacket packet{{'E', 'H', 'R', '1', 1}};
  std::copy(ext.begin(), ext.end(), packet.begin() + 5);
  std::copy(nonce.begin(), nonce.end(), packet.begin() + 13);
  return packet;
}
inline bool restart_reply_matches(const RestartPacket &request, const std::uint8_t *reply,
                                  std::size_t length, std::uint16_t source_port) {
  return reply && source_port == kNodeRestartPort && length == request.size() && reply[4] == 2 &&
      std::equal(request.begin(), request.begin() + 4, reply) &&
      std::equal(request.begin() + 5, request.end(), reply + 5);
}
}
