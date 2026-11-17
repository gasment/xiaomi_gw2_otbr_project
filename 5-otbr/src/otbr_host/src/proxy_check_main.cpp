#include "otbr_host/proxy_core.hpp"
#include <csignal>
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <cstring>
#include <thread>
#include <chrono>
namespace { std::atomic<bool> stop{false};void quit(int){stop=true;} }
int main(int argc,char **argv){
  if(argc!=2 && (argc!=3 || std::string(argv[2])!="--fixture")){std::cerr<<"Usage: thread-proxy-api-check config.yaml [--fixture]\n";return 2;}
  std::signal(SIGINT,quit);std::signal(SIGTERM,quit);
  try{
    const auto config=otbr_host::load_config(argv[1]);
    if(!config.proxy.enabled)throw std::runtime_error("Proxy YAML block required for protocol test");
    otbr_host::ProxyCore core(config.proxy);std::atomic<bool> ready{false};
    if(argc==3){
      otbr_host::ProxyStatus state;state.available=true;state.attached=true;state.ready=true;state.role="router";
      state.network_id="0011223344556677";state.partition_id="12345678";core.set_status(state);
      otbr_host::ProxyHeader header{};std::memcpy(header.data(),"TSD2",4);header[4]=2;
      header[5]=(config.proxy.udp_key.empty()?0:1)|2;header[6]=2;header[11]=2;header[12]=1;header[27]=7;header[32]=1;
      const std::string mac="02:00:00:00:00:02";
      otbr_host::ProxyBytes info{26,static_cast<std::uint8_t>(mac.size())};info.insert(info.end(),mac.begin(),mac.end());
      otbr_host::ProxyBytes body{0,10,0,static_cast<std::uint8_t>(info.size())};body.insert(body.end(),info.begin(),info.end());
      body.insert(body.end(),{0,19,0,0,62,128,5,220});body.resize(body.size()+1500,0);
      const auto parts=(body.size()+767)/768;header[31]=parts;
      for(unsigned part=0;part<parts;++part){
        header[29]=part;header[23]=part+1;const auto start=part*768;const auto size=std::min(std::size_t(768),body.size()-start);
        auto packet=otbr_host::proxy_encode(header,otbr_host::ProxyBytes(body.begin()+start,body.begin()+start+size),config.proxy.udp_key);
        otbr_host::ProxyDatagram datagram;datagram.size=packet.size();std::copy(packet.begin(),packet.end(),datagram.bytes.begin());
        bool queued=false;
        for(unsigned retry=0;retry<100 && !queued;++retry){queued=core.ingest(datagram);if(!queued)std::this_thread::sleep_for(std::chrono::milliseconds(1));}
        if(!queued)throw std::runtime_error("Fixture queue failed");
      }
      std::cerr<<"PROTOCOL_ONLY_FIXTURE: synthetic metadata and node packet; no Thread instance or UDP socket\n";
    }
    // Only TCP on the explicitly configured test port. No OT instance or UDP.
    otbr_host::run_proxy_tcp(config,core,stop,ready);return 0;
  }catch(const std::exception &e){if(stop)return 0;std::cerr<<"PROXY_TEST_ERROR: "<<e.what()<<'\n';return 1;}
}
