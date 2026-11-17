#include "otbr_host/proxy_core.hpp"
#include <chrono>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <algorithm>
using namespace otbr_host;
void require(bool value){if(!value)throw std::runtime_error("thread proxy protocol regression");}
ProxyHeader header(unsigned kind,unsigned parts=1,unsigned part=0){
  ProxyHeader h{};std::memcpy(h.data(),"TSD2",4);h[4]=kind;h[6]=2;h[11]=7;h[12]=9;h[24]=1;h[29]=part;h[31]=parts;return h;
}
ProxyDatagram datagram(const ProxyBytes &body,const ProxyHeader &h,const std::string &key=""){
  const auto bytes=proxy_encode(h,body,key);ProxyDatagram d;d.size=bytes.size();std::copy(bytes.begin(),bytes.end(),d.bytes.begin());d.peer.address[0]=0xfd;return d;
}
template<class F>void until(F f){for(unsigned n=0;n<200;++n){if(f())return;std::this_thread::sleep_for(std::chrono::milliseconds(5));}require(false);}
int main(){
  const std::string key="AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=";
  ProxyHeader out;ProxyBytes plain;
  auto h=header(2);ProxyBytes body{0,25,0,2,8,1};
  auto bytes=proxy_encode(h,body,"");require(proxy_decode(bytes,"",out,plain) && plain==body);
  h[5]=1;bytes=proxy_encode(h,body,key);require(proxy_decode(bytes,key,out,plain) && plain==body);
  bytes.back()^=1;require(!proxy_decode(bytes,key,out,plain));
  bytes=proxy_encode(h,body,key);bytes[6]^=1;require(!proxy_decode(bytes,key,out,plain)); // AAD authenticated.
  require(!proxy_decode(bytes,"",out,plain));
  h=header(8);h[5]=1;bytes=proxy_encode(h,{},key);require(proxy_decode(bytes,key,out,plain) && plain.empty());
  ProxyConfig config;config.enabled=true;config.queue_groups=1;
  ProxyCore core(config);ProxyStatus state;state.ready=true;state.attached=true;core.set_status(state);
  require(core.claim(1));require(!core.claim(2));core.release(1);require(core.claim(2));core.release(2);
  h=header(8);until([&]{return core.ingest(datagram({},h));});
  std::vector<ProxyOutgoing> outputs;
  until([&]{outputs=core.outgoing();return !outputs.empty();});
  require(outputs[0].bytes[4]==1 && outputs[0].bytes.size()==56);
  require(std::equal(h.begin()+12,h.begin()+20,outputs[0].bytes.begin()+48));
  h=header(2);const auto data=datagram(body,h);until([&]{return core.ingest(data);});
  until([&]{return core.head()!=nullptr;});const auto delivery=core.head()->delivery;
  until([&]{outputs=core.outgoing();return !outputs.empty();});require(outputs[0].bytes[4]==3);
  until([&]{return core.ingest(data);});until([&]{outputs=core.outgoing();return !outputs.empty();});
  require(core.status().queued==1 && core.head()->delivery==delivery);
  // Queue full: a different group is not acknowledged.
  h[27]=1;until([&]{return core.ingest(datagram(body,h));});std::this_thread::sleep_for(std::chrono::milliseconds(50));require(core.outgoing().empty());
  require(!core.acknowledge("wrong"));require(core.acknowledge(delivery));require(!core.head());
  // Out-of-order fragments and frozen group identity across sequence changes.
  ProxyBytes large(800,0);large[1]=25;large[2]=3;large[3]=28; // 4 + 796 bytes = 800.
  h=header(2,2,1);h[27]=2;until([&]{return core.ingest(datagram(ProxyBytes(large.begin()+768,large.end()),h));});
  h[29]=0;h[23]=2;until([&]{return core.ingest(datagram(ProxyBytes(large.begin(),large.begin()+768),h));});
  until([&]{return core.head()!=nullptr;});require(core.head()->body==large);
  core.stop();
  std::cout<<"THREAD_PROXY_PROTOCOL_PASS (in-memory only; no UDP or gateway operation)\n";
}
