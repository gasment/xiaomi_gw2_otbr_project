#pragma once
#include "otbr_host/web.hpp"
#include <openthread/instance.h>
namespace otbr_host {
// Call exclusively on the OpenThread owner thread.
WebReply query_web(otInstance *instance, const Config &config, const WebRequest &request);
std::string commissioner_network_config(const Config &config);
}
