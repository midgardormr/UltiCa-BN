"""Check the BN graphics contract after composing a pack."""
import argparse
import hashlib
import json
from pathlib import Path

import pyvips


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def snapshot(root):
    config = json.loads((root / 'tile_config.json').read_text())
    info = config['tile_info'][0]
    frames, entries, offsets = {}, {}, {}
    offset = 0
    for sheet in config['tiles-new']:
        image = pyvips.Image.new_from_file(str(root / sheet['file']), access='random', revalidate=True)
        image = image.colourspace('srgb')
        if not image.hasalpha():
            image = image.addalpha()
        width = sheet.get('sprite_width', info['width'])
        height = sheet.get('sprite_height', info['height'])
        across, down = image.width // width, image.height // height
        if image.width % width or image.height % height:
            raise ValueError(f"Non-integral sheet: {sheet['file']}")
        placement = [width, height, sheet.get('sprite_offset_x', 0), sheet.get('sprite_offset_y', 0),
                     sheet.get('sprite_offset_x_retracted', sheet.get('sprite_offset_x', 0)),
                     sheet.get('sprite_offset_y_retracted', sheet.get('sprite_offset_y', 0)),
                     sheet.get('pixelscale', 1)]
        # Read one atlas row at a time; large generated sheets need not fit in RAM.
        for row in range(down):
            pixels = bytes(image.crop(0, row * height, image.width, height).write_to_memory())
            stride = image.width * 4
            for column in range(across):
                frame = b''.join(pixels[y * stride + column * width * 4:
                                       y * stride + (column + 1) * width * 4]
                                 for y in range(height))
                frames[offset + row * across + column] = [placement, hashlib.sha256(frame).hexdigest()]
        for entry in sheet.get('tiles', []):
            for name in entry['id'] if isinstance(entry['id'], list) else [entry['id']]:
                if name in entries:
                    raise ValueError(f'Duplicate binding: {name}')
                entries[name], offsets[name] = entry, placement
        offset += across * down

    def normalize(value, key=None):
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items() if not k.startswith('//')}
        if isinstance(value, list):
            return [normalize(v, key) for v in value]
        if isinstance(value, int) and not isinstance(value, bool) and key in ('fg', 'bg', 'sprite') and value >= 0:
            if value not in frames:
                raise ValueError(f'Out-of-range sprite: {value}')
            return frames[value]
        return value

    for name, entry in entries.items():
        normalize(entry)
    # Protect every binding, including static overmap and basement entries.
    protected = {name: digest([offsets[name], normalize(entry)])
                 for name, entry in entries.items()}
    protected['$tile_info'] = digest(info)
    orientation = root / 'BN_ORIENTATION.json'
    if orientation.exists():
        protected['$orientation'] = digest(json.loads(orientation.read_text()))
    return protected


def verify(actual, expected):
    changed = sorted(name for name in actual.keys() | expected.keys() if actual.get(name) != expected.get(name))
    if changed:
        raise ValueError('BN graphics contract changed; manual review required: ' + ', '.join(changed[:30]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', choices=('UltimateCataclysm', 'Chibi_Ultica', 'Altica'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--contract', type=Path, default=Path(__file__).with_name('bn-compatibility.json'))
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    if contract.get('schema') != 2:
        raise ValueError('Unsupported BN contract schema')
    actual = snapshot(args.root)
    verify(actual, contract['packs'][args.pack])
    receipt = {'schema': 2, 'contract_sha256': hashlib.sha256(args.contract.read_bytes()).hexdigest(),
               'pack': args.pack, 'protected_bindings': len(actual), 'bn_pr': contract['bn_pr'],
               'stock_reference': contract['stock_reference'], 'renderer_features': ['rotates_to']}
    config = json.loads((args.root / 'tile_config.json').read_text())
    files = {'tile_config.json', 'tileset.txt', 'layering.json', 'BN_ORIENTATION.json'} | {s['file'] for s in config['tiles-new']}
    receipt['files'] = {name: hashlib.sha256((args.root / name).read_bytes()).hexdigest()
                        for name in sorted(files)}
    (args.root / 'BN_COMPATIBILITY.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'{args.pack}: {len(actual)} BN bindings verified')


if __name__ == '__main__':
    main()
