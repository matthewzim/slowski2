"""
Yaz0 decompression for Nintendo Wii/GameCube compressed data.
"""

import struct


def is_yaz0(data):
    return len(data) >= 4 and data[:4] == b'Yaz0'


def decompress(data):
    """Decompress Yaz0 data. Returns decompressed bytes."""
    if not is_yaz0(data):
        raise ValueError("Not Yaz0 data")

    decompressed_size = struct.unpack_from('>I', data, 4)[0]
    output = bytearray(decompressed_size)

    src = 16  # Skip header
    dst = 0
    group_head = 0
    group_head_len = 0

    while dst < decompressed_size and src < len(data):
        if group_head_len == 0:
            group_head = data[src]
            src += 1
            group_head_len = 8

        if group_head & 0x80:
            # Direct copy
            if src >= len(data):
                break
            output[dst] = data[src]
            src += 1
            dst += 1
        else:
            # Reference copy
            if src + 1 >= len(data):
                break
            b1 = data[src]
            b2 = data[src + 1]
            src += 2

            dist = ((b1 & 0x0F) << 8) | b2
            copy_src = dst - dist - 1

            length = b1 >> 4
            if length == 0:
                # Extended length
                if src >= len(data):
                    break
                length = data[src] + 0x12
                src += 1
            else:
                length += 2

            for _ in range(length):
                if dst >= decompressed_size:
                    break
                if copy_src < 0 or copy_src >= dst:
                    output[dst] = 0
                else:
                    output[dst] = output[copy_src]
                copy_src += 1
                dst += 1

        group_head <<= 1
        group_head_len -= 1

    return bytes(output)
