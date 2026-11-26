"""Adapt existing BN artwork to generic connection/rotation data without repainting it."""
import json
from pathlib import Path


def prepare(root):
    path = Path(root) / 'tile_config.json'
    config = json.loads(path.read_text())
    settings = {'furniture': {}, 'terrain': {}}
    def discard_legacy(value):
        if isinstance(value, dict):
            for key in list(value):
                if key.startswith('vehicle_'):
                    del value[key]
                else:
                    discard_legacy(value[key])
        elif isinstance(value, list):
            for child in value:
                discard_legacy(child)
    discard_legacy(config)
    for sheet in config['tiles-new']:
        for tile in sheet.get('tiles', []):
            flags = tile.get('flags', [])
            ids = tile['id'] if isinstance(tile['id'], list) else [tile['id']]
            if 'ALIGN_TO_TERRAIN' in flags:
                children = {entry['id']: entry for entry in tile.get('additional_tiles', [])}
                if not tile.get('multitile', False):
                    for key in ids:
                        settings['furniture'][key] = {'connects_to': []}
                elif any(key.endswith('_reverse') for key in children):
                    for key in ids:
                        settings['furniture'][key] = {'rotates_to': 'INDOORFLOOR'}
                    for kind in ('edge', 'end_piece'):
                        normal, reverse = children.get(kind), children.get(kind + '_reverse')
                        if not normal or not reverse:
                            continue
                        count = 2 if kind == 'edge' else 4
                        for member in ('fg', 'bg', 'fg_tint_mask', 'bg_tint_mask'):
                            if member not in normal or member not in reverse:
                                continue
                            front, back = normal[member], reverse[member]
                            if not (isinstance(front, list) and isinstance(back, list)
                                    and front and back and all(isinstance(i, int) for i in front + back)):
                                raise ValueError(f'Unsupported rotated bank: {ids}.{kind}.{member}')
                            normal[member] = [bank[i % len(bank)] for bank in (front, back, front, front)
                                              for i in range(count)]
                    tile['additional_tiles'] = [entry for entry in tile['additional_tiles']
                                                if not entry['id'].endswith('_reverse')]
            if 'CONNECT_TO_WALL' in flags:
                for key in ids:
                    settings['terrain'][key.split('_season_', 1)[0]] = {'connects_to': ['WALL']}
            if 'flags' in tile:
                tile['flags'] = [flag for flag in flags if flag not in ('ALIGN_TO_TERRAIN', 'CONNECT_TO_WALL')]
                if not tile['flags']:
                    del tile['flags']
    path.write_text(json.dumps(config, separators=(',', ':')) + '\n')
    (Path(root) / 'BN_ORIENTATION.json').write_text(json.dumps(settings, sort_keys=True, indent=2) + '\n')
    return settings
