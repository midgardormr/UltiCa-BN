"""Keep BN's pre-2026-05 vehicle rotation order without contextual vehicle selection."""
import json
import os
from pathlib import Path


def vehicle_ids(source):
    source = Path(source)
    info = json.loads((source / 'tile_info.json').read_text())
    result = set()
    for block in info[1:]:
        for name, props in block.items():
            folder = source / f'pngs_{name[:-4]}_{props.get("sprite_width", 32)}x{props.get("sprite_height", 32)}'
            excluded = {folder / path for path in props.get('exclude', [])}
            for root, dirs, files in os.walk(folder, followlinks=True):
                dirs[:] = [d for d in dirs if Path(root) / d not in excluded
                           and not (Path(root) / d / '.scratch').is_file()]
                for filename in files:
                    path = Path(root) / filename
                    if path.suffix != '.json' or path in excluded:
                        continue
                    if not {'vehicle', 'vehicles'} & set(path.parts):
                        continue
                    value = json.loads(path.read_text())
                    for entry in value if isinstance(value, list) else [value]:
                        ids = entry.get('id', [])
                        result.update(ids if isinstance(ids, list) else [ids])
    return result


def rotate_banks(value, role=None):
    """Mirror E/W slots, including masks and weighted rotation banks, exactly once."""
    if isinstance(value, dict):
        return {key: rotate_banks(child, key) for key, child in value.items()}
    if isinstance(value, list):
        result = [rotate_banks(child, role) for child in value]
        if role in ('fg', 'bg', 'sprite') and len(result) == 4 and all(
                isinstance(child, (str, int)) for child in result):
            result = [result[0], result[3], result[2], result[1]]
        return result
    return value


def prepare(source, output):
    ids = vehicle_ids(source)
    path = Path(output) / 'tile_config.json'
    config = json.loads(path.read_text())
    changed = 0
    for sheet in config['tiles-new']:
        for index, entry in enumerate(sheet.get('tiles', [])):
            keys = entry['id'] if isinstance(entry['id'], list) else [entry['id']]
            if ids.intersection(keys):
                replacement = rotate_banks(entry)
                changed += replacement != entry
                sheet['tiles'][index] = replacement
    path.write_text(json.dumps(config, separators=(',', ':')) + '\n')
    return changed
