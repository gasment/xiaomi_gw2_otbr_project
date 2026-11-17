#include "otbr_host/backbone.hpp"
#include "otbr_host/config.hpp"
#include <chrono>
#include <iostream>
#include <thread>
int main(int argc, char **argv) {
  if (argc != 2 && argc != 3) { std::cerr << "Usage: otbr-backbone-inspect config.yaml [--watch]\n"; return 2; }
  const bool watch = argc == 3 && std::string(argv[2]) == "--watch";
  if (argc == 3 && !watch) return 2;
  try {
    const auto c = otbr_host::load_config(argv[1]);
    otbr_host::BackboneSelector selector(c.backbone_policy, c.switch_delay_ms);
    std::string last = "<uninitialized>";
    do {
      const auto links = otbr_host::snapshot_links(c.candidates, c.thread_interface);
      const auto now = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
      const auto selected = selector.update(links, now);
      if (!watch || last != selected) {
        for (const auto &link : links) std::cout << link.name << " ready=" << link.ready << " default_route=" << link.default_route << " metric=" << link.route_metric << '\n';
        std::cout << "selected=" << (selected.empty() ? "none (offline or debounce)" : selected) << std::endl;
        last = selected;
      }
      if (watch) std::this_thread::sleep_for(std::chrono::seconds(1));
    } while (watch);
    return 0;
  } catch (const std::exception &e) { std::cerr << "ERROR: " << e.what() << '\n'; return 1; }
}
