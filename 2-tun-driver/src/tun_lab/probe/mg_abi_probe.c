#include <linux/module.h>
#include <linux/init.h>
#include <linux/stddef.h>
#include <linux/netdevice.h>
#include <linux/skbuff.h>
#include <net/sock.h>

const unsigned int mg_sizeof_module = sizeof(struct module);
const unsigned int mg_module_init_offset = offsetof(struct module, init);
const unsigned int mg_module_exit_offset = offsetof(struct module, exit);
const unsigned int mg_sizeof_net_device = sizeof(struct net_device);
const unsigned int mg_sizeof_sk_buff = sizeof(struct sk_buff);
const unsigned int mg_sizeof_sock = sizeof(struct sock);

const unsigned int mg_sizeof_device = sizeof(struct device);
const unsigned int mg_sizeof_dev_pm_info = sizeof(struct dev_pm_info);
const unsigned int mg_netdev_tx_offset = offsetof(struct net_device, _tx);
const unsigned int mg_netdev_dev_offset = offsetof(struct net_device, dev);
const unsigned int mg_skb_data_offset = offsetof(struct sk_buff, data);
const unsigned int mg_skb_head_offset = offsetof(struct sk_buff, head);
const unsigned int mg_skb_len_offset = offsetof(struct sk_buff, len);
const unsigned int mg_skb_dev_offset = offsetof(struct sk_buff, dev);
const unsigned int mg_skb_mac_header_offset = offsetof(struct sk_buff, mac_header);


static int __init mg_probe_init(void)
{
    pr_info("mg_abi_probe: loaded\n");
    return 0;
}
static void __exit mg_probe_exit(void)
{
    pr_info("mg_abi_probe: unloaded\n");
}
module_init(mg_probe_init);
module_exit(mg_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Xiaomi gateway module ABI measurement; do not load before review");
