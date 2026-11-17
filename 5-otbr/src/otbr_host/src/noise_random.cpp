#include <cerrno>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <unistd.h>
// Linux kernel CSPRNG, with complete-read and EINTR handling. Failure aborts;
// never falls back to a time seed or an application PRNG.
extern "C" void noise_rand_bytes(void *output, std::size_t length) {
  int fd;
  do { fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC); } while (fd < 0 && errno == EINTR);
  if (fd < 0) { std::fputs("Noise: kernel random device unavailable\n", stderr); std::abort(); }
  auto *p = static_cast<unsigned char *>(output);
  while (length) {
    auto count = read(fd, p, length);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) { close(fd); std::fputs("Noise: kernel random read failed\n", stderr); std::abort(); }
    p += count; length -= static_cast<std::size_t>(count);
  }
  close(fd);
}
