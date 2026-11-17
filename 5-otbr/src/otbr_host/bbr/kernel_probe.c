#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <linux/mroute6.h>
#include <unistd.h>

int main(void) {
    int value = 0;
    socklen_t size = sizeof(value);
    int fd = socket(AF_INET6, SOCK_RAW | SOCK_CLOEXEC, IPPROTO_ICMPV6);
    if (fd < 0) {
        int error = errno;
        printf("BBR_RAW_SOCKET_UNAVAILABLE errno=%d (%s)\n", error, strerror(error));
        puts("Run as root. This result alone does not determine multicast-routing support.");
        return 3;
    }
    /* Query only: never call MRT6_INIT, MRT6_ADD_MIF, JOIN_GROUP or send().
     * Linux 4.9 returns its API version without taking router ownership. */
    int result = getsockopt(fd, IPPROTO_IPV6, MRT6_VERSION, &value, &size);
    int error = errno;
    close(fd);
    if (result == 0 && size == sizeof(value)) {
        printf("BBR_KERNEL_MROUTE_API_PRESENT version=0x%x\n", (unsigned int)value);
        puts("The read-only API exists. Router initialization and forwarding remain untested.");
        return 0;
    }
    if (result < 0 && (error == ENOPROTOOPT || error == EOPNOTSUPP)) {
        printf("BBR_KERNEL_MROUTE_API_UNSUPPORTED errno=%d (%s)\n", error, strerror(error));
        puts("The standard Linux BBR multicast backend cannot be assumed usable.");
        return 2;
    }
    printf("BBR_KERNEL_MROUTE_API_INCONCLUSIVE result=%d errno=%d (%s) length=%u\n",
           result, result < 0 ? error : 0, result < 0 ? strerror(error) : "unexpected value length", (unsigned int)size);
    return 3;
}
