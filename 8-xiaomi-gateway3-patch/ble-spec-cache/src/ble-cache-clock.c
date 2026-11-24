#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stop;
static void terminate(int sig){(void)sig;stop=1;}
static void pause_seconds(unsigned n){while(n--&&!stop)sleep(1);}
static int write_all(int fd,const unsigned char *p,size_t n){
  while(n&&!stop){ssize_t k=send(fd,p,n,MSG_NOSIGNAL);if(k<0&&errno==EINTR)continue;if(k<=0)return -1;p+=k;n-=(size_t)k;}
  return n?-1:0;
}
static int packet(int fd,unsigned char type,const unsigned char *p,size_t n){
  if(n>=128)return -1;
  unsigned char h[2]={type,(unsigned char)n};
  return write_all(fd,h,2)||write_all(fd,p,n)?-1:0;
}
static int receive_ack(int fd){
  unsigned char b[4];size_t pos=0;time_t end=time(NULL)+5;
  while(pos<4&&!stop){
    if(time(NULL)>=end)return -1;
    fd_set set;FD_ZERO(&set);FD_SET(fd,&set);struct timeval tv={1,0};
    int r=select(fd+1,&set,NULL,NULL,&tv);if(r<0&&errno==EINTR)continue;if(r<0)return -1;if(!r)continue;
    ssize_t k=recv(fd,b+pos,4-pos,0);if(k<=0)return -1;pos+=(size_t)k;
  }
  return pos==4&&b[0]==0x20&&b[1]==2&&b[2]==0&&b[3]==0?0:-1;
}
static int connect_mqtt(void){
  int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return -1;
  struct timeval timeout={3,0};
  if(setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout))<0){close(fd);return -1;}
  struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_port=htons(1883);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
  if(connect(fd,(struct sockaddr*)&a,sizeof(a))<0){close(fd);return -1;}
  unsigned char p[96]={0,6,'M','Q','I','s','d','p',3,2,0xfd,0x20};
  char id[24];snprintf(id,sizeof(id),"gw2clock-%08lx",(unsigned long)getpid()&0xffffffffUL);
  size_t len=strlen(id);p[12]=0;p[13]=(unsigned char)len;memcpy(p+14,id,len);
  if(packet(fd,0x10,p,14+len)<0||receive_ack(fd)<0){close(fd);return -1;}
  return fd;
}
int main(int argc,char **argv){
  if(argc==2&&!strcmp(argv[1],"--version")){puts("gw2-ble-cache-clock-v1 MQTT3.1 localhost-only");return 0;}
  int once=argc==2&&!strcmp(argv[1],"--once");
  const char *learn=NULL;
  if(argc==3&&!strcmp(argv[1],"--learn-product")){
    char *end=NULL;errno=0;unsigned long pid=strtoul(argv[2],&end,10);
    if(errno||!argv[2][0]||strspn(argv[2],"0123456789")!=strlen(argv[2])||*end||pid<1||pid>65535){fputs("Invalid product ID (1..65535)\n",stderr);return 2;}
    learn=argv[2];once=1;
  }
  if(argc>1&&!once){fprintf(stderr,"Usage: %s [--version|--once|--learn-product PDID]\n",argv[0]);return 2;}
  signal(SIGTERM,terminate);signal(SIGINT,terminate);signal(SIGHUP,SIG_IGN);signal(SIGPIPE,SIG_IGN);
  umask(0077);setvbuf(stdout,NULL,_IOLBF,0);
  int lock=-1;
  if(!once){
    lock=open("/tmp/gw2-ble-cache-clock.lock",O_RDWR|O_CREAT,0600);
    if(lock<0||flock(lock,LOCK_EX|LOCK_NB)<0){fputs("clock already running or lock unavailable\n",stderr);if(lock>=0)close(lock);return 1;}
    FILE *pid=fopen("/tmp/gw2-ble-cache-clock.pid","w");if(!pid){perror("PID file");close(lock);return 1;}
    if(fprintf(pid,"%ld\n",(long)getpid())<0||fclose(pid)!=0){close(lock);return 1;}
  }
  const char *topic=learn?"gw2/ble-spec-cache/learn":"gw2/ble-spec-cache/tick";
  const char *body=learn?learn:"1";unsigned char payload[96];size_t n=strlen(topic),bodylen=strlen(body);
  payload[0]=0;payload[1]=(unsigned char)n;memcpy(payload+2,topic,n);memcpy(payload+2+n,body,bodylen);
  int result=0;
  while(!stop){
    int fd=connect_mqtt();if(fd<0){if(once){result=1;break;}pause_seconds(2);continue;}
    puts("BLE cache clock connected to local MQTT");
    do{
      if(packet(fd,0x30,payload,n+2+bodylen)<0){result=1;break;}
      if(once)break;
      pause_seconds(1);
      unsigned char byte;ssize_t got=recv(fd,&byte,1,MSG_PEEK|MSG_DONTWAIT);
      if(got==0||(got<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR)){result=1;break;}
    }while(!stop);
    close(fd);if(once)break;
    if(!stop){puts("BLE cache clock reconnecting local MQTT");pause_seconds(2);}
  }
  if(lock>=0){unlink("/tmp/gw2-ble-cache-clock.pid");close(lock);}
  if(learn&&result==0)puts("LEARN_REQUEST_SENT: check patch status for the cloud result; this is not a learning success result.");
  return once?result:0;
}
