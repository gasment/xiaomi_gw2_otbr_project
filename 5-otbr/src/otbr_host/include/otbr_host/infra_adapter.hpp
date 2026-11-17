#pragma once
#include <openthread/error.h>
// Call only on the OpenThread owner thread. The private InfraNetif C++ layout
// stays entirely inside the OpenThread platform library.
extern "C" {
void mi_infra_teardown();
otError mi_infra_bind(const char *name);
}
