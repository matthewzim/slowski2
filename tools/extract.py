#!/usr/bin/env python3
"""
We Ski & Snowboard asset extraction toolkit.
Scans ski.dat for known Wii format signatures and extracts/converts game assets.

Usage:
    python extract.py --input ~/Downloads/ski.dat --output ../public/assets/
"""

import argparse
import json
import sys
import os
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scanner import scan_file, decompress_yaz0_files
from brres_parser import BRRESParser, TEX0Parser
from mdl0_parser import MDL0Parser
from tpl_parser import TPLParser
from audio_extractor import BRSTMParser
from gltf_converter import mdl0_to_gltf


def process_brres_files(raw_dir, models_dir, textures_dir):
    """Process extracted BRRES files: parse models and textures."""
    results = {'models': [], 'textures': []}

    for brres_file in sorted(raw_dir.glob('BRRES_*.brres')):
        print(f"\n  Processing {brres_file.name}...")
        try:
            with open(brres_file, 'rb') as f:
                data = f.read()

            parser = BRRESParser(data)
            print(f"    Found {len(parser.sub_files)} sub-files")

            for sf in parser.sub_files:
                if sf['magic'] == 'TEX0' and sf['size']:
                    # Extract and decode texture
                    tex_data = data[sf['offset']:sf['offset'] + sf['size']]
                    try:
                        tex_parser = TEX0Parser(tex_data, parser.endian)
                        decoded = tex_parser.decode_textures()
                        for tex in decoded:
                            try:
                                from PIL import Image
                                img = Image.fromarray(tex['pixels'], 'RGBA')
                                tex_name = f"{sf['name']}_{tex['width']}x{tex['height']}.png"
                                out_path = textures_dir / tex_name
                                img.save(str(out_path))
                                results['textures'].append({
                                    'name': sf['name'],
                                    'file': tex_name,
                                    'width': tex['width'],
                                    'height': tex['height'],
                                    'format': tex['format_name'],
                                })
                                print(f"    Texture: {tex_name} ({tex['format_name']})")
                            except ImportError:
                                print("    Warning: Pillow not installed, skipping texture export")
                    except Exception as e:
                        print(f"    Warning: Failed to parse TEX0 '{sf['name']}': {e}")

                elif sf['magic'] == 'MDL0' and sf['size']:
                    # Extract and convert model
                    mdl_data = data[sf['offset']:sf['offset'] + sf['size']]
                    try:
                        mdl_parser = MDL0Parser(mdl_data, parser.endian)
                        summary = mdl_parser.get_summary()
                        print(f"    Model: {sf['name']} (v{summary['version']}, "
                              f"{summary['total_vertices']} verts, "
                              f"{summary['bones']} bones)")

                        if summary['total_vertices'] > 0:
                            glb_name = f"{sf['name']}.glb"
                            glb_path = models_dir / glb_name
                            if mdl0_to_gltf(mdl_parser, glb_path, textures_dir):
                                results['models'].append({
                                    'name': sf['name'],
                                    'file': glb_name,
                                    'vertices': summary['total_vertices'],
                                    'bones': summary['bones'],
                                })
                    except Exception as e:
                        print(f"    Warning: Failed to parse MDL0 '{sf['name']}': {e}")

        except Exception as e:
            print(f"    Error processing {brres_file.name}: {e}")

    return results


def process_tpl_files(raw_dir, textures_dir):
    """Process extracted TPL texture files."""
    results = []

    for tpl_file in sorted(raw_dir.glob('TPL_*.tpl')):
        print(f"\n  Processing {tpl_file.name}...")
        try:
            with open(tpl_file, 'rb') as f:
                data = f.read()

            parser = TPLParser(data)
            decoded = parser.decode_images()

            for img in decoded:
                try:
                    from PIL import Image
                    pil_img = Image.fromarray(img['pixels'], 'RGBA')
                    tex_name = f"{tpl_file.stem}_img{img['index']}_{img['width']}x{img['height']}.png"
                    out_path = textures_dir / tex_name
                    pil_img.save(str(out_path))
                    results.append({
                        'name': tpl_file.stem,
                        'file': tex_name,
                        'width': img['width'],
                        'height': img['height'],
                        'format': img['format_name'],
                    })
                    print(f"    Image: {tex_name} ({img['format_name']})")
                except ImportError:
                    print("    Warning: Pillow not installed, skipping texture export")
        except Exception as e:
            print(f"    Error processing {tpl_file.name}: {e}")

    return results


