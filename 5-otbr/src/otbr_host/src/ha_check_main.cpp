#include "otbr_host/ha.hpp"
#include <chrono>
#include <iostream>
#include <thread>
#include <exception>
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  try {
    const auto config = otbr_host::load_config(argv[1]);
    otbr_host::HaNames names(config);
    for (unsigned i = 0; i < 250; ++i) {
      if (names.status().find("synchronized") != std::string::npos) {
        auto reply = names.annotate({200, R"([{"Rloc16":4096,"ExtAddress":"8899aabbccddeeff","ChildTable":[{"ChildId":52},{"ChildId":53}]}])"}, "0011223344556677");
        std::cout << reply.body << '\n'; return 0;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    std::cerr << names.status() << '\n'; return 1;
  } catch (const std::exception &) { std::cerr << "HA_CHECK_FAILED\n"; return 1; }
}
