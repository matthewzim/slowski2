"""
Binary file carver: scans large files for known Wii format magic byte signatures.
Uses memory-mapped I/O for efficient scanning of 700MB+ files.
"""

import mmap
import struct
import os
import json
from pathlib import Path

from yaz0_decoder import is_yaz0, decompress as yaz0_decompress


# Magic byte signatures to search for
SIGNATURES = {
    b'bres': {
        'name': 'BRRES',
        'ext': '.brres',
        'desc': '3D model/texture container',
        'size_offset': 8,  # File size at offset 8 from magic
        'size_fmt': '>I',
    },
    b'\x00\x20\xAF\x30': {
        'name': 'TPL',
        'ext': '.tpl',
        'desc': 'Texture palette library',
        'size_offset': None,  # Need to calculate from header
    },
    b'\x55\xAA\x38\x2D': {
        'name': 'U8',
        'ext': '.arc',
        'desc': 'Nintendo U8 archive',
        'size_offset': 8,
        'size_fmt': '>I',
    },
    b'Yaz0': {
        'name': 'Yaz0',
        'ext': '.szs',
        'desc': 'Yaz0 compressed data',
        'size_offset': 4,
        'size_fmt': '>I',
        'add_header': True,  # Size is decompressed size, need actual compressed size
    },
    b'RSTM': {
        'name': 'BRSTM',
        'ext': '.brstm',
        'desc': 'Audio stream',
        'size_offset': 8,
        'size_fmt': '>I',
    },
    b'RSAR': {
        'name': 'BRSAR',
        'ext': '.brsar',
        'desc': 'Sound archive',
        'size_offset': 8,
        'size_fmt': '>I',
    },
    b'J3D2': {
        'name': 'BMD/BDL',
        'ext': '.bmd',
        'desc': 'J3D model',
        'size_offset': None,
    },
    b'REFF': {
        'name': 'BREFF',
        'ext': '.breff',
        'desc': 'Effect file',
        'size_offset': 8,
        'size_fmt': '>I',
    },
    b'REFT': {
        'name': 'BREFT',
        'ext': '.breft',
        'desc': 'Effect texture',
        'size_offset': 8,
        'size_fmt': '>I',
    },
}

# BOM-aware signatures (these have a 2-byte BOM after the magic)
BOM_SIGNATURES = {b'RSTM', b'RSAR', b'REFF', b'REFT'}


def get_file_size(mm, offset, sig_info, magic):
    """Try to determine the size of a found file from its header."""
    if sig_info.get('size_offset') is None:
        return None

    size_pos = offset + sig_info['size_offset']
    fmt = sig_info['size_fmt']
    size_len = struct.calcsize(fmt)

    if size_pos + size_len > len(mm):
        return None

    # For BOM-aware formats, check BOM to determine endianness
    if magic in BOM_SIGNATURES:
        bom_pos = offset + 4
        if bom_pos + 2 <= len(mm):
            bom = struct.unpack_from('>H', mm, bom_pos)[0]
            if bom == 0xFFFE:
                fmt = fmt.replace('>', '<')  # Little-endian

    size = struct.unpack_from(fmt, mm, size_pos)[0]

    # For BRRES, the size field includes the header
    if magic == b'bres':
        pass  # Size is total file size

    # Sanity check
    if size < 16 or size > 100_000_000:  # 100MB max per file
        return None

    # For Yaz0, we store the header + some padding to find compressed size
    if magic == b'Yaz0':
        # Yaz0 doesn't store compressed size - scan for next magic or use heuristic
        return None

    return size


def scan_file(filepath, output_dir, progress_callback=None):
    """
    Scan a binary file for known format signatures.
    Returns a list of found assets.
    """
    filepath = Path(filepath)
    output_dir = Path(output_dir)
    raw_dir = output_dir / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)

    file_size = filepath.stat().st_size
    found_assets = []
    magic_bytes_list = list(SIGNATURES.keys())

    print(f"Scanning {filepath.name} ({file_size / 1024 / 1024:.1f} MB)...")
    print(f"Looking for {len(SIGNATURES)} format signatures...")

    with open(filepath, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        for magic, sig_info in SIGNATURES.items():
            print(f"  Scanning for {sig_info['name']} ({magic.hex()})...")
            search_pos = 0
            count = 0

            while True:
                pos = mm.find(magic, search_pos)
                if pos == -1:
                    break

                # Try to determine file size
                size = get_file_size(mm, pos, sig_info, magic)

                asset_info = {
                    'type': sig_info['name'],
                    'offset': pos,
                    'offset_hex': f'0x{pos:08X}',
                    'size': size,
                    'description': sig_info['desc'],
                }

                # Extract the file if we know its size
                if size and pos + size <= len(mm):
                    filename = f"{sig_info['name']}_{count:04d}{sig_info['ext']}"
                    out_path = raw_dir / filename
                    with open(out_path, 'wb') as out_f:
                        out_f.write(mm[pos:pos + size])
                    asset_info['extracted'] = True
                    asset_info['filename'] = filename
                    print(f"    Found at 0x{pos:08X}, size {size:,} bytes -> {filename}")
                else:
                    # Try a default extraction size (64KB) for unknown sizes
                    default_size = min(65536, len(mm) - pos)
                    filename = f"{sig_info['name']}_{count:04d}_partial{sig_info['ext']}"
                    out_path = raw_dir / filename
                    with open(out_path, 'wb') as out_f:
                        out_f.write(mm[pos:pos + default_size])
                    asset_info['extracted'] = True
                    asset_info['partial'] = True
                    asset_info['filename'] = filename
                    print(f"    Found at 0x{pos:08X}, size unknown -> {filename} (partial)")

                found_assets.append(asset_info)
                count += 1
                search_pos = pos + max(4, size or 4)

                if progress_callback:
                    progress_callback(search_pos / file_size)

            if count > 0:
                print(f"    Total: {count} {sig_info['name']} file(s)")

        mm.close()

    print(f"\nScan complete. Found {len(found_assets)} assets total.")
    return found_assets


def decompress_yaz0_files(output_dir):
    """Find and decompress any Yaz0 files, then re-scan the decompressed data."""
    raw_dir = Path(output_dir) / 'raw'
    decompressed = []

    for yaz0_file in raw_dir.glob('Yaz0_*'):
        try:
            with open(yaz0_file, 'rb') as f:
                data = f.read()
            if is_yaz0(data):
                dec_data = yaz0_decompress(data)
                dec_path = yaz0_file.with_suffix('.dec')
                with open(dec_path, 'wb') as f:
                    f.write(dec_data)
                decompressed.append(dec_path)
                print(f"  Decompressed {yaz0_file.name} -> {dec_path.name} ({len(dec_data):,} bytes)")
        except Exception as e:
            print(f"  Failed to decompress {yaz0_file.name}: {e}")

    return decompressed