def process_audio_files(raw_dir, audio_dir):
    """Process extracted BRSTM audio files."""
    results = []

    for brstm_file in sorted(raw_dir.glob('BRSTM_*.brstm')):
        print(f"\n  Processing {brstm_file.name}...")
        try:
            with open(brstm_file, 'rb') as f:
                data = f.read()

            parser = BRSTMParser(data)
            summary = parser.get_summary()
            print(f"    Audio: {summary['codec']}, {summary['sample_rate']}Hz, "
                  f"{summary['channels']}ch, {summary['duration_seconds']:.1f}s")

            wav_name = f"{brstm_file.stem}.wav"
            wav_path = audio_dir / wav_name
            if parser.save_wav(wav_path):
                results.append({
                    'name': brstm_file.stem,
                    'file': wav_name,
                    **summary,
                })
                print(f"    Saved: {wav_name}")
        except Exception as e:
            print(f"    Error processing {brstm_file.name}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Extract assets from We Ski & Snowboard ski.dat file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
    python extract.py --input ~/Downloads/ski.dat --output ../public/assets/
    python extract.py --input ski.dat --output ./extracted/ --scan-only
        """)

    parser.add_argument('--input', '-i', required=True, help='Path to ski.dat file')
    parser.add_argument('--output', '-o', required=True, help='Output directory for extracted assets')
    parser.add_argument('--scan-only', action='store_true', help='Only scan for signatures, do not convert')
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).resolve()

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Create output directories
    raw_dir = output_dir / 'raw'
    models_dir = output_dir / 'models'
    textures_dir = output_dir / 'textures'
    audio_dir = output_dir / 'audio'

    for d in [raw_dir, models_dir, textures_dir, audio_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Phase 1: Scan for known format signatures
    print("=" * 60)
    print("Phase 1: Scanning for known format signatures")
    print("=" * 60)
    found_assets = scan_file(input_path, output_dir)

    # Phase 2: Decompress any Yaz0 files
    yaz0_count = sum(1 for a in found_assets if a['type'] == 'Yaz0')
    if yaz0_count > 0:
        print(f"\n{'=' * 60}")
        print(f"Phase 2: Decompressing {yaz0_count} Yaz0 files")
        print("=" * 60)
        decompressed = decompress_yaz0_files(output_dir)
        # Re-scan decompressed files for embedded formats
        for dec_file in decompressed:
            print(f"\n  Re-scanning {dec_file.name}...")
            dec_assets = scan_file(dec_file, output_dir)
            found_assets.extend(dec_assets)

    if args.scan_only:
        # Save manifest and exit
        manifest = {'scan_results': found_assets}
        manifest_path = output_dir / 'manifest.json'
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2, default=str)
        print(f"\nScan results saved to {manifest_path}")
        return

    # Phase 3: Process extracted files
    print(f"\n{'=' * 60}")
    print("Phase 3: Processing extracted assets")
    print("=" * 60)

    all_results = {
        'scan_results': found_assets,
        'models': [],
        'textures': [],
        'audio': [],
    }

    # Process BRRES files (models + textures)
    brres_count = sum(1 for a in found_assets if a['type'] == 'BRRES')
    if brres_count > 0:
        print(f"\nProcessing {brres_count} BRRES files...")
        brres_results = process_brres_files(raw_dir, models_dir, textures_dir)
        all_results['models'].extend(brres_results['models'])
        all_results['textures'].extend(brres_results['textures'])

    # Process TPL files (textures)
    tpl_count = sum(1 for a in found_assets if a['type'] == 'TPL')
    if tpl_count > 0:
        print(f"\nProcessing {tpl_count} TPL files...")
        tpl_results = process_tpl_files(raw_dir, textures_dir)
        all_results['textures'].extend(tpl_results)

    # Process BRSTM files (audio)
    brstm_count = sum(1 for a in found_assets if a['type'] == 'BRSTM')
    if brstm_count > 0:
        print(f"\nProcessing {brstm_count} BRSTM files...")
        audio_results = process_audio_files(raw_dir, audio_dir)
        all_results['audio'].extend(audio_results)

    # Save manifest
    manifest_path = output_dir / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    # Summary
    print(f"\n{'=' * 60}")
    print("Extraction Summary")
    print("=" * 60)
    print(f"  Raw files found:  {len(found_assets)}")
    print(f"  Models exported:  {len(all_results['models'])}")
    print(f"  Textures exported: {len(all_results['textures'])}")
    print(f"  Audio exported:   {len(all_results['audio'])}")
    print(f"\n  Output directory: {output_dir}")
    print(f"  Manifest: {manifest_path}")
    print(f"\nDone! Run 'npm run dev' from the project root to view in Three.js.")


if __name__ == '__main__':
    main()
