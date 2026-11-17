#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static int serial=-1,uploading=0;
static volatile sig_atomic_t interrupted=0;
static void signal_handler(int n) { (void)n; interrupted=1; }
static void cleanup(void) {
    if(serial>=0) {
        if(uploading) {
            const unsigned char cancel[2]={0x18,0x18};
            ssize_t sent=write(serial,cancel,sizeof(cancel));
            if(sent!=(ssize_t)sizeof(cancel)) {
                fputs("WARNING: cancellation bytes were not fully sent; keep the radio in bootloader for recovery.\n",stderr);
            }
        }
        (void)ioctl(serial,TIOCNXCL);
        close(serial);
    }
}
static void fail(const char *s) { fprintf(stderr,"ERROR: %s\n",s); exit(1); }
static int64_t now_ms(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) fail("clock_gettime");
    return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint32_t crc32_bytes(const unsigned char *b,size_t n) {
    uint32_t c=0xffffffff;
    for(size_t i=0;i<n;i++) { c^=b[i]; for(int j=0;j<8;j++) c=(c>>1)^((c&1)?0xedb88320:0); }
    return c^0xffffffff;
}
static uint16_t crc16_bytes(const unsigned char *b,size_t n) {
    uint16_t c=0;
    for(size_t i=0;i<n;i++) { c^=(uint16_t)b[i]<<8; for(int j=0;j<8;j++) c=(uint16_t)((c<<1)^((c&0x8000)?0x1021:0)); }
    return c;
}
static unsigned char *load_gbl(const char *path,size_t *length) {
    FILE *f=fopen(path,"rb"); if(!f) fail("cannot open firmware");
    if(fseek(f,0,SEEK_END)) fail("firmware seek");
    long len=ftell(f); if(len<32 || len>0x80000) fail("unexpected firmware size");
    rewind(f);
    unsigned char *b=malloc((size_t)len); if(!b) fail("out of memory");
    if(fread(b,1,(size_t)len,f)!=(size_t)len) fail("firmware read");
    fclose(f);
    size_t p=0,end=0; int programs=0,applications=0;
    if(le32(b)!=0x03a617eb) fail("not a GBL3 image");
    while(p+8<=(size_t)len) {
        uint32_t tag=le32(b+p),n=le32(b+p+4);
        if(n>(size_t)len-p-8) fail("invalid GBL tag length");
        const unsigned char *v=b+p+8;
        if(tag==0xfd0303fd) {
            if(n<4) fail("invalid program tag");
            uint32_t start=le32(v);
            if(start<0x4000 || (uint64_t)start+n-4>0x80000) fail("program block outside application area");
            programs++;
        } else if(tag==0xf40a0af4) applications++;
        else if(tag!=0x03a617eb && tag!=0xf60808f6 && tag!=0xfc0404fc)
            fail("unsupported GBL tag (bootloader/security updates are not allowed)");
        p+=8+n;
        if(tag==0xfc0404fc) { if(n!=4) fail("invalid end tag"); end=p; break; }
    }
    if(!end || programs==0 || applications!=1) fail("incomplete application GBL");
    if((size_t)len-end>3) fail("unexpected trailing data");
    for(size_t j=end;j<(size_t)len;j++) if(b[j]!=0xff) fail("invalid padding");
    if(crc32_bytes(b,end)!=0x2144df1c) fail("GBL CRC mismatch");
    *length=(size_t)len;
    printf("GBL_VALIDATED: %zu bytes; application-only tags and CRC checked\n",*length);
    return b;
}
static void open_serial(const char *device) {
    serial=open(device,O_RDWR|O_NOCTTY|O_NONBLOCK);
    if(serial<0) { perror(device); fail("open serial"); }
    if(ioctl(serial,TIOCEXCL)) fail("TIOCEXCL");
    struct termios t;
    if(tcgetattr(serial,&t)) fail("tcgetattr");
    cfmakeraw(&t); t.c_cflag|=CLOCAL|CREAD|CRTSCTS; t.c_cflag&=~(CSTOPB|PARENB);
    t.c_cc[VMIN]=0; t.c_cc[VTIME]=0;
    if(cfsetispeed(&t,B115200) || cfsetospeed(&t,B115200) || tcsetattr(serial,TCSANOW,&t)) fail("serial configuration");
}
static void send_bytes(const unsigned char *b,size_t n) {
    int64_t deadline=now_ms()+5000;
    while(n) {
        if(interrupted) fail("interrupted");
        ssize_t k=write(serial,b,n);
        if(k>0) { b+=k; n-=(size_t)k; continue; }
        if(k<0 && errno!=EAGAIN && errno!=EINTR) fail("serial write");
        if(now_ms()>=deadline) fail("serial write timeout (check RTS/CTS)");
        struct pollfd p={serial,POLLOUT,0}; (void)poll(&p,1,100);
    }
}
static int read_byte_until(int64_t deadline) {
    for(;;) {
        if(interrupted) fail("interrupted");
        int64_t remaining=deadline-now_ms(); if(remaining<=0) return -1;
        struct pollfd p={serial,POLLIN,0};
        int rc=poll(&p,1,(int)remaining);
        if(rc<0) { if(errno==EINTR) continue; fail("serial poll"); }
        if(!rc) return -1;
        if(p.revents&(POLLERR|POLLHUP|POLLNVAL)) fail("serial connection lost");
        unsigned char b; ssize_t n=read(serial,&b,1);
        if(n==1) return b;
        if(n<0 && errno!=EAGAIN && errno!=EINTR) fail("serial read");
    }
}
static void get_menu(char *out,size_t cap,int timeout) {
    size_t n=0; int64_t deadline=now_ms()+timeout;
    out[0]=0;
    for(;;) {
        int c=read_byte_until(deadline); if(c<0) fail("bootloader menu timeout");
        if(c==0) c=' ';
        if(n+1>=cap) fail("bootloader output too long");
        out[n++]=(char)c; out[n]=0;
        if(strstr(out,"BL > ")) break;
    }
    fputs(out,stdout); putchar('\n');
    if(!strstr(out,"Gecko Bootloader v1.9.2")) fail("expected validated Gecko Bootloader 1.9.2");
}
static int await_ack(int timeout) {
    int64_t deadline=now_ms()+timeout;
    for(;;) {
        int c=read_byte_until(deadline);
        if(c==0x06 || c==0x15 || c==0x18 || c<0) return c;
        /* Ignore bootloader CR/LF or a repeated CRC-mode C. */
    }
}
int main(int argc,char **argv) {
    setvbuf(stdout,NULL,_IONBF,0); atexit(cleanup);
    signal(SIGINT,signal_handler); signal(SIGTERM,signal_handler);
    int flash=argc>=2 && !strcmp(argv[1],"flash");
    if((!flash && !(argc==3 && !strcmp(argv[1],"probe"))) || (flash && argc!=4)) {
        fprintf(stderr,"Usage: radio-flasher probe DEVICE\n       radio-flasher flash DEVICE APPLICATION.gbl\n"); return 2;
    }
    size_t length=0; unsigned char *firmware=NULL;
    if(flash) firmware=load_gbl(argv[3],&length); /* Validate before opening UART. */
    open_serial(argv[2]);
    const unsigned char enter='\r'; send_bytes(&enter,1);
    char menu[8192]; get_menu(menu,sizeof(menu),8000);
    if(!flash) { puts("BOOTLOADER_PROBE_PASS (no upload requested)"); return 0; }
    const unsigned char upload='1'; send_bytes(&upload,1); uploading=1;
    int c; int64_t deadline=now_ms()+15000;
    do { c=read_byte_until(deadline); if(c<0) fail("XMODEM CRC handshake timeout"); if(c==0x18) fail("receiver cancelled before upload"); } while(c!='C');
    size_t chunks=(length+127)/128;
    for(size_t i=0;i<chunks;i++) {
        unsigned char packet[133]; packet[0]=1; packet[1]=(unsigned char)(i+1); packet[2]=(unsigned char)(255-packet[1]);
        memset(packet+3,0xff,128);
        size_t remain=length-i*128; memcpy(packet+3,firmware+i*128,remain<128?remain:128);
        uint16_t crc=crc16_bytes(packet+3,128); packet[131]=(unsigned char)(crc>>8); packet[132]=(unsigned char)crc;
        int acked=0;
        for(int retry=0;retry<10;retry++) {
            send_bytes(packet,sizeof(packet)); c=await_ack(4000);
            if(c==0x18) fail("receiver cancelled upload");
            if(c==0x06) { acked=1; break; }
            fprintf(stderr,"Retry block %zu (%d/10)\n",i+1,retry+1);
        }
        if(!acked) fail("XMODEM block retry limit");
        if(i%64==0 || i+1==chunks) printf("Upload %zu/%zu blocks\n",i+1,chunks);
    }
    int finished=0; const unsigned char eot=4;
    for(int retry=0;retry<10;retry++) {
        send_bytes(&eot,1); c=await_ack(4000);
        if(c==0x18) fail("receiver cancelled at EOT");
        if(c==0x06) { finished=1; break; }
    }
    if(!finished) fail("XMODEM EOT not acknowledged");
    get_menu(menu,sizeof(menu),10000);
    if(!strstr(menu,"Serial upload complete") || strstr(menu,"Serial upload aborted")) fail("bootloader did not confirm successful GBL installation");
    uploading=0;
    const unsigned char run='2'; send_bytes(&run,1);
    puts("APPLICATION_UPLOAD_PASS: bootloader accepted image; run command sent.");
    puts("Verify the running application separately. No bootloader image or mass erase command was sent.");
    free(firmware);
    return 0;
}
