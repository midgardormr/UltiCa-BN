"""Check compiled frames/states/masks against source, plus a small BN direction policy."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import pyvips
from prepare_bn_tileset import rotate_banks, vehicle_ids


def load_image(path):
    image = pyvips.Image.pngload(str(path))
    if image.interpretation != 'srgb':
        image = image.colourspace('srgb')
    if not image.hasalpha():
        image = image.addalpha()
    if image.get_typeof('icc-profile-data'):
        image = image.icc_transform('srgb')
    return image


def placement(props, width=32, height=32):
    x, y = props.get('sprite_offset_x', 0), props.get('sprite_offset_y', 0)
    return [props.get('sprite_width', width), props.get('sprite_height', height), x, y,
            props.get('sprite_offset_x_retracted', x), props.get('sprite_offset_y_retracted', y),
            props.get('pixelscale', 1)]


def descriptor(image, position):
    return [position, hashlib.sha256(bytes(image.write_to_memory())).hexdigest()]


def source_catalog(source):
    info = json.loads((source / 'tile_info.json').read_text())
    images, main_entries, filler_entries, main_images = {}, {}, {}, set()
    sheets = [(name, props) for block in info[1:] for name, props in block.items()]
    for name, props in sorted(sheets, key=lambda sheet: sheet[1].get('filler', False)):
        if props.get('fallback'):
            continue
        pos = placement(props, info[0]['width'], info[0]['height'])
        folder = source / f'pngs_{name[:-4]}_{pos[0]}x{pos[1]}'
        excluded = {folder / path for path in props.get('exclude', [])}
        def files_in_sheet():
            for root, dirs, files in os.walk(folder, followlinks=True):
                dirs[:] = sorted(d for d in dirs if Path(root) / d not in excluded
                                 and not (Path(root) / d / '.scratch').is_file())
                yield root, files
        for root, files in sorted(files_in_sheet()):
            for filename in sorted(files):
                path = Path(root) / filename
                if path in excluded:
                    continue
                if path.suffixes == ['.png'] and path.stem not in images:
                    image = load_image(path)
                    if (image.width, image.height) != tuple(pos[:2]):
                        raise ValueError(f'Wrong source canvas: {path}')
                    images[path.stem] = descriptor(image, pos)
                    if not props.get('filler'):
                        main_images.add(path.stem)
                elif path.suffixes == ['.json']:
                    value = json.loads(path.read_text())
                    for entry in value if isinstance(value, list) else [value]:
                        names = entry['id'] if isinstance(entry['id'], list) else [entry['id']]
                        for ident in names:
                            bank = filler_entries if props.get('filler') else main_entries
                            bank.setdefault(ident, entry)
    # --use-all creates unused main-image IDs before processing fallback JSON.
    # A main PNG therefore wins over a filler binding with the same ID.
    def references(value, role=None):
        if isinstance(value, dict):
            return set().union(*(references(v, k) for k, v in value.items()))
        if isinstance(value, list):
            return set().union(*(references(v, role) for v in value))
        return {value} if role in ('fg', 'bg', 'sprite') and isinstance(value, str) else set()
    def state_ids(entry, prefix=''):
        ids = entry['id'] if isinstance(entry['id'], list) else [entry['id']]
        result = {prefix + ident for ident in ids}
        for child in entry.get('additional_tiles', []):
            result.update(state_ids(child, prefix + ids[0] + '_'))
        return result
    reserved = set().union(*(state_ids(e) for e in main_entries.values()))
    used = references(list(main_entries.values()))
    entries = dict(main_entries)
    for name in sorted(main_images - used - reserved):
        entries[name] = {'id': name, 'fg': name}
    for ident, entry in filler_entries.items():
        if ident not in reserved:
            entries.setdefault(ident, entry)
    return info[0], images, entries


def built_catalog(root):
    config = json.loads((root / 'tile_config.json').read_text())
    frames, entries, offset = {}, {}, 0
    width, height = config['tile_info'][0]['width'], config['tile_info'][0]['height']
    for sheet in config['tiles-new']:
        image = load_image(root / sheet['file'])
        pos = placement(sheet, width, height)
        w, h = pos[:2]
        if image.width % w or image.height % h:
            raise ValueError(f"Non-integral atlas: {sheet['file']}")
        across, down = image.width // w, image.height // h
        for y in range(down):
            row = bytes(image.crop(0, y * h, image.width, h).write_to_memory())
            stride = image.width * 4
            for x in range(across):
                pixels = b''.join(row[r * stride + x * w * 4:r * stride + (x + 1) * w * 4]
                                  for r in range(h))
                frames[offset + y * across + x] = [pos, hashlib.sha256(pixels).hexdigest()]
        for entry in sheet.get('tiles', []):
            for ident in entry['id'] if isinstance(entry['id'], list) else [entry['id']]:
                if ident in entries:
                    raise ValueError(f'Duplicate compiled ID: {ident}')
                entries[ident] = entry
        offset += across * down
    return config['tile_info'][0], frames, entries


def normalize(value, frames, source=False, role=None):
    if isinstance(value, dict):
        result = {key: normalize(child, frames, source, key) for key, child in value.items()
                  if not key.startswith('//')}
        return {key: child for key, child in result.items()
                if not (key in ('fg', 'bg') and child in ('', []))}
    if isinstance(value, list):
        result = [normalize(child, frames, source, role) for child in value
                  if not (source and role in ('fg', 'bg', 'sprite') and child == '')]
        return result[0] if len(result) == 1 and role in ('fg', 'bg', 'sprite') else result
    if source and role in ('fg', 'bg', 'sprite') and value == '':
        return ''
    if role in ('fg', 'bg', 'sprite'):
        if value not in frames:
            raise ValueError(f'{"Missing source sprite" if source else "Invalid sprite index"}: {value}')
        return frames[value]
    return value


def without_id(entry):
    return {key: value for key, value in entry.items() if key != 'id'}


def mask_layout(value):
    if isinstance(value, str):
        return [(1, 1)]
    if isinstance(value, list) and all(isinstance(child, str) for child in value):
        return [(1, len(value))]
    if isinstance(value, list):
        return [(child.get('weight', 1), len(child['sprite']) if isinstance(child['sprite'], list) else 1)
                for child in value]
    return []


def validate_masks(entry, ident):
    if any(key.startswith('vehicle_') for key in entry):
        raise ValueError(f'Contextual vehicle metadata is outside this pack: {ident}')
    for mask in entry.get('masks', []):
        if mask.get('type') != 'tint':
            raise ValueError(f'Unsupported mask type: {ident}')
        for layer in ('fg', 'bg'):
            if layer in mask and mask_layout(mask[layer]) != mask_layout(entry.get(layer)):
                raise ValueError(f'Mask does not match sprite bank: {ident}.{layer}')
    for child in entry.get('additional_tiles', []):
        validate_masks(child, ident + ':' + child['id'])


def verify(pack, source, root, contract=None):
    contract = contract or {"required_bindings": {}, "directions": []}
    source_info, images, expected = source_catalog(source)
    info, frames, actual = built_catalog(root)
    defaults = {'zlevel_height': 0, 'iso': False, 'retract_dist_min': -1.0, 'retract_dist_max': 1.0}
    if info != {**defaults, **source_info}:
        raise ValueError('Root tileset metadata differs from source')
    vehicles = vehicle_ids(source)
    differences = []
    for ident, entry in expected.items():
        validate_masks(entry, ident)
        expected_entry = rotate_banks(entry) if ident in vehicles else entry
        if ident not in actual or normalize(without_id(expected_entry), images, True) != normalize(
                without_id(actual[ident]), frames):
            differences.append(ident)
    for ident, entry in actual.items():
        normalize(entry, frames)
        if ident not in expected and ident in images and normalize(entry['fg'], frames, role='fg') != images[ident]:
            differences.append(ident)
    if differences:
        raise ValueError('Source/compiled bindings differ: ' + ', '.join(differences[:30]))
    required = contract['required_bindings'].get('shared', []) + contract['required_bindings'].get(pack, [])
    missing = sorted(set(required) - actual.keys())
    if missing:
        raise ValueError('Required BN bindings missing: ' + ', '.join(missing))
    for check in contract['directions']:
        entry = actual[check['id']]
        if check.get('state'):
            entry = next(child for child in entry['additional_tiles'] if child['id'] == check['state'])
        observed = normalize(entry[check.get('layer', 'fg')], frames, role='fg')
        reference = [images[name] for name in check['frames']]
        if observed != reference:
            raise ValueError(f"BN direction convention changed: {check['id']} ({check.get('state', 'base')})")
    print(f'{pack}: {len(expected)} source bindings, {len(actual)} compiled IDs, '
          f'{len(images)} source frames and {len(contract["directions"])} direction checks passed')
    return {'source_bindings': len(expected), 'compiled_ids': len(actual), 'source_frames': len(images)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', choices=('UltimateCataclysm', 'Chibi_Ultica', 'Altica'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--policy', type=Path, help='Optional external BN compatibility policy')
    args = parser.parse_args()
    source = args.source or Path(__file__).resolve().parents[1] / 'gfx' / args.pack
    contract = None
    if args.policy:
        contract = json.loads(args.policy.read_text())
        if contract.get('schema') != 3:
            raise ValueError('Unsupported BN compatibility policy')
    verify(args.pack, source, args.root, contract)


if __name__ == '__main__':
    main()
