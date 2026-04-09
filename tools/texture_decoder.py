"""
Wii/GameCube GPU texture format decoder.
Decodes tile-based texture formats to RGBA8888 pixel data.
Reference: Dolphin emulator TextureDecoder_Generic.cpp, smstools texture.py
"""

import struct
import numpy as np


# Texture format constants (GX format IDs)
I4 = 0
I8 = 1
IA4 = 2
IA8 = 3
RGB565 = 4
RGB5A3 = 5
RGBA32 = 6
C4 = 8
C8 = 9
C14X2 = 10
CMPR = 14

FORMAT_NAMES = {
    I4: 'I4', I8: 'I8', IA4: 'IA4', IA8: 'IA8',
    RGB565: 'RGB565', RGB5A3: 'RGB5A3', RGBA32: 'RGBA32',
    C4: 'C4', C8: 'C8', C14X2: 'C14X2', CMPR: 'CMPR',
}

# Block dimensions (width, height) for each format
BLOCK_DIMS = {
    I4: (8, 8), I8: (8, 4), IA4: (8, 4), IA8: (4, 4),
    RGB565: (4, 4), RGB5A3: (4, 4), RGBA32: (4, 4),
    C4: (8, 8), C8: (8, 4), C14X2: (4, 4), CMPR: (8, 8),
}

# Bytes per block
BLOCK_BYTES = {
    I4: 32, I8: 32, IA4: 32, IA8: 32,
    RGB565: 32, RGB5A3: 32, RGBA32: 64,
    C4: 32, C8: 32, C14X2: 32, CMPR: 32,
}


def decode_rgb565_pixel(val):
    r = ((val >> 11) & 0x1F) * 255 // 31
    g = ((val >> 5) & 0x3F) * 255 // 63
    b = (val & 0x1F) * 255 // 31
    return r, g, b, 255


def decode_rgb5a3_pixel(val):
    if val & 0x8000:  # RGB555, no alpha
        r = ((val >> 10) & 0x1F) * 255 // 31
        g = ((val >> 5) & 0x1F) * 255 // 31
        b = (val & 0x1F) * 255 // 31
        return r, g, b, 255
    else:  # RGB4A3
        a = ((val >> 12) & 0x07) * 255 // 7
        r = ((val >> 8) & 0x0F) * 255 // 15
        g = ((val >> 4) & 0x0F) * 255 // 15
        b = (val & 0x0F) * 255 // 15
        return r, g, b, a


