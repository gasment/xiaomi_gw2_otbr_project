#include "otbr_host/restart_protocol.hpp"
#include <iostream>
#include <stdexcept>
using namespace otbr_host;
void require(bool value) { if (!value) throw std::runtime_error("EHR1 wire protocol regression"); }
int main() {
  // Match the ESP node's independent 21-byte wire contract, including byte order.
  const std::array<std::uint8_t, 8> ext{{0,1,2,3,4,5,6,7}}, nonce{{8,9,10,11,12,13,14,15}};
  const RestartPacket expected{{0x45,0x48,0x52,0x31,1,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15}};
  const auto request = restart_packet(ext, nonce);
  require(request == expected);
  auto response = expected; response[4] = 2;
  require(restart_reply_matches(request, response.data(), response.size(), 18514));
  require(!restart_reply_matches(request, request.data(), request.size(), 18514));
  require(!restart_reply_matches(request, nullptr, response.size(), 18514));
  require(!restart_reply_matches(request, response.data(), 20, 18514));
  require(!restart_reply_matches(request, response.data(), 22, 18514));
  require(!restart_reply_matches(request, response.data(), response.size(), 18515));
  for (unsigned n = 0; n < response.size(); ++n) {
    auto wrong = response; wrong[n] ^= 0x80;
    require(!restart_reply_matches(request, wrong.data(), wrong.size(), 18514));
  }
  auto previous = request; previous[13] ^= 1;
  require(!restart_reply_matches(previous, response.data(), response.size(), 18514));
  std::cout << "NODE_RESTART_PROTOCOL_PASS (no socket or reboot)\n";
}
