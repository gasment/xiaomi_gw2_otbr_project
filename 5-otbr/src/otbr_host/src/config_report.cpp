#include "otbr_host/config.hpp"
#include <ostream>
namespace otbr_host {
int report_config(std::ostream &out, const Config &c) {
  out << "CONFIG_CHECK_ONLY\nCONFIG_SCHEMA_VALID\n"
      << "device=" << c.device_name << '\n'
      << "host.version=" << MI_OTBR_HOST_VERSION << '\n'
      << "native_api.port=" << c.api_port << " encryption=" << (c.api_key.empty() ? "plaintext" : "Noise") << '\n'
      << "web.port=" << c.web_port << " authentication=Basic\n"
      << "backbone=auto policy=" << c.backbone_policy << " switch_delay_ms=" << c.switch_delay_ms << '\n'
      << "backbone.candidates=";
  if (c.candidates.empty()) out << "discover";
  for (const auto &name : c.candidates) out << name << ' ';
  out << "\nrcp.device=" << c.uart_device << " baud_rate=" << c.baud_rate << " flow_control=" << c.flow_control
      << "\noutput_power.requested=";
  if (c.output_power) out << *c.output_power << " dBm (actual value requires RCP readback)";
  else out << "unchanged (RCP default)";
  out << "\nthread.interface=" << c.thread_interface << " state_directory=" << c.state_directory
      << "\ndataset.source=YAML force_dataset=" << (c.force_dataset ? "true" : "false")
      << " omr=" << (c.omr_prefix.empty() ? "automatic" : "custom")
      << "\ncommissioner.enabled=" << (c.commissioner_enabled ? "true" : "false")
      << "\nentities=" << c.entities.size() << " update_interval_ms=" << c.update_interval_ms << '\n';
  for (const auto &entry : c.entities)
    out << "entity=" << entry.first << " id=" << entry.second.id << '\n';
  out << "thread_proxy_api=" << (c.proxy.enabled ? "enabled" : "disabled") << '\n';
  if(c.proxy.enabled)out << "thread_proxy_api.tcp="<<c.proxy.port<<" encryption="<<(c.proxy.api_key.empty()?"plaintext":"Noise")
    <<" max_connections="<<c.proxy.max_connections<<" status_interval_ms="<<c.proxy.status_interval_ms
    <<"\nthread_proxy_api.udp=6064 encryption="<<(c.proxy.udp_key.empty()?"plaintext":"AES-256-GCM")
    <<" queue_groups="<<c.proxy.queue_groups<<" queue_bytes="<<c.proxy.queue_bytes<<'\n';
  for (const auto &warning : c.warnings) out << "WARNING: " << warning << '\n';
  out << "ha_name_mapping=" << (!c.ha_url.empty() ? "enabled (background HTTP/HTTPS, identity cache)" : "not_configured") << '\n'
      << "CONFIG_FIELDS_READY (does not prove radio attachment or routing).\n"
      << "No UART, TUN, listener, sysctl, Dataset write or Thread operation performed.\n";
  return 0;
}
}