def decode_i4(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[I4]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            for y in range(bh):
                for x in range(0, bw, 2):
                    if offset >= len(data):
                        return pixels
                    byte = data[offset]
                    offset += 1
                    for nibble in range(2):
                        px = bx + x + nibble
                        py = by + y
                        if px < width and py < height:
                            val = ((byte >> 4) if nibble == 0 else (byte & 0x0F)) * 0x11
                            pixels[py, px] = [val, val, val, 255]
    return pixels


def decode_i8(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[I8]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            for y in range(bh):
                for x in range(bw):
                    if offset >= len(data):
                        return pixels
                    val = data[offset]
                    offset += 1
                    px, py = bx + x, by + y
                    if px < width and py < height:
                        pixels[py, px] = [val, val, val, 255]
    return pixels


def decode_ia4(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[IA4]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            for y in range(bh):
                for x in range(bw):
                    if offset >= len(data):
                        return pixels
                    byte = data[offset]
                    offset += 1
                    px, py = bx + x, by + y
                    if px < width and py < height:
                        intensity = (byte & 0x0F) * 0x11
                        alpha = ((byte >> 4) & 0x0F) * 0x11
                        pixels[py, px] = [intensity, intensity, intensity, alpha]
    return pixels


def decode_ia8(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[IA8]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            for y in range(bh):
                for x in range(bw):
                    if offset + 1 >= len(data):
                        return pixels
                    alpha = data[offset]
                    intensity = data[offset + 1]
                    offset += 2
                    px, py = bx + x, by + y
                    if px < width and py < height:
                        pixels[py, px] = [intensity, intensity, intensity, alpha]
    return pixels


def decode_rgb565(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[RGB565]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            for y in range(bh):
                for x in range(bw):
                    if offset + 1 >= len(data):
                        return pixels
                    val = struct.unpack_from('>H', data, offset)[0]
                    offset += 2
                    px, py = bx + x, by + y
                    if px < width and py < height:
                        pixels[py, px] = decode_rgb565_pixel(val)
    return pixels


def decode_rgb5a3(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[RGB5A3]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            for y in range(bh):
                for x in range(bw):
                    if offset + 1 >= len(data):
                        return pixels
                    val = struct.unpack_from('>H', data, offset)[0]
                    offset += 2
                    px, py = bx + x, by + y
                    if px < width and py < height:
                        pixels[py, px] = decode_rgb5a3_pixel(val)
    return pixels


def decode_rgba32(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[RGBA32]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            # First 32 bytes: AR pairs for each pixel in the 4x4 block
            ar_data = data[offset:offset + 32]
            offset += 32
            # Next 32 bytes: GB pairs
            gb_data = data[offset:offset + 32]
            offset += 32
            for y in range(bh):
                for x in range(bw):
                    idx = y * bw + x
                    if idx * 2 + 1 >= len(ar_data) or idx * 2 + 1 >= len(gb_data):
                        continue
                    px, py = bx + x, by + y
                    if px < width and py < height:
                        a = ar_data[idx * 2]
                        r = ar_data[idx * 2 + 1]
                        g = gb_data[idx * 2]
                        b = gb_data[idx * 2 + 1]
                        pixels[py, px] = [r, g, b, a]
    return pixels


def decode_cmpr(data, width, height):
    """Decode CMPR (S3TC/DXT1) compressed texture."""
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    offset = 0

    for by in range(0, height, 8):
        for bx in range(0, width, 8):
            # Each 8x8 block has 4 sub-blocks of 4x4
            for sub in range(4):
                sub_x = bx + (sub % 2) * 4
                sub_y = by + (sub // 2) * 4

                if offset + 7 >= len(data):
                    return pixels

                c0 = struct.unpack_from('>H', data, offset)[0]
                c1 = struct.unpack_from('>H', data, offset + 2)[0]
                offset += 4

                # Decode the two base colors
                r0, g0, b0, _ = decode_rgb565_pixel(c0)
                r1, g1, b1, _ = decode_rgb565_pixel(c1)

                # Build color palette
                colors = [(r0, g0, b0, 255), (r1, g1, b1, 255)]
                if c0 > c1:
                    colors.append(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3, 255))
                    colors.append(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3, 255))
                else:
                    colors.append(((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2, 255))
                    colors.append((0, 0, 0, 0))  # Transparent

                # Read 4 bytes of indices (2 bits per texel, 4x4 = 32 bits)
                indices = struct.unpack_from('>I', data, offset)[0]
                offset += 4

                for y in range(4):
                    for x in range(4):
                        idx = (indices >> (30 - (y * 4 + x) * 2)) & 0x03
                        px = sub_x + x
                        py = sub_y + y
                        if px < width and py < height:
                            pixels[py, px] = colors[idx]

    return pixels


def decode_c4(data, width, height, palette):
    """Decode C4 (4-bit palette indexed)."""
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[C4]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            for y in range(bh):
                for x in range(0, bw, 2):
                    if offset >= len(data):
                        return pixels
                    byte = data[offset]
                    offset += 1
                    for nibble in range(2):
                        idx = (byte >> 4) if nibble == 0 else (byte & 0x0F)
                        px = bx + x + nibble
                        py = by + y
                        if px < width and py < height and idx < len(palette):
                            pixels[py, px] = palette[idx]
    return pixels


def decode_c8(data, width, height, palette):
    """Decode C8 (8-bit palette indexed)."""
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = BLOCK_DIMS[C8]
    offset = 0
    for by in range(0, height, bh):
        for bx in range(0, width, bw):
            for y in range(bh):
                for x in range(bw):
                    if offset >= len(data):
                        return pixels
                    idx = data[offset]
                    offset += 1
                    px, py = bx + x, by + y
                    if px < width and py < height and idx < len(palette):
                        pixels[py, px] = palette[idx]
    return pixels


DECODERS = {
    I4: decode_i4,
    I8: decode_i8,
    IA4: decode_ia4,
    IA8: decode_ia8,
    RGB565: decode_rgb565,
    RGB5A3: decode_rgb5a3,
    RGBA32: decode_rgba32,
    CMPR: decode_cmpr,
}

PALETTE_DECODERS = {
    C4: decode_c4,
    C8: decode_c8,
}


def decode_texture(data, width, height, fmt, palette=None):
    """Decode Wii texture data to RGBA numpy array."""
    if fmt in PALETTE_DECODERS:
        if palette is None:
            palette = [(128, 128, 128, 255)] * 256
        return PALETTE_DECODERS[fmt](data, width, height, palette)
    if fmt in DECODERS:
        return DECODERS[fmt](data, width, height)
    raise ValueError(f"Unsupported texture format: {fmt} ({FORMAT_NAMES.get(fmt, '?')})")
