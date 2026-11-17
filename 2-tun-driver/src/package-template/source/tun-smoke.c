#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/if_tun.h>
#include <net/if.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static int tunfd=-1, rawfd=-1, ctlfd=-1;
static void cleanup(void) {
    if (rawfd>=0) close(rawfd);
    if (ctlfd>=0) close(ctlfd);
    if (tunfd>=0) close(tunfd);
}
static void die(const char *what) { perror(what); exit(1); }
static int64_t now_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) die("clock_gettime");
    return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
static uint32_t sum_bytes(uint32_t sum,const unsigned char *p,size_t n) {
    while (n>=2) { sum+=((uint32_t)p[0]<<8)|p[1]; p+=2; n-=2; }
    if (n) sum+=(uint32_t)p[0]<<8;
    return sum;
}
static uint16_t icmp6_checksum(const unsigned char *ip,size_t n) {
    size_t payload=n-40;
    uint32_t s=sum_bytes(0,ip+8,32);
    s+=(uint32_t)(payload>>16)+(uint32_t)(payload&65535)+58;
    s=sum_bytes(s,ip+40,payload);
    while(s>>16) s=(s&65535)+(s>>16);
    return (uint16_t)~s;
}
int main(void) {
    const char *name="mgtun0";
    const char *local="fd6d:6747:3274:756e::1";
    const char *remote="fd6d:6747:3274:756e::2";
    const char marker[]="mi-gateway2-tun-smoke";
    struct in6_addr src,dst;
    struct ifreq ifr;
    struct { struct in6_addr addr; uint32_t prefixlen; int ifindex; } in6req;
    struct sockaddr_in6 from,to;
    unsigned char request[8+sizeof(marker)],buf[4096];
    int received_tun=0, wrote_tun=0, success=0;
    setvbuf(stdout,NULL,_IONBF,0);
    atexit(cleanup);
    if (if_nametoindex(name)) { fprintf(stderr,"Interface mgtun0 already exists; refusing to attach.\n"); return 1; }
    if(inet_pton(AF_INET6,local,&src)!=1 || inet_pton(AF_INET6,remote,&dst)!=1) return 1;
    tunfd=open("/dev/net/tun",O_RDWR|O_NONBLOCK);
    if(tunfd<0) die("open /dev/net/tun");
    memset(&ifr,0,sizeof(ifr));
    strncpy(ifr.ifr_name,name,IFNAMSIZ-1);
    ifr.ifr_flags=IFF_TUN|IFF_NO_PI;
    if(ioctl(tunfd,TUNSETIFF,&ifr)) die("TUNSETIFF");
    printf("PASS: TUNSETIFF created %s\n",name);
    ctlfd=socket(AF_INET6,SOCK_DGRAM,0);
    if(ctlfd<0) die("IPv6 control socket");
    if(ioctl(ctlfd,SIOCGIFFLAGS,&ifr)) die("SIOCGIFFLAGS");
    ifr.ifr_flags|=IFF_UP;
    if(ioctl(ctlfd,SIOCSIFFLAGS,&ifr)) die("SIOCSIFFLAGS");
    memset(&in6req,0,sizeof(in6req));
    in6req.addr=src; in6req.prefixlen=64; in6req.ifindex=(int)if_nametoindex(name);
    if(ioctl(ctlfd,SIOCSIFADDR,&in6req)) die("SIOCSIFADDR IPv6");
    printf("PASS: assigned %s/64 to temporary interface\n",local);
    /* Allow address configuration/DAD to settle; no persistent state is set. */
    sleep(2);
    rawfd=socket(AF_INET6,SOCK_RAW,IPPROTO_ICMPV6);
    if(rawfd<0) die("ICMPv6 raw socket");
    if(setsockopt(rawfd,SOL_SOCKET,SO_BINDTODEVICE,name,strlen(name)+1)) die("SO_BINDTODEVICE");
    memset(&from,0,sizeof(from)); from.sin6_family=AF_INET6; from.sin6_addr=src;
    if(bind(rawfd,(struct sockaddr *)&from,sizeof(from))) die("bind local IPv6");
    memset(&to,0,sizeof(to)); to.sin6_family=AF_INET6; to.sin6_addr=dst;
    to.sin6_scope_id=(unsigned)in6req.ifindex;
    memset(request,0,sizeof(request));
    request[0]=128; request[4]=0x4d; request[5]=0x47; request[7]=1;
    memcpy(request+8,marker,sizeof(marker));
    /* Linux ICMPv6 raw sockets calculate the outgoing checksum. */
    if(sendto(rawfd,request,sizeof(request),0,(struct sockaddr *)&to,sizeof(to))!=(ssize_t)sizeof(request)) die("send ICMPv6");
    int64_t deadline=now_ms()+6000;
    while(now_ms()<deadline && !success) {
        struct pollfd fds[2]={{tunfd,POLLIN,0},{rawfd,POLLIN,0}};
        int remaining=(int)(deadline-now_ms());
        if(remaining<0) break;
        int rc=poll(fds,2,remaining);
        if(rc<0) { if(errno==EINTR) continue; die("poll"); }
        if(!rc) break;
        if(fds[0].revents&POLLIN) {
            ssize_t n=read(tunfd,buf,sizeof(buf));
            if(n<0) { if(errno!=EAGAIN && errno!=EINTR) die("TUN read"); }
            else if(n==(ssize_t)(40+sizeof(request)) && (buf[0]>>4)==6 && buf[6]==58 &&
                    !memcmp(buf+8,&src,16) && !memcmp(buf+24,&dst,16) &&
                    buf[40]==128 && !memcmp(buf+44,request+4,sizeof(request)-4)) {
                received_tun=1;
                printf("PASS: kernel -> TUN read received IPv6 echo request\n");
                memcpy(buf+8,&dst,16); memcpy(buf+24,&src,16); buf[7]=64;
                buf[40]=129; buf[42]=buf[43]=0;
                uint16_t checksum=icmp6_checksum(buf,(size_t)n);
                buf[42]=(unsigned char)(checksum>>8); buf[43]=(unsigned char)checksum;
                if(write(tunfd,buf,(size_t)n)!=n) die("TUN write");
                wrote_tun=1;
                printf("PASS: TUN write injected simulated peer echo reply\n");
            }
        }
        if(fds[1].revents&POLLIN) {
            ssize_t n=recv(rawfd,buf,sizeof(buf),0);
            if(n<0) { if(errno!=EINTR) die("ICMPv6 receive"); }
            else if(n==(ssize_t)sizeof(request) && buf[0]==129 &&
                    !memcmp(buf+4,request+4,sizeof(request)-4)) success=1;
        }
    }
    if(success && received_tun && wrote_tun) {
        puts("TUN_IPV6_ROUNDTRIP_PASS");
        puts("Closing the nonpersistent interface; only its test addresses/routes are removed.");
        return 0;
    }
    fprintf(stderr,"FAIL: timeout; read_request=%d injected_reply=%d received_reply=%d\n",received_tun,wrote_tun,success);
    return 1;
}
