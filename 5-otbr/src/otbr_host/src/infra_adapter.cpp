#include "otbr_host/infra_adapter.hpp"
#include "posix/platform/infra_if.hpp"
extern "C" void mi_infra_teardown() { ot::Posix::InfraNetif::Get().TearDown(); }
extern "C" otError mi_infra_bind(const char *name) {
  int fd = ot::Posix::InfraNetif::CreateIcmp6Socket(name);
  if (fd < 0) return OT_ERROR_FAILED;
  auto &infra = ot::Posix::InfraNetif::Get();
  infra.SetInfraNetif(name, fd);
  infra.SetUp();
  return OT_ERROR_NONE;
}
