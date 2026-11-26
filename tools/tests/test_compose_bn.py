"""Exercise BN metadata and override precedence through a real composition."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pyvips


class ComposeMetadataTest(unittest.TestCase):
    def test_masks_states_and_multiple_overridden_ids(self):
        self.check_composition("UltimateCataclysm")

    def test_other_pack_keeps_legacy_metadata_behavior(self):
        self.check_composition("MSX++")

    def check_composition(self, name):
        composer = Path(os.environ.get(
            'COMPOSE_TEST_SCRIPT', Path(__file__).resolve().parents[1] / 'compose.py'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            primary = source / 'pngs_primary_32x32'
            filler = source / 'pngs_legacy_32x32'
            primary.mkdir(parents=True)
            filler.mkdir()
            (source / 'tileset.txt').write_text(f'# fixture\nVIEW: renamed test directory\nNAME: {name}\nJSON: tile_config.json\n')
            (source / 'tile_info.json').write_text(json.dumps([
                {'width': 32, 'height': 32, 'vehicle_layered_display': True},
                {'legacy.png': {'filler': True, 'exclude': ['withdrawn.json']}},
                {'primary.png': {}},
            ]))
            if name != 'UltimateCataclysm':
                info = json.loads((source / 'tile_info.json').read_text())
                info[1:] = reversed(info[1:])
                (source / 'tile_info.json').write_text(json.dumps(info))
            for directory, sprite_name, color in [
                (primary, 'new_sprite', [255, 0, 0, 255]),
                (primary, 'mask_sprite', [255, 255, 255, 255]),
                (filler, 'old_sprite', [0, 255, 0, 255]),
            ]:
                pyvips.Image.black(32, 32, bands=4).new_from_image(color).pngsave(
                    str(directory / (sprite_name + '.png')))
            (primary / 'entries.json').write_text(json.dumps({
                'id': ['test_one', 'test_two'], 'fg': 'new_sprite',
                'multitile': True, 'masks': [{'type': 'tint', 'fg': 'mask_sprite'}],
                'additional_tiles': [{
                    'id': 'open', 'fg': 'old_sprite',
                    'masks': [{'type': 'tint', 'fg': ['mask_sprite'] * 4}],
                }],
            }))
            (filler / 'entries.json').write_text(json.dumps({
                'id': ['test_one', 'test_two', 'test_three'], 'fg': 'old_sprite',
            }))
            (filler / 'withdrawn.json').write_text(json.dumps({
                'id': 'withdrawn_alias', 'fg': 'old_sprite',
            }))
            output = root / 'output'
            result = subprocess.run([
                sys.executable, str(composer), '--feedback', 'CONCISE',
                '--no-use-all', str(source), str(output),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads((output / 'tile_config.json').read_text())
            if name != 'UltimateCataclysm':
                self.assertNotIn('vehicle_layered_display', data['tile_info'][0])
                entries = [entry for sheet in data['tiles-new'] for entry in sheet['tiles']]
                self.assertTrue(any(entry['id'] == 'withdrawn_alias' for entry in entries))
                self.assertEqual(entries[0]['masks'][0]['fg'], 'mask_sprite')
                return
            self.assertTrue(data['tile_info'][0]['vehicle_layered_display'])
            self.assertEqual([s['file'] for s in data['tiles-new']], ['primary.png', 'legacy.png', 'fallback.png'])
            entries = {}
            for sheet in data['tiles-new']:
                for entry in sheet['tiles']:
                    names = entry['id'] if isinstance(entry['id'], list) else [entry['id']]
                    for name in names:
                        self.assertNotIn(name, entries, 'duplicate binding survived composition')
                        entries[name] = entry
            self.assertEqual(set(entries), {'test_one', 'test_two', 'test_three'})
            self.assertEqual(entries['test_one'], entries['test_two'])
            top = entries['test_one']
            self.assertNotEqual(top['fg'], entries['test_three']['fg'])
            self.assertIsInstance(top['masks'][0]['fg'], int)
            state = top['additional_tiles'][0]
            self.assertEqual(state['fg'], entries['test_three']['fg'])
            self.assertEqual(state['masks'][0]['fg'], [top['masks'][0]['fg']] * 4)


if __name__ == '__main__':
    unittest.main()
