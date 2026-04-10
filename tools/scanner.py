"""
Binary file carver: scans large files for known Wii format magic byte signatures.
Uses memory-mapped I/O for efficient scanning of 700MB+ files.
"""

import mmap
import struct
import json
from pathlib import Path

from yaz0_decoder import is_yaz0, decompress as yaz0_decompress


# Magic byte signatures with validation
SIGNATURES = {
    b'bres': {
        'name': 'BRRES',
        'ext': '.brres',
        'desc': '3D model/texture container',
        'size_offset': 8,
        'size_fmt': '>I',
        'max_size': 16_000_000,  # 16MB max -- real BRRES files are typically 1-10MB
        'validate': lambda mm, off: (
            off + 6 <= len(mm) and struct.unpack_from('>H', mm, off + 4)[0] == 0xFEFF
        ),
    },
    b'\x00\x20\xAF\x30': {
        'name': 'TPL',
        'ext': '.tpl',
        'desc': 'Texture palette library',
        'size_offset': None,
        'max_size': 4_000_000,
        'validate': lambda mm, off: (
            off + 12 <= len(mm) and struct.unpack_from('>I', mm, off + 4)[0] < 500
        ),
    },
    b'\x55\xAA\x38\x2D': {
        'name': 'U8',
        'ext': '.arc',
        'desc': 'Nintendo U8 archive',
        'size_offset': 8,
        'size_fmt': '>I',
        'max_size': 32_000_000,
    },
    b'Yaz0': {
        'name': 'Yaz0',
        'ext': '.szs',
        'desc': 'Yaz0 compressed data',
        'size_offset': None,
        'max_size': 16_000_000,
        'validate': lambda mm, off: (
            off + 8 <= len(mm) and 0 < struct.unpack_from('>I', mm, off + 4)[0] < 64_000_000
        ),
    },
    b'RSTM': {
        'name': 'BRSTM',
        'ext': '.brstm',
        'desc': 'Audio stream',
        'size_offset': 8,
        'size_fmt': '>I',
        'max_size': 32_000_000,
        'validate': lambda mm, off: (
            off + 6 <= len(mm) and struct.unpack_from('>H', mm, off + 4)[0] in (0xFEFF, 0xFFFE)
        ),
    },
    b'RSAR': {
        'name': 'BRSAR',
        'ext': '.brsar',
        'desc': 'Sound archive',
        'size_offset': 8,
        'size_fmt': '>I',
        'max_size': 32_000_000,
        'validate': lambda mm, off: (
            off + 6 <= len(mm) and struct.unpack_from('>H', mm, off + 4)[0] in (0xFEFF, 0xFFFE)
        ),
    },
    b'J3D2': {
        'name': 'BMD/BDL',
        'ext': '.bmd',
        'desc': 'J3D model',
        'size_offset': None,
        'max_size': 8_000_000,
    },
    b'REFF': {
        'name': 'BREFF',
        'ext': '.breff',
        'desc': 'Effect file',
        'size_offset': 8,
        'size_fmt': '>I',
        'max_size': 8_000_000,
        'validate': lambda mm, off: (
            off + 6 <= len(mm) and struct.unpack_from('>H', mm, off + 4)[0] in (0xFEFF, 0xFFFE)
        ),
    },
    b'REFT': {
        'name': 'BREFT',
        'ext': '.breft',
        'desc': 'Effect texture',
        'size_offset': 8,
        'size_fmt': '>I',
        'max_size': 8_000_000,
        'validate': lambda mm, off: (
            off + 6 <= len(mm) and struct.unpack_from('>H', mm, off + 4)[0] in (0xFEFF, 0xFFFE)
        ),
    },
}

# BOM-aware signatures
BOM_SIGNATURES = {b'RSTM', b'RSAR', b'REFF', b'REFT'}


def get_file_size(mm, offset, sig_info, magic):
    """Try to determine the size of a found file from its header."""
    if sig_info.get('size_offset') is None:
        return None

    size_pos = offset + sig_info['size_offset']
    fmt = sig_info.get('size_fmt', '>I')
    size_len = struct.calcsize(fmt)

    if size_pos + size_len > len(mm):
        return None

    # Check BOM for endianness
    if magic in BOM_SIGNATURES:
        bom_pos = offset + 4
        if bom_pos + 2 <= len(mm):
            bom = struct.unpack_from('>H', mm, bom_pos)[0]
            if bom == 0xFFFE:
                fmt = fmt.replace('>', '<')

    size = struct.unpack_from(fmt, mm, size_pos)[0]

    # Sanity checks
    max_size = sig_info.get('max_size', 16_000_000)
    if size < 32 or size > max_size:
        return None

    # Verify size doesn't exceed remaining data
    if offset + size > len(mm):
        return None

    return size


def validate_match(mm, offset, sig_info):
    """Run format-specific validation to reject false positives."""
    validator = sig_info.get('validate')
    if validator:
        try:
            return validator(mm, offset)
        except Exception:
            return False
    return True


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

    print(f"Scanning {filepath.name} ({file_size / 1024 / 1024:.1f} MB)...")
    print(f"Looking for {len(SIGNATURES)} format signatures...")

    with open(filepath, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        for magic, sig_info in SIGNATURES.items():
            print(f"  Scanning for {sig_info['name']} ({magic.hex()})...")
            search_pos = 0
            count = 0
            false_positives = 0

            while True:
                pos = mm.find(magic, search_pos)
                if pos == -1:
                    break

                # Validate this isn't a false positive
                if not validate_match(mm, pos, sig_info):
                    false_positives += 1
                    search_pos = pos + 4
                    continue

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
                    # Extract a small sample for inspection (32KB)
                    sample_size = min(32768, len(mm) - pos)
                    filename = f"{sig_info['name']}_{count:04d}_partial{sig_info['ext']}"
                    out_path = raw_dir / filename
                    with open(out_path, 'wb') as out_f:
                        out_f.write(mm[pos:pos + sample_size])
                    asset_info['extracted'] = True
                    asset_info['partial'] = True
                    asset_info['filename'] = filename
                    if size:
                        print(f"    Found at 0x{pos:08X}, claimed size {size:,} (exceeds file) -> {filename} (partial)")
                    else:
                        print(f"    Found at 0x{pos:08X}, size unknown -> {filename} (partial)")

                found_assets.append(asset_info)
                count += 1
                search_pos = pos + max(4, size or 4)

                if progress_callback:
                    progress_callback(search_pos / file_size)

            if count > 0 or false_positives > 0:
                print(f"    Total: {count} valid, {false_positives} rejected")

        mm.close()

    print(f"\nScan complete. Found {len(found_assets)} assets total.")
    return found_assets


def decompress_yaz0_files(output_dir):
    """Find and decompress any Yaz0 files, then re-scan the decompressed data."""
    raw_dir = Path(output_dir) / 'raw'
    decompressed = []

    for yaz0_file in sorted(raw_dir.glob('Yaz0_*')):
        if yaz0_file.suffix == '.dec':
            continue
        try:
            data = yaz0_file.read_bytes()
            if is_yaz0(data):
                dec_data = yaz0_decompress(data)
                dec_path = yaz0_file.with_suffix('.dec')
                dec_path.write_bytes(dec_data)
                decompressed.append(dec_path)
                print(f"  Decompressed {yaz0_file.name} -> {dec_path.name} ({len(dec_data):,} bytes)")
        except Exception as e:
            print(f"  Failed to decompress {yaz0_file.name}: {e}")

    return decompressed
