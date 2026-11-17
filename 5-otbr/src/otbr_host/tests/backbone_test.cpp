#include "otbr_host/backbone.hpp"
#include <cstdlib>
#include <iostream>
#include <vector>
using namespace otbr_host;
void require(bool value, const char *reason) { if (!value) { std::cerr << reason << '\n'; std::exit(1); } }
int main() {
  BackboneSelector s("follow_default_route", 3000);
  std::vector<Link> links{{"wlan0", true, true, 100}, {"eth0", false, false, 10}};
  require(s.update(links, 0).empty(), "initial debounce");
  require(s.update(links, 3000) == "wlan0", "initial selection");
  links[1] = {"eth0", true, true, 10};
  require(s.update(links, 4000) == "wlan0", "new-route debounce");
  links[1].ready = false;
  require(s.update(links, 5000) == "wlan0", "transient carrier flap");
  links[1].ready = true;
  require(s.update(links, 6000) == "wlan0", "debounce restarts after flap");
  require(s.update(links, 9000) == "eth0", "stable route switch");
  links[1].ready = false;
  require(s.update(links, 10000).empty(), "withdraw dead backbone immediately");
  require(s.update(links, 13000) == "wlan0", "fallback to Wi-Fi");
  links[0].ready = false;
  require(s.update(links, 14000).empty(), "all links down");
  BackboneSelector sticky("keep_current", 0);
  links[0].ready = true;
  require(sticky.update(links, 0) == "wlan0", "sticky startup");
  links[1].ready = true;
  require(sticky.update(links, 1000) == "wlan0", "healthy sticky interface retained");
  BackboneSelector seeded("follow_default_route", 3000, "eth0");
  require(seeded.update(links, 0) == "eth0", "initial healthy interface is not withdrawn for startup debounce");
  links[1].ready = false;
  require(seeded.update(links, 1000).empty(), "failed initial interface immediately withdrawn");
  require(seeded.update(links, 4000) == "wlan0", "seeded selector recovers to stable fallback");
  std::cout << "BACKBONE_POLICY_TEST_PASS\n";
}
