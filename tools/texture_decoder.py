"""
Wii/GameCube GPU texture format decoder (vectorized with numpy).
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

BLOCK_DIMS = {
    I4: (8, 8), I8: (8, 4), IA4: (8, 4), IA8: (4, 4),
    RGB565: (4, 4), RGB5A3: (4, 4), RGBA32: (4, 4),
    C4: (8, 8), C8: (8, 4), C14X2: (4, 4), CMPR: (8, 8),
}

BLOCK_BYTES = {
    I4: 32, I8: 32, IA4: 32, IA8: 32,
    RGB565: 32, RGB5A3: 32, RGBA32: 64,
    C4: 32, C8: 32, C14X2: 32, CMPR: 32,
}


def _build_tile_map(width, height, bw, bh):
    """Build a mapping from linear tile order to (py, px) coordinates.
    Returns (py_arr, px_arr) arrays where index i maps to pixel (py[i], px[i]).
    """
    # Number of tile columns and rows (round up)
    tiles_x = (width + bw - 1) // bw
    tiles_y = (height + bh - 1) // bh

    # For each tile, generate the (py, px) for every pixel in tile order
    # Tile order: row-major tiles, row-major pixels within tile
    ty = np.arange(tiles_y)
    tx = np.arange(tiles_x)
    iy = np.arange(bh)
    ix = np.arange(bw)

    # Broadcast to get all combinations: (tiles_y, tiles_x, bh, bw)
    py = (ty[:, None, None, None] * bh + iy[None, None, :, None]).ravel()
    px = (tx[None, :, None, None] * bw + ix[None, None, None, :]).ravel()

    # Tile the coordinates to match iteration order
    # Order is: for ty -> for tx -> for iy -> for ix
    py_full = np.repeat(ty * bh, tiles_x * bh * bw) + np.tile(
        np.repeat(iy, bw), tiles_x * tiles_y
    ).ravel()[:tiles_y * tiles_x * bh * bw]

    # Simpler approach: build explicitly
    total = tiles_y * tiles_x * bh * bw
    py_arr = np.empty(total, dtype=np.int32)
    px_arr = np.empty(total, dtype=np.int32)
    idx = 0
    for by in range(0, tiles_y * bh, bh):
        for bx in range(0, tiles_x * bw, bw):
            for y in range(bh):
                for x in range(bw):
                    py_arr[idx] = by + y
                    px_arr[idx] = bx + x
                    idx += 1

    return py_arr[:idx], px_arr[:idx]


# Cache tile maps to avoid rebuilding
_tile_map_cache = {}


def _get_tile_map(width, height, bw, bh):
    key = (width, height, bw, bh)
    if key not in _tile_map_cache:
        _tile_map_cache[key] = _build_tile_map(width, height, bw, bh)
    return _tile_map_cache[key]


def decode_rgb565_pixel(val):
    r = ((val >> 11) & 0x1F) * 255 // 31
    g = ((val >> 5) & 0x3F) * 255 // 63
    b = (val & 0x1F) * 255 // 31
    return r, g, b, 255


def decode_rgb5a3_pixel(val):
    if val & 0x8000:
        r = ((val >> 10) & 0x1F) * 255 // 31
        g = ((val >> 5) & 0x1F) * 255 // 31
        b = (val & 0x1F) * 255 // 31
        return r, g, b, 255
    else:
        a = ((val >> 12) & 0x07) * 255 // 7
        r = ((val >> 8) & 0x0F) * 255 // 15
        g = ((val >> 4) & 0x0F) * 255 // 15
        b = (val & 0x0F) * 255 // 15
        return r, g, b, a


def _rgb565_vec(vals):
    """Vectorized RGB565 decode. vals is uint16 array."""
    r = ((vals >> 11) & 0x1F).astype(np.uint16) * 255 // 31
    g = ((vals >> 5) & 0x3F).astype(np.uint16) * 255 // 63
    b = (vals & 0x1F).astype(np.uint16) * 255 // 31
    return r.astype(np.uint8), g.astype(np.uint8), b.astype(np.uint8)


def decode_i4(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 8, 8
    py_map, px_map = _get_tile_map(width, height, bw, bh)

    # Each byte has 2 pixels (high nibble first)
    num_pixels = len(py_map)
    num_bytes = (num_pixels + 1) // 2
    raw = np.frombuffer(data[:num_bytes], dtype=np.uint8)

    # Extract nibbles
    high = (raw >> 4) * 0x11
    low = (raw & 0x0F) * 0x11
    interleaved = np.empty(len(raw) * 2, dtype=np.uint8)
    interleaved[0::2] = high
    interleaved[1::2] = low
    interleaved = interleaved[:num_pixels]

    # Filter valid coordinates
    valid = (py_map < height) & (px_map < width)
    valid_idx = np.where(valid)[0]
    valid_idx = valid_idx[valid_idx < len(interleaved)]

    vals = interleaved[valid_idx]
    pixels[py_map[valid_idx], px_map[valid_idx], 0] = vals
    pixels[py_map[valid_idx], px_map[valid_idx], 1] = vals
    pixels[py_map[valid_idx], px_map[valid_idx], 2] = vals
    pixels[py_map[valid_idx], px_map[valid_idx], 3] = 255
    return pixels


def decode_i8(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 8, 4
    py_map, px_map = _get_tile_map(width, height, bw, bh)

    num_pixels = len(py_map)
    raw = np.frombuffer(data[:num_pixels], dtype=np.uint8)

    valid = (py_map < height) & (px_map < width)
    valid_idx = np.where(valid)[0]
    valid_idx = valid_idx[valid_idx < len(raw)]

    vals = raw[valid_idx]
    pixels[py_map[valid_idx], px_map[valid_idx], 0] = vals
    pixels[py_map[valid_idx], px_map[valid_idx], 1] = vals
    pixels[py_map[valid_idx], px_map[valid_idx], 2] = vals
    pixels[py_map[valid_idx], px_map[valid_idx], 3] = 255
    return pixels


def decode_ia4(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 8, 4
    py_map, px_map = _get_tile_map(width, height, bw, bh)

    num_pixels = len(py_map)
    raw = np.frombuffer(data[:num_pixels], dtype=np.uint8)

    valid = (py_map < height) & (px_map < width)
    valid_idx = np.where(valid)[0]
    valid_idx = valid_idx[valid_idx < len(raw)]

    bytes_v = raw[valid_idx]
    intensity = (bytes_v & 0x0F) * 0x11
    alpha = ((bytes_v >> 4) & 0x0F) * 0x11

    pixels[py_map[valid_idx], px_map[valid_idx], 0] = intensity
    pixels[py_map[valid_idx], px_map[valid_idx], 1] = intensity
    pixels[py_map[valid_idx], px_map[valid_idx], 2] = intensity
    pixels[py_map[valid_idx], px_map[valid_idx], 3] = alpha
    return pixels


def decode_ia8(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 4, 4
    py_map, px_map = _get_tile_map(width, height, bw, bh)

    num_pixels = len(py_map)
    needed = num_pixels * 2
    raw = np.frombuffer(data[:needed], dtype=np.uint8)

    alpha_vals = raw[0::2]
    intensity_vals = raw[1::2]

    valid = (py_map < height) & (px_map < width)
    valid_idx = np.where(valid)[0]
    valid_idx = valid_idx[valid_idx < len(alpha_vals)]

    pixels[py_map[valid_idx], px_map[valid_idx], 0] = intensity_vals[valid_idx]
    pixels[py_map[valid_idx], px_map[valid_idx], 1] = intensity_vals[valid_idx]
    pixels[py_map[valid_idx], px_map[valid_idx], 2] = intensity_vals[valid_idx]
    pixels[py_map[valid_idx], px_map[valid_idx], 3] = alpha_vals[valid_idx]
    return pixels


def decode_rgb565(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 4, 4
    py_map, px_map = _get_tile_map(width, height, bw, bh)

    num_pixels = len(py_map)
    needed = num_pixels * 2
    raw = np.frombuffer(data[:needed], dtype=np.dtype('>u2'))

    valid = (py_map < height) & (px_map < width)
    valid_idx = np.where(valid)[0]
    valid_idx = valid_idx[valid_idx < len(raw)]

    vals = raw[valid_idx].astype(np.uint16)
    r, g, b = _rgb565_vec(vals)

    pixels[py_map[valid_idx], px_map[valid_idx], 0] = r
    pixels[py_map[valid_idx], px_map[valid_idx], 1] = g
    pixels[py_map[valid_idx], px_map[valid_idx], 2] = b
    pixels[py_map[valid_idx], px_map[valid_idx], 3] = 255
    return pixels


def decode_rgb5a3(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 4, 4
    py_map, px_map = _get_tile_map(width, height, bw, bh)

    num_pixels = len(py_map)
    needed = num_pixels * 2
    raw = np.frombuffer(data[:needed], dtype=np.dtype('>u2'))

    valid = (py_map < height) & (px_map < width)
    valid_idx = np.where(valid)[0]
    valid_idx = valid_idx[valid_idx < len(raw)]

    vals = raw[valid_idx].astype(np.uint16)

    # Split into opaque (bit15 set) and translucent
    opaque = (vals & 0x8000) != 0

    # RGB555 (opaque)
    r_o = ((vals >> 10) & 0x1F) * 255 // 31
    g_o = ((vals >> 5) & 0x1F) * 255 // 31
    b_o = (vals & 0x1F) * 255 // 31

    # RGB4A3 (translucent)
    a_t = ((vals >> 12) & 0x07) * 255 // 7
    r_t = ((vals >> 8) & 0x0F) * 255 // 15
    g_t = ((vals >> 4) & 0x0F) * 255 // 15
    b_t = (vals & 0x0F) * 255 // 15

    r = np.where(opaque, r_o, r_t).astype(np.uint8)
    g = np.where(opaque, g_o, g_t).astype(np.uint8)
    b = np.where(opaque, b_o, b_t).astype(np.uint8)
    a = np.where(opaque, 255, a_t).astype(np.uint8)

    pixels[py_map[valid_idx], px_map[valid_idx], 0] = r
    pixels[py_map[valid_idx], px_map[valid_idx], 1] = g
    pixels[py_map[valid_idx], px_map[valid_idx], 2] = b
    pixels[py_map[valid_idx], px_map[valid_idx], 3] = a
    return pixels


def decode_rgba32(data, width, height):
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 4, 4
    tiles_x = (width + bw - 1) // bw
    tiles_y = (height + bh - 1) // bh
    total_tiles = tiles_x * tiles_y
    needed = total_tiles * 64

    raw = np.frombuffer(data[:needed], dtype=np.uint8)
    if len(raw) < needed:
        raw = np.pad(raw, (0, needed - len(raw)))

    # Reshape: (num_tiles, 64) -> split into AR (32 bytes) and GB (32 bytes)
    tiles = raw.reshape(total_tiles, 64)
    ar = tiles[:, :32].reshape(total_tiles, 16, 2)  # (tile, pixel, [A,R])
    gb = tiles[:, 32:].reshape(total_tiles, 16, 2)  # (tile, pixel, [G,B])

    # Build coordinate arrays for all tile pixels
    tile_idx = np.arange(total_tiles)
    tile_y = (tile_idx // tiles_x) * bh
    tile_x = (tile_idx % tiles_x) * bw

    # Within each tile: 4x4 pixels in row order
    inner_y = np.arange(4).repeat(4)  # [0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3]
    inner_x = np.tile(np.arange(4), 4)  # [0,1,2,3,0,1,2,3,...]

    # Broadcast to get absolute coordinates
    py_all = (tile_y[:, None] + inner_y[None, :]).ravel()
    px_all = (tile_x[:, None] + inner_x[None, :]).ravel()

    a_all = ar[:, :, 0].ravel()
    r_all = ar[:, :, 1].ravel()
    g_all = gb[:, :, 0].ravel()
    b_all = gb[:, :, 1].ravel()

    valid = (py_all < height) & (px_all < width)
    vi = np.where(valid)[0]

    pixels[py_all[vi], px_all[vi], 0] = r_all[vi]
    pixels[py_all[vi], px_all[vi], 1] = g_all[vi]
    pixels[py_all[vi], px_all[vi], 2] = b_all[vi]
    pixels[py_all[vi], px_all[vi], 3] = a_all[vi]
    return pixels


def decode_cmpr(data, width, height):
    """Decode CMPR (S3TC/DXT1) - vectorized per sub-block."""
    pixels = np.zeros((height, width, 4), dtype=np.uint8)

    tiles_x = (width + 7) // 8
    tiles_y = (height + 7) // 8
    total_sub_blocks = tiles_x * tiles_y * 4
    needed = total_sub_blocks * 8

    raw = data[:needed]
    if len(raw) < needed:
        raw = raw + b'\x00' * (needed - len(raw))
    raw = np.frombuffer(raw, dtype=np.uint8).reshape(total_sub_blocks, 8)

    # Extract c0, c1 as big-endian uint16
    c0 = (raw[:, 0].astype(np.uint16) << 8) | raw[:, 1].astype(np.uint16)
    c1 = (raw[:, 2].astype(np.uint16) << 8) | raw[:, 3].astype(np.uint16)

    # Decode base colors (RGB565)
    r0, g0, b0 = _rgb565_vec(c0)
    r1, g1, b1 = _rgb565_vec(c1)

    # Build 4-color palettes: shape (n, 4, 3+1)
    n = len(c0)
    pal = np.zeros((n, 4, 4), dtype=np.uint8)
    pal[:, 0] = np.stack([r0, g0, b0, np.full(n, 255, dtype=np.uint8)], axis=1)
    pal[:, 1] = np.stack([r1, g1, b1, np.full(n, 255, dtype=np.uint8)], axis=1)

    # Mode: c0 > c1 -> 4-color, else 3-color + transparent
    mode4 = c0 > c1

    # Color 2
    r2_4 = ((2 * r0.astype(np.uint16) + r1.astype(np.uint16)) // 3).astype(np.uint8)
    g2_4 = ((2 * g0.astype(np.uint16) + g1.astype(np.uint16)) // 3).astype(np.uint8)
    b2_4 = ((2 * b0.astype(np.uint16) + b1.astype(np.uint16)) // 3).astype(np.uint8)
    r2_3 = ((r0.astype(np.uint16) + r1.astype(np.uint16)) // 2).astype(np.uint8)
    g2_3 = ((g0.astype(np.uint16) + g1.astype(np.uint16)) // 2).astype(np.uint8)
    b2_3 = ((b0.astype(np.uint16) + b1.astype(np.uint16)) // 2).astype(np.uint8)

    pal[:, 2, 0] = np.where(mode4, r2_4, r2_3)
    pal[:, 2, 1] = np.where(mode4, g2_4, g2_3)
    pal[:, 2, 2] = np.where(mode4, b2_4, b2_3)
    pal[:, 2, 3] = 255

    # Color 3
    r3 = ((r0.astype(np.uint16) + 2 * r1.astype(np.uint16)) // 3).astype(np.uint8)
    g3 = ((g0.astype(np.uint16) + 2 * g1.astype(np.uint16)) // 3).astype(np.uint8)
    b3 = ((b0.astype(np.uint16) + 2 * b1.astype(np.uint16)) // 3).astype(np.uint8)
    pal[:, 3, 0] = np.where(mode4, r3, 0)
    pal[:, 3, 1] = np.where(mode4, g3, 0)
    pal[:, 3, 2] = np.where(mode4, b3, 0)
    pal[:, 3, 3] = np.where(mode4, 255, 0)

    # Extract 2-bit indices: 4 bytes -> 16 pixels
    idx_bytes = (raw[:, 4].astype(np.uint32) << 24) | (raw[:, 5].astype(np.uint32) << 16) | \
                (raw[:, 6].astype(np.uint32) << 8) | raw[:, 7].astype(np.uint32)

    # 16 pixels per sub-block, 2 bits each (MSB first)
    pixel_indices = np.zeros((n, 16), dtype=np.uint8)
    for p in range(16):
        pixel_indices[:, p] = (idx_bytes >> (30 - p * 2)) & 0x03

    # Look up colors: pal[block, index, channel]
    block_range = np.arange(n)[:, None]  # (n, 1)
    rgba = pal[block_range, pixel_indices]  # (n, 16, 4)

    # Compute absolute pixel coordinates for each sub-block pixel
    # Sub-blocks: within each 8x8 tile, 4 sub-blocks in 2x2 arrangement
    block_idx = np.arange(total_sub_blocks)
    tile_idx = block_idx // 4
    sub_idx = block_idx % 4

    tile_row = tile_idx // tiles_x
    tile_col = tile_idx % tiles_x

    sub_row = sub_idx // 2
    sub_col = sub_idx % 2

    base_y = tile_row * 8 + sub_row * 4
    base_x = tile_col * 8 + sub_col * 4

    # Inner pixel positions (4x4 row-major)
    inner_y = np.arange(4).repeat(4)
    inner_x = np.tile(np.arange(4), 4)

    py_all = (base_y[:, None] + inner_y[None, :]).ravel()
    px_all = (base_x[:, None] + inner_x[None, :]).ravel()
    rgba_flat = rgba.reshape(-1, 4)

    valid = (py_all < height) & (px_all < width)
    vi = np.where(valid)[0]

    pixels[py_all[vi], px_all[vi]] = rgba_flat[vi]
    return pixels


def decode_c4(data, width, height, palette):
    """Decode C4 (4-bit palette indexed) - vectorized."""
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 8, 8
    py_map, px_map = _get_tile_map(width, height, bw, bh)

    num_pixels = len(py_map)
    num_bytes = (num_pixels + 1) // 2
    raw = np.frombuffer(data[:num_bytes], dtype=np.uint8)

    high = raw >> 4
    low = raw & 0x0F
    indices = np.empty(len(raw) * 2, dtype=np.uint8)
    indices[0::2] = high
    indices[1::2] = low
    indices = indices[:num_pixels]

    pal_arr = np.array(palette, dtype=np.uint8)

    valid = (py_map < height) & (px_map < width)
    valid_idx = np.where(valid)[0]
    valid_idx = valid_idx[valid_idx < len(indices)]

    pal_idx = indices[valid_idx]
    pal_idx = np.clip(pal_idx, 0, len(pal_arr) - 1)
    pixels[py_map[valid_idx], px_map[valid_idx]] = pal_arr[pal_idx]
    return pixels


def decode_c8(data, width, height, palette):
    """Decode C8 (8-bit palette indexed) - vectorized."""
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    bw, bh = 8, 4
    py_map, px_map = _get_tile_map(width, height, bw, bh)

    num_pixels = len(py_map)
    raw = np.frombuffer(data[:num_pixels], dtype=np.uint8)

    pal_arr = np.array(palette, dtype=np.uint8)

    valid = (py_map < height) & (px_map < width)
    valid_idx = np.where(valid)[0]
    valid_idx = valid_idx[valid_idx < len(raw)]

    pal_idx = raw[valid_idx]
    pal_idx = np.clip(pal_idx, 0, len(pal_arr) - 1)
    pixels[py_map[valid_idx], px_map[valid_idx]] = pal_arr[pal_idx]
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
