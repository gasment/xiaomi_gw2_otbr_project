#include "otbr_host/proxy_core.hpp"
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <deque>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <thread>

namespace otbr_host {
namespace {
using Clock = std::chrono::steady_clock;
std::uint64_t now_ms() { return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count(); }
unsigned u16(const std::uint8_t *p) { return (unsigned(p[0]) << 8) | p[1]; }
void put32(std::uint8_t *p, std::uint32_t v) { for (int i = 3; i >= 0; --i) { p[i] = v; v >>= 8; } }
bool same(const ProxyHeader &a, const ProxyHeader &b) {
  return a[4] == b[4] && a[5] == b[5] && !std::memcmp(a.data()+6,b.data()+6,14) &&
         !std::memcmp(a.data()+24,b.data()+24,4) && !std::memcmp(a.data()+32,b.data()+32,16);
}
std::uint64_t digest(const ProxyBytes &body) {
  std::uint64_t h = 14695981039346656037ull;
  for (auto byte : body) h = (h ^ byte) * 1099511628211ull;
  return h;
}
bool key_bytes(const std::string &text, std::array<std::uint8_t, 32> &key) {
  if (text.size() != 44 || text.back() != '=') return false;
  std::array<unsigned char, 33> decoded{};
  if (EVP_DecodeBlock(decoded.data(), reinterpret_cast<const unsigned char *>(text.data()), text.size()) != 33) return false;
  std::copy_n(decoded.begin(), 32, key.begin()); return true;
}
}
std::string proxy_hex(const std::uint8_t *p, std::size_t size) {
  static const char hex[] = "0123456789abcdef"; std::string out; out.reserve(size*2);
  for (std::size_t i=0;i<size;++i) { out += hex[p[i]>>4]; out += hex[p[i]&15]; } return out;
}
ProxyBytes proxy_encode(const ProxyHeader &header, const ProxyBytes &body, const std::string &key_text) {
  if (body.size() > 768 || std::memcmp(header.data(),"TSD2",4) || bool(header[5]&1) != !key_text.empty()) return {};
  ProxyBytes out(header.begin(),header.end());
  if (key_text.empty()) { out.insert(out.end(),body.begin(),body.end()); return out; }
  std::array<std::uint8_t,32> key{}; if (!key_bytes(key_text,key)) return {};
  std::unique_ptr<EVP_CIPHER_CTX,decltype(&EVP_CIPHER_CTX_free)> ctx(EVP_CIPHER_CTX_new(),EVP_CIPHER_CTX_free);
  int n=0,total=0; out.resize(48+body.size()+16);const std::uint8_t empty=0;
  if (!ctx || EVP_EncryptInit_ex(ctx.get(),EVP_aes_256_gcm(),nullptr,nullptr,nullptr)!=1 ||
      EVP_EncryptInit_ex(ctx.get(),nullptr,nullptr,key.data(),header.data()+12)!=1 ||
      EVP_EncryptUpdate(ctx.get(),nullptr,&n,header.data(),48)!=1 ||
      EVP_EncryptUpdate(ctx.get(),out.data()+48,&n,body.empty()?&empty:body.data(),body.size())!=1) return {};
  total=n;
  if (EVP_EncryptFinal_ex(ctx.get(),out.data()+48+total,&n)!=1 || std::size_t(total+n)!=body.size() ||
      EVP_CIPHER_CTX_ctrl(ctx.get(),EVP_CTRL_GCM_GET_TAG,16,out.data()+48+body.size())!=1) return {};
  return out;
}
bool proxy_decode(const ProxyBytes &packet, const std::string &key_text, ProxyHeader &header, ProxyBytes &body) {
  if (packet.size()<48 || packet.size()>832 || std::memcmp(packet.data(),"TSD2",4) || (packet[5]&~3) ||
      bool(packet[5]&1)!=!key_text.empty()) return false;
  std::copy_n(packet.begin(),48,header.begin());
  const auto parts=u16(header.data()+30), part=u16(header.data()+28);
  if (!parts || parts>43 || part>=parts) return false;
  if (key_text.empty()) body.assign(packet.begin()+48,packet.end());
  else {
    if (packet.size()<64) return false;
    std::array<std::uint8_t,32> key{}; if (!key_bytes(key_text,key)) return false;
    const auto size=packet.size()-64;
    // Keep a byte even for empty authenticated messages, for EVP output pointers.
    body.resize(size+1);
    std::unique_ptr<EVP_CIPHER_CTX,decltype(&EVP_CIPHER_CTX_free)> ctx(EVP_CIPHER_CTX_new(),EVP_CIPHER_CTX_free);
    int n=0,total=0;
    if (!ctx || EVP_DecryptInit_ex(ctx.get(),EVP_aes_256_gcm(),nullptr,nullptr,nullptr)!=1 ||
        EVP_DecryptInit_ex(ctx.get(),nullptr,nullptr,key.data(),header.data()+12)!=1 ||
        EVP_DecryptUpdate(ctx.get(),nullptr,&n,header.data(),48)!=1 ||
        EVP_DecryptUpdate(ctx.get(),body.data(),&n,packet.data()+48,size)!=1) return false;
    total=n;
    if (EVP_CIPHER_CTX_ctrl(ctx.get(),EVP_CTRL_GCM_SET_TAG,16,const_cast<std::uint8_t *>(packet.data()+48+size))!=1 ||
        EVP_DecryptFinal_ex(ctx.get(),body.data()+total,&n)!=1 || std::size_t(total+n)!=size) { body.clear(); return false; }
    body.resize(size);
  }
  return body.size()<=768 && (part+1==parts || body.size()==768) && std::size_t(part)*768+body.size()<=32768;
}
struct ProxyCore::Impl {
  ProxyConfig config;
  std::function<void()> wakeup;
  mutable std::mutex mutex;
  std::mutex incoming_mutex;
  std::condition_variable cv;
  std::array<ProxyDatagram,8> incoming{};
  std::size_t rx_head{0},rx_size{0};
  std::deque<std::array<std::uint8_t,6>> requests;
  std::atomic<bool> stopping{false};
  std::thread worker;
  ProxyStatus state;
  std::deque<std::shared_ptr<ProxyGroup>> queue;
  std::deque<ProxyOutgoing> outputs;
  std::uint64_t consumer{0};
  std::size_t bytes{0};
  std::array<std::uint8_t,8> boot{};
  std::uint32_t sequence{0},delivery{0};
  struct Assembly { ProxyHeader h{}; ProxyPeer peer; ProxyBytes body; std::uint64_t mask{0},touched{0}; unsigned final_size{0}; };
  struct Receipt { ProxyHeader h{}; std::uint64_t hash{0},at{0}; };
  struct Node { std::array<std::uint8_t,6> mac{}; std::array<std::uint8_t,16> schema{}; ProxyPeer peer; };
  std::vector<Assembly> assemblies;
  std::deque<Receipt> receipts;
  std::vector<Node> nodes;
  Impl(const ProxyConfig &c,std::function<void()> fn) : config(c),wakeup(std::move(fn)) {
    if (RAND_bytes(boot.data(),boot.size())!=1) throw std::runtime_error("Proxy random source unavailable");
    worker=std::thread([this] { run(); });
  }
  ~Impl() { stop(); }
  void stop() { stopping=true;cv.notify_all();if(worker.joinable()) worker.join(); }
  void send(unsigned kind,const ProxyHeader &original,const ProxyBytes &body,const ProxyPeer &peer) {
    ProxyHeader h{};std::memcpy(h.data(),"TSD2",4);h[4]=kind;h[5]=config.udp_key.empty()?0:1;
    std::copy_n(original.begin()+6,6,h.begin()+6);
    if (++sequence==0 && RAND_bytes(boot.data(),boot.size())!=1) { stopping=true;return; }
    std::copy(boot.begin(),boot.end(),h.begin()+12);put32(h.data()+20,sequence);
    std::copy_n(original.begin()+24,4,h.begin()+24);h[31]=1;
    std::copy_n(original.begin()+32,16,h.begin()+32);
    auto packet=proxy_encode(h,body,config.udp_key);if(packet.empty()) return;
    { std::lock_guard<std::mutex> lock(mutex);if(outputs.size()>=32) return;outputs.push_back({peer,std::move(packet)}); }
    if(wakeup) wakeup();
  }
  bool accept(const ProxyHeader &h,const ProxyBytes &body) {
    if(h[4]==2) for(std::size_t offset=0;offset<body.size();) {
      if(body.size()-offset<4 || !u16(body.data()+offset) || u16(body.data()+offset+2)>body.size()-offset-4) return false;
      offset+=4+u16(body.data()+offset+2);
    }
    const auto hash=digest(body);
    for(const auto &receipt:receipts) if(same(receipt.h,h)) return hash==receipt.hash;
    {
      std::lock_guard<std::mutex> lock(mutex);
      for(const auto &p:queue) if(same(p->header,h)) return p->body==body;
      if(queue.size()>=config.queue_groups || body.size()>config.queue_bytes-bytes) return false;
      auto group=std::make_shared<ProxyGroup>();group->header=h;group->body=body;
      if(++delivery==0) { stopping=true;return false; } // Never reuse a delivery token.
      std::uint8_t counter[4];put32(counter,delivery);
      group->delivery=proxy_hex(boot.data(),boot.size())+"-"+proxy_hex(counter,4);
      queue.push_back(group);bytes+=body.size();
    }
    receipts.push_back({h,hash,now_ms()});if(receipts.size()>64) receipts.pop_front();
    if(h[4]==2 && (h[5]&2)) for(auto &n:nodes) if(!std::memcmp(n.mac.data(),h.data()+6,6)) std::copy_n(h.begin()+32,16,n.schema.begin());
    return true;
  }
  void process(const ProxyDatagram &datagram) {
    { std::lock_guard<std::mutex> lock(mutex);if(!state.ready) return; }
    ProxyHeader h;ProxyBytes body;
    if(datagram.size>datagram.bytes.size() || !proxy_decode(ProxyBytes(datagram.bytes.begin(),datagram.bytes.begin()+datagram.size),config.udp_key,h,body)) return;
    if(h[4]!=2 && h[4]!=6 && h[4]!=7 && h[4]!=8) return;
    const auto parts=u16(h.data()+30),part=u16(h.data()+28);
    if(h[4]==8 && (parts!=1 || !body.empty() || (h[5]&2))) return;
    if((h[4]==6 || h[4]==7) && (parts!=1 || body.size()!=(h[4]==6?4u:0u))) return;
    auto node=std::find_if(nodes.begin(),nodes.end(),[&](const Node &n){return !std::memcmp(n.mac.data(),h.data()+6,6);});
    if(node==nodes.end()) {
      if(nodes.size()>=64) return;
      nodes.push_back({});node=nodes.end()-1;std::copy_n(h.begin()+6,6,node->mac.begin());
    }
    node->peer=datagram.peer;
    if(h[4]==2 && !(h[5]&2) && std::memcmp(node->schema.data(),h.data()+32,16)) node->schema.fill(0);
    { std::lock_guard<std::mutex> lock(mutex);state.nodes=nodes.size(); }
    if(h[4]==8) {
      { std::lock_guard<std::mutex> lock(mutex);if(queue.size()>=config.queue_groups || bytes>=config.queue_bytes) return; }
      std::copy(node->schema.begin(),node->schema.end(),h.begin()+32);
      send(1,h,ProxyBytes(h.begin()+12,h.begin()+20),datagram.peer);return;
    }
    if(h[4]!=2) { accept(h,body);return; }
    if(parts==1) { if(accept(h,body)) send(3,h,ProxyBytes(h.begin()+12,h.begin()+20),datagram.peer);return; }
    auto it=std::find_if(assemblies.begin(),assemblies.end(),[&](const Assembly &a){return same(a.h,h) && a.peer==datagram.peer;});
    if(it==assemblies.end()) {
      if(assemblies.size()>=4) return;
      Assembly a;a.h=h;a.peer=datagram.peer;a.body.resize(std::min(std::size_t(parts)*768,std::size_t(32768)));
      assemblies.push_back(std::move(a));it=assemblies.end()-1;
    }
    if(u16(it->h.data()+30)!=parts) return;
    const auto bit=std::uint64_t{1}<<part;
    if(it->mask&bit) {
      if((part+1==parts && it->final_size!=body.size()) || !std::equal(body.begin(),body.end(),it->body.begin()+part*768)) return;
    } else {
      std::copy(body.begin(),body.end(),it->body.begin()+part*768);it->mask|=bit;
      if(part+1==parts) it->final_size=body.size();
    }
    it->touched=now_ms();
    if(it->mask!=(std::uint64_t{1}<<parts)-1) return;
    it->body.resize((parts-1)*768+it->final_size);
    if(accept(it->h,it->body)) send(3,h,ProxyBytes(h.begin()+12,h.begin()+20),datagram.peer);
    assemblies.erase(it);
  }
  void run() {
    try {
      while(!stopping) {
        ProxyDatagram datagram;bool have=false;std::array<std::uint8_t,6> request{};bool have_request=false;
        {
          std::unique_lock<std::mutex> lock(incoming_mutex);
          cv.wait_for(lock,std::chrono::milliseconds(10),[&]{return stopping || rx_size || !requests.empty();});
          if(stopping) break;
          if(rx_size) { datagram=incoming[rx_head];rx_head=(rx_head+1)%incoming.size();--rx_size;have=true; }
          if(!requests.empty()) { request=requests.front();requests.pop_front();have_request=true; }
        }
        if(have) process(datagram);
        if(have_request) for(const auto &node:nodes) if(node.mac==request) {
          ProxyHeader h{};std::copy(request.begin(),request.end(),h.begin()+6);send(4,h,{},node.peer);break;
        }
        const auto now=now_ms();
        assemblies.erase(std::remove_if(assemblies.begin(),assemblies.end(),[&](const Assembly &a){return now-a.touched>10000;}),assemblies.end());
        while(!receipts.empty() && now-receipts.front().at>120000) receipts.pop_front();
      }
    } catch(const std::exception &) {
      std::cerr<<"[thread-proxy] UDP worker failed; data plane disabled\n";stopping=true;
    }
  }
};
ProxyCore::ProxyCore(const ProxyConfig &c,std::function<void()> wakeup):impl_(std::make_unique<Impl>(c,std::move(wakeup))){}
ProxyCore::~ProxyCore()=default;
void ProxyCore::stop(){impl_->stop();}
bool ProxyCore::ingest(const ProxyDatagram &packet){
  if(impl_->stopping || packet.size<48 || packet.size>832) return false;
  std::unique_lock<std::mutex> lock(impl_->incoming_mutex,std::try_to_lock);
  if(!lock || impl_->rx_size==impl_->incoming.size()) return false;
  impl_->incoming[(impl_->rx_head+impl_->rx_size)%impl_->incoming.size()]=packet;++impl_->rx_size;impl_->cv.notify_one();return true;
}
bool ProxyCore::request_schema(const std::string &mac){
  if(mac.size()!=12) return false;std::array<std::uint8_t,6> bytes{};
  for(unsigned i=0;i<12;++i){char c=mac[i];int v=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;if(v<0)return false;bytes[i/2]|=v<<(i%2?0:4);}
  std::lock_guard<std::mutex> lock(impl_->incoming_mutex);if(impl_->requests.size()>=8)return false;
  impl_->requests.push_back(bytes);impl_->cv.notify_one();return true;
}
std::vector<ProxyOutgoing> ProxyCore::outgoing(){
  std::lock_guard<std::mutex> lock(impl_->mutex);std::vector<ProxyOutgoing> out;
  while(!impl_->outputs.empty() && out.size()<8){out.push_back(std::move(impl_->outputs.front()));impl_->outputs.pop_front();}return out;
}
std::shared_ptr<const ProxyGroup> ProxyCore::head()const{std::lock_guard<std::mutex> lock(impl_->mutex);return impl_->queue.empty()?nullptr:impl_->queue.front();}
bool ProxyCore::acknowledge(const std::string &delivery){
  std::lock_guard<std::mutex> lock(impl_->mutex);if(impl_->queue.empty() || impl_->queue.front()->delivery!=delivery)return false;
  impl_->bytes-=impl_->queue.front()->body.size();impl_->queue.pop_front();return true;
}
bool ProxyCore::claim(std::uint64_t client){std::lock_guard<std::mutex> lock(impl_->mutex);if(impl_->consumer && impl_->consumer!=client)return false;impl_->consumer=client;return true;}
void ProxyCore::release(std::uint64_t client){std::lock_guard<std::mutex> lock(impl_->mutex);if(impl_->consumer==client)impl_->consumer=0;}
void ProxyCore::set_status(ProxyStatus status){std::lock_guard<std::mutex> lock(impl_->mutex);status.nodes=impl_->state.nodes;impl_->state=std::move(status);}
ProxyStatus ProxyCore::status()const{std::lock_guard<std::mutex> lock(impl_->mutex);auto s=impl_->state;s.queued=impl_->queue.size();if(impl_->stopping)s.ready=false;return s;}
}
