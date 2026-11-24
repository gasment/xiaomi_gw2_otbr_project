"""Check the Xiaomi experiment image without opening a serial port."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parent
HEADER, APPLICATION, PROGRAM, METADATA, END = (
    0x03A617EB, 0xF40A0AF4, 0xFD0303FD, 0xF60808F6, 0xFC0404FC,
)
EXPECTED = "2.5.3.0_GitHub-1fceb225b"


def verify(path):
    data = path.read_bytes()
    assert 32 <= len(data) <= 0x80000, path
    position = 0
    tags = []
    ranges = []
    metadata = None
    while position + 8 <= len(data):
        tag, size = struct.unpack_from("<II", data, position)
        position += 8
        assert position + size <= len(data), "Truncated tag"
        value = data[position:position + size]
        position += size
        tags.append(tag)
        if tag == PROGRAM:
            assert size > 4
            start, = struct.unpack_from("<I", value)
            end = start + size - 4
            assert 0x4000 <= start < end <= 0x80000
            ranges.append((start, end))
        elif tag == METADATA:
            metadata = json.loads(value)
        elif tag == END:
            assert size == 4
            assert data[position:] in (b"", b"\xff", b"\xff\xff", b"\xff\xff\xff")
            assert zlib.crc32(data[:position]) == 0x2144DF1C
            break
        else:
            assert tag in (HEADER, APPLICATION), f"Unsupported tag: {tag:#x}"
    assert tags[0] == HEADER and tags[-1] == END
    for tag in (HEADER, APPLICATION, METADATA, END):
        assert tags.count(tag) == 1
    assert ranges and min(start for start, _ in ranges) == 0x4000
    ordered = sorted(ranges)
    assert all(left[1] <= right[0] for left, right in zip(ordered, ordered[1:]))
    assert metadata["fw_type"] == "openthread_rcp" and metadata["baudrate"] == 115200
    print(f"{path.name}: {len(data)} bytes, application {ordered[0][0]:#x}..{ordered[-1][1] - 1:#x}, CRC OK")
    return metadata



if __name__ == "__main__":
    import sys
    assert verify(Path(sys.argv[1]))["ot_rcp_version"].removeprefix("SL-OPENTHREAD/") == EXPECTED
