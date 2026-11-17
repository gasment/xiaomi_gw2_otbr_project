#include "otbr_host/config.hpp"
#include <iostream>
#include <exception>
int main(int argc, char **argv) {
  if (argc != 2) { std::cerr << "Usage: otbr-config-check config.yaml\n"; return 2; }
  try {
    const auto c = otbr_host::load_config(argv[1]);
    return otbr_host::report_config(std::cout, c);
  } catch (const std::exception &e) {
    std::cerr << "CONFIG_ERROR: " << e.what() << '\n'; return 1;
  }
}
