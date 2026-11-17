# 1.0.8_0015 runtime acceptance

Model: lumi.gateway.mcn001; Linux 4.9.84 #1, built 2026-08-19.
The 0015 stock ccm.ko module layout and bridge.ko network-field anchors match the candidate configuration. All 125 required imports exist in the running kernel export snapshot.

Verified on the upgraded gateway:
- ABI probe loaded and unloaded.
- Rebuilt TUN loaded without force flags; misc device is 10:200.
- TUNSETIFF, temporary IPv6 addressing, kernel-to-TUN read and TUN-to-kernel reply injection passed: TUN_IPV6_ROUNDTRIP_PASS.
- Temporary mgtun0 disappeared after closing the descriptor.
- No kernel Oops, panic or unknown-symbol error was observed during these tests.

This validates the tested TUN path; it does not prove all possible kernel ABI fields or TUN/TAP modes.
