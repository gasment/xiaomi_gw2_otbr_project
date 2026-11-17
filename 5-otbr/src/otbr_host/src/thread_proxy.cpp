#include "otbr_host/thread_proxy.hpp"
#include "otbr_host/proxy_core.hpp"
#include "otbr_host/discovery.hpp"
#include "common/mainloop.hpp"
#include <openthread/thread.h>
#include <openthread/udp.h>
#include <openthread/message.h>
#include <sys/eventfd.h>
#include <unistd.h>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <thread>

namespace otbr_host {
namespace {
using Clock=std::chrono::steady_clock;
const char *role_name(otDeviceRole r){
  switch(r){case OT_DEVICE_ROLE_CHILD:return "child";case OT_DEVICE_ROLE_ROUTER:return "router";
    case OT_DEVICE_ROLE_LEADER:return "leader";case OT_DEVICE_ROLE_DETACHED:return "detached";default:return "disabled";}
}
struct WakeFd {
  int fd{eventfd(0,EFD_NONBLOCK|EFD_CLOEXEC)};
  WakeFd(){if(fd<0)throw std::runtime_error("Proxy eventfd unavailable");}
  ~WakeFd(){close(fd);}
};
}
struct ThreadProxy::Impl : otbr::MainloopProcessor {
  otInstance *instance;
  const bool allow_thread;
  WakeFd wake;
  ProxyCore core;
  ApiDiscovery discovery;
  std::atomic<bool> stopping{false},tcp_ready{false};
  std::thread tcp;
  otUdpSocket socket{};
  bool opened{false},closed{false};
  Clock::time_point sample_at{},bind_at{};
  struct Pending { ProxyOutgoing packet;Clock::time_point started,attempted; };
  std::vector<Pending> pending;
  Impl(otInstance *i,const Config &config,bool allow):instance(i),allow_thread(allow),
      core(config.proxy,[this]{std::uint64_t one=1;const auto ignored=write(wake.fd,&one,sizeof(one));(void)ignored;}),
      discovery(i,config,true) {
    pending.reserve(32);
    tcp=std::thread([this,&config]{
      while(!stopping){
        try{run_proxy_tcp(config,core,stopping,tcp_ready);}
        catch(const std::exception &){std::cerr<<"[thread-proxy] TCP listener unavailable; retrying\n";}
        for(unsigned n=0;n<50 && !stopping;++n)std::this_thread::sleep_for(std::chrono::milliseconds(100));
      }
    });
    std::cerr<<"[thread-proxy] THREAD_PROXY_RUNTIME_ENABLED tcp="<<config.proxy.port<<" udp=6064 protocol=tsd2-v1\n";
  }
  ~Impl(){stop();}
  static void receive(void *context,otMessage *message,const otMessageInfo *peer){
    auto *self=static_cast<Impl *>(context);if(self->closed)return;
    const auto size=otMessageGetLength(message)-otMessageGetOffset(message);
    if(size<48 || size>832)return;
    ProxyDatagram packet;packet.size=size;packet.peer.port=peer->mPeerPort;
    std::memcpy(packet.peer.address.data(),peer->mPeerAddr.mFields.m8,16);
    std::memcpy(packet.peer.local.data(),peer->mSockAddr.mFields.m8,16);
    if(otMessageRead(message,otMessageGetOffset(message),packet.bytes.data(),size)==size)self->core.ingest(packet);
  }
  void Update(otbr::MainloopContext &context) override {
    if(closed)return;
    context.AddFdToReadSet(wake.fd);
    if(!pending.empty() && (context.mTimeout.tv_sec>0 || context.mTimeout.tv_usec>10000)){
      context.mTimeout.tv_sec=0;context.mTimeout.tv_usec=10000;
    }
  }
  void Process(const otbr::MainloopContext &context) override {
    if(closed)return;
    if(FD_ISSET(wake.fd,&context.mReadFdSet)){std::uint64_t n;const auto ignored=read(wake.fd,&n,sizeof(n));(void)ignored;}
    drain();
  }
  bool send(const ProxyOutgoing &packet){
    if(!opened || !allow_thread || otThreadGetDeviceRole(instance)<OT_DEVICE_ROLE_CHILD)return false;
    otMessageInfo info{};info.mPeerPort=packet.peer.port;info.mSockPort=6064;
    std::memcpy(info.mPeerAddr.mFields.m8,packet.peer.address.data(),16);
    if(packet.bytes[4]==3)std::memcpy(info.mSockAddr.mFields.m8,packet.peer.local.data(),16);
    else info.mSockAddr=*otThreadGetMeshLocalEid(instance);
    auto *message=otUdpNewMessage(instance,nullptr);if(!message)return false;
    if(otMessageAppend(message,packet.bytes.data(),packet.bytes.size())==OT_ERROR_NONE &&
       otUdpSend(instance,&socket,message,&info)==OT_ERROR_NONE)return true;
    otMessageFree(message);return false;
  }
  void drain(){
    const auto now=Clock::now();
    // Bound each turn even during an input flood; radio processing keeps priority.
    for(unsigned work=0;work<4;++work){
      auto outputs=core.outgoing();if(outputs.empty())break;
      for(auto &p:outputs)if(pending.size()<32)pending.push_back({std::move(p),now,{}});
    }
    unsigned work=0;
    for(auto it=pending.begin();it!=pending.end();){
      if(now-it->started>=std::chrono::milliseconds(400)){it=pending.erase(it);continue;}
      if(work>=8 || (it->attempted!=Clock::time_point{} && now-it->attempted<std::chrono::milliseconds(10))){++it;continue;}
      ++work;it->attempted=now;
      if(send(it->packet))it=pending.erase(it);else ++it;
    }
  }
  void tick(const std::string &backbone){
    if(closed)return;
    const auto now=Clock::now();
    if(now>=sample_at){
      ProxyStatus state;state.available=true;const auto role=otThreadGetDeviceRole(instance);
      state.role=role_name(role);state.attached=role>=OT_DEVICE_ROLE_CHILD;
      state.network_id=proxy_hex(otThreadGetExtendedPanId(instance)->m8,8);
      const auto partition=otThreadGetPartitionId(instance);
      std::uint8_t bytes[4]={static_cast<std::uint8_t>(partition>>24),static_cast<std::uint8_t>(partition>>16),static_cast<std::uint8_t>(partition>>8),static_cast<std::uint8_t>(partition)};
      state.partition_id=proxy_hex(bytes,4);
      if(allow_thread && state.attached && !opened && now>=bind_at){
        bind_at=now+std::chrono::seconds(5);otSockAddr local{};local.mPort=6064;
        if(otUdpOpen(instance,&socket,receive,this)==OT_ERROR_NONE){
          if(otUdpBind(instance,&socket,&local,OT_NETIF_THREAD_INTERNAL)==OT_ERROR_NONE)opened=true;
          else otUdpClose(instance,&socket);
        }
        if(!opened)std::cerr<<"[thread-proxy] Thread UDP bind unavailable; retrying\n";
      }
      if(opened && !state.attached){otUdpClose(instance,&socket);opened=false;pending.clear();}
      state.ready=opened && state.attached && allow_thread;core.set_status(std::move(state));
      sample_at=now+std::chrono::seconds(1);
    }
    discovery.update(backbone,tcp_ready);drain();
  }
  void stop(){
    if(closed)return;closed=true;stopping=true;
    if(tcp.joinable())tcp.join();
    core.stop();pending.clear();
    if(opened){otUdpClose(instance,&socket);opened=false;}
    discovery.stop();
  }
};
ThreadProxy::ThreadProxy(otInstance *i,const Config &c,bool allow):impl_(std::make_unique<Impl>(i,c,allow)){}
ThreadProxy::~ThreadProxy()=default;
void ThreadProxy::tick(const std::string &backbone){impl_->tick(backbone);}
void ThreadProxy::stop(){impl_->stop();}
}
