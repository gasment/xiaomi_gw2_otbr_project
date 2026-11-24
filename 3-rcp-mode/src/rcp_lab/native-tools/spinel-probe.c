#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static int uart=-1;
static void cleanup(void) { if(uart>=0) { (void)ioctl(uart,TIOCNXCL); close(uart); } }
static void die(const char *s) { fprintf(stderr,"ERROR: %s\n",s); exit(1); }
static int64_t now_ms(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) die("clock_gettime");
    return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
static uint16_t fcs(const unsigned char *p,size_t n) {
    uint16_t c=0xffff;
    for(size_t i=0;i<n;i++) { c^=p[i]; for(int j=0;j<8;j++) c=(uint16_t)((c>>1)^((c&1)?0x8408:0)); }
    return c;
}
static size_t packed(unsigned char *p,uint32_t v) {
    size_t n=0;
    do { p[n]=(unsigned char)(v&127); v>>=7; if(v) p[n]|=128; n++; } while(v);
    return n;
}
static int unpack(const unsigned char *b,size_t n,size_t *pos,uint32_t *value) {
    uint32_t v=0;
    for(unsigned shift=0;shift<28;shift+=7) {
        if(*pos>=n) return -1;
        unsigned c=b[(*pos)++]; v|=(c&127)<<shift;
        if(!(c&128)) { *value=v; return 0; }
    }
    return -1;
}
static void send_get(unsigned tid,uint32_t property) {
    unsigned char raw[16],encoded[40]; size_t n=0,m=0;
    raw[n++]=(unsigned char)(0x80|tid); raw[n++]=2; /* PROP_VALUE_GET only. */
    n+=packed(raw+n,property);
    uint16_t c=(uint16_t)~fcs(raw,n); raw[n++]=(unsigned char)c; raw[n++]=(unsigned char)(c>>8);
    encoded[m++]=0x7e;
    for(size_t i=0;i<n;i++) {
        unsigned char b=raw[i];
        if(b==0x7e || b==0x7d || b==0x11 || b==0x13 || b==0xf8) { encoded[m++]=0x7d; b^=0x20; }
        encoded[m++]=b;
    }
    encoded[m++]=0x7e;
    size_t off=0; int64_t end=now_ms()+2000;
    while(off<m) {
        ssize_t written=write(uart,encoded+off,m-off);
        if(written>0) { off+=(size_t)written; continue; }
        if(written<0 && errno!=EINTR && errno!=EAGAIN) die("UART write");
        if(now_ms()>=end) die("UART write timeout; check flow control");
        struct pollfd p={uart,POLLOUT,0}; (void)poll(&p,1,100);
    }
}
static size_t get(unsigned tid,uint32_t prop,unsigned char *result,size_t cap) {
    for(int attempt=0;attempt<3;attempt++) {
        send_get(tid,prop);
        unsigned char frame[2048]; size_t n=0; int started=0,escaped=0;
        int64_t end=now_ms()+2500;
        while(now_ms()<end) {
            struct pollfd p={uart,POLLIN,0};
            int remaining=(int)(end-now_ms());
            if(remaining<=0) break;
            int rc=poll(&p,1,remaining);
            if(rc<0) { if(errno==EINTR) continue; die("UART poll"); }
            if(rc==0) break;
            if(p.revents&(POLLERR|POLLHUP|POLLNVAL)) die("UART disconnected");
            unsigned char b; ssize_t count=read(uart,&b,1);
            if(count<0) { if(errno==EAGAIN || errno==EINTR) continue; die("UART read"); }
            if(!count) continue;
            if(b==0x7e) {
                if(n>=5 && fcs(frame,n)==0xf0b8 && (frame[0]&0x8f)==(0x80|tid)) {
                    size_t pos=1; uint32_t command,key;
                    if(!unpack(frame,n-2,&pos,&command) && !unpack(frame,n-2,&pos,&key) && command==6) {
                        if(key==prop) {
                            size_t len=n-2-pos;
                            if(len>cap) die("Property value too long");
                            memcpy(result,frame+pos,len); return len;
                        }
                        if(key==0) {
                            uint32_t status=0;
                            (void)unpack(frame,n-2,&pos,&status);
                            fprintf(stderr,"Property %u returned LAST_STATUS=%u\n",prop,status);
                            die("RCP property request rejected");
                        }
                    }
                }
                n=0; started=1; escaped=0; continue;
            }
            if(!started) continue;
            if(!escaped && b==0x7d) { escaped=1; continue; }
            if(escaped) { b^=0x20; escaped=0; }
            if(n==sizeof(frame)) { n=0; started=0; continue; }
            frame[n++]=b;
        }
        fprintf(stderr,"GET property %u timed out, attempt %d/3\n",prop,attempt+1);
    }
    die("No valid Spinel property response at the selected baud rate"); return 0;
}
static uint32_t one_uint(unsigned tid,uint32_t prop,const char *label) {
    unsigned char value[64]; size_t n=get(tid,prop,value,sizeof(value)),pos=0; uint32_t v;
    if(unpack(value,n,&pos,&v) || pos!=n) die("Invalid integer property");
    printf("%s=%u\n",label,v); return v;
}
int main(int argc,char **argv) {
    int legacy = argc > 1 && strcmp(argv[1], "--legacy") == 0;
    if (legacy) { --argc; ++argv; }
    if(argc>2) { fprintf(stderr,"Usage: spinel-probe [--legacy] [UART_DEVICE]\n"); return 2; }
    const char *device=argc==2?argv[1]:"/dev/ttyS1";
    setvbuf(stdout,NULL,_IONBF,0); atexit(cleanup);
    uart=open(device,O_RDWR|O_NOCTTY|O_NONBLOCK);
    if(uart<0) { perror(device); die("open UART"); }
    if(ioctl(uart,TIOCEXCL)) die("TIOCEXCL");
    struct termios t;
    if(tcgetattr(uart,&t)) die("tcgetattr");
    cfmakeraw(&t); t.c_cflag|=CLOCAL|CREAD; t.c_cflag&=~(CSTOPB|PARENB|CRTSCTS);
    if (legacy) t.c_cflag |= CRTSCTS;
    t.c_cc[VMIN]=0; t.c_cc[VTIME]=0;
    speed_t rate = legacy ? B460800 : B115200;
    if(cfsetispeed(&t,rate) || cfsetospeed(&t,rate) || tcsetattr(uart,TCSANOW,&t)) die("UART configuration");
    unsigned char value[1024]; size_t n=get(1,2,value,sizeof(value)-1);
    if(!n) die("Empty version string");
    value[n]=0; printf("NCP_VERSION=%s\n",value);
    unsigned char release_version[sizeof(value)];
    memcpy(release_version, value, n + 1);
    if(!strstr((const char *)value,"OPENTHREAD")) die("Unexpected firmware version string");
    n=get(2,1,value,sizeof(value)); size_t pos=0; uint32_t major,minor;
    if(unpack(value,n,&pos,&major) || unpack(value,n,&pos,&minor)) die("Invalid protocol version");
    printf("SPINEL_PROTOCOL_VERSION=%u.%u\n",major,minor);
    n=get(3,5,value,sizeof(value)); pos=0; printf("CAPABILITIES=");
    while(pos<n) { uint32_t cap; if(unpack(value,n,&pos,&cap)) die("Invalid capability list"); printf("%u ",cap); }
    putchar('\n');
    uint32_t api=one_uint(4,0xb0,"RCP_API_VERSION");
    uint32_t minimum=one_uint(5,0xb1,"RCP_MIN_HOST_API_VERSION");
    if(api<minimum) die("Inconsistent RCP API versions");
    if (!legacy && (strncmp((const char *)release_version, "SL-OPENTHREAD/2.5.3.0_GitHub-1fceb225b;",
                            sizeof("SL-OPENTHREAD/2.5.3.0_GitHub-1fceb225b;") - 1) || api != 10))
        die("Unexpected 2.5.3.0 test RCP version or API");
    puts("SPINEL_RCP_PROBE_PASS");
    puts("Only PROP_VALUE_GET requests were sent; no reset, SET, flash or network configuration command.");
    return 0;
}
