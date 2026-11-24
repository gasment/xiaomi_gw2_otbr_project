"""Fingerprints of 0.3.0 installations shipped before VERSION was persisted."""

LEGACY_030 = {
    "openssh": {
        "/data/openssh/sbin/sshd": "1cbcb7d1cca6e417cec0b801e0b73ce660804043020913826d327e638739b118",
        "/data/openssh/start-ssh.sh": "fd45e22c8dfeb759fc2aad397568014a47cfb85133041d61031399ad190ae41c"
    },
    "tun": {
        "/data/tun/tun.ko": "99cb2d19c5d70b178d569f68e2f570a69d043ad7c85ef4e9e8e155ff73db5de1",
        "/data/tun/start-tun.sh": "57d12f46d7c61401f23d2b3872faec840b8f5b80f5a2603ce9d390f0ac8996c5"
    },
    "ble-cache": {
        "/data/ble-spec-cache/ble-cache-clock": "a92314119171b67eadfe06b54473b66bb3ccb49e84064f8d3b9146d1cad1100a",
        "/data/ble-spec-cache/spec-cache.lua": "126dd0b1f87932608d6c2bc0bceef781af42ba82155d32197874e05fd5f4a383"
    },
    "otbr": {
        "/data/otbr/mi-otbr-host": "8fb32e3e020bcd8f8ea914d870a64deb18aaff7ce6420a6e3e0cf3ac2866fa54",
        "/data/otbr/start.sh": "720690f53fba5f225436330fffe15d95535af167d43ede9234e65ce7c91984e1"
    }
}

LEGACY_030_GITHUB_OTBR = {'/data/otbr/mi-otbr-host': 'c39394577ffbc0c543264a2d04aba0547b3fd6c7998299c4d89e8710891050b5', '/data/otbr/start.sh': '720690f53fba5f225436330fffe15d95535af167d43ede9234e65ce7c91984e1'}
