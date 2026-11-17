#pragma once
#include <cstddef>
#include <cstdint>
namespace otbr_host {
// Complete only packets explicitly marked CHECKSUM_PARTIAL by Linux packet
// metadata. Never repair an incoming peer's invalid transport checksum.
inline bool complete_multicast_checksum(std::uint8_t *ip, std::size_t length) {
  if (!ip || length < 40 || (ip[0] >> 4) != 6) return false;
  const std::size_t total = 40 + (static_cast<unsigned>(ip[4]) << 8) + ip[5];
  if (total > length || total == 40) return false;
  std::size_t offset = 40;
  unsigned next = ip[6];
  for (unsigned headers = 0; next == 0 || next == 43 || next == 60; ++headers) {
    if (headers >= 8 || offset + 8 > total) return false;
    if (next == 43 && ip[offset+3] != 0) return false; // Unknown final destination.
    const std::size_t size = (static_cast<unsigned>(ip[offset+1]) + 1) * 8;
    next = ip[offset]; offset += size;
    if (offset > total) return false;
  }
  const std::size_t size = total - offset;
  unsigned checksum_offset;
  if (next == 17) {
    if (size < 8 || ((static_cast<unsigned>(ip[offset+4]) << 8) | ip[offset+5]) != size) return false;
    checksum_offset = 6;
  } else if (next == 58) {
    if (size < 4) return false;
    checksum_offset = 2;
  } else return false; // Fragments/unsupported partial checksums are not injected.
  ip[offset+checksum_offset] = ip[offset+checksum_offset+1] = 0;
  std::uint32_t sum = static_cast<std::uint32_t>(size) + next;
  for (unsigned i = 8; i < 40; i += 2) sum += (static_cast<unsigned>(ip[i]) << 8) | ip[i+1];
  for (std::size_t i = offset; i + 1 < total; i += 2) sum += (static_cast<unsigned>(ip[i]) << 8) | ip[i+1];
  if (size & 1) sum += static_cast<unsigned>(ip[total-1]) << 8;
  while (sum >> 16) sum = (sum & 0xffff) + (sum >> 16);
  auto checksum = static_cast<std::uint16_t>(~sum);
  if (checksum == 0 && next == 17) checksum = 0xffff;
  ip[offset+checksum_offset] = static_cast<std::uint8_t>(checksum >> 8);
  ip[offset+checksum_offset+1] = static_cast<std::uint8_t>(checksum);
  return true;
}
}
