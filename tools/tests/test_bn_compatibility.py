"""Check that incompatible frame order and metadata changes cannot pass the BN gate."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

spec = importlib.util.spec_from_file_location('bn_guard', Path(__file__).parents[1] / 'check_bn_compatibility.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class CompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bn-guard-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        image = Image.new('RGBA', (128, 32))
        for i, color in enumerate(['red', 'green', 'blue', 'yellow']):
            image.paste(color, (i * 32, 0, i * 32 + 32, 32))
        image.save(self.root / 'sheet.png')
        self.config = {'tile_info': [{'width': 32, 'height': 32}],
                       'tiles-new': [{'file': 'sheet.png', 'tiles': [
                           {'id': 'f_test', 'fg': [0, 1, 2, 3], 'multitile': True,
                            'additional_tiles': [{'id': 'open', 'fg': [3, 2, 1, 0]}]}]}]}
        self.write()
        self.reference = guard.snapshot(self.root)

    def write(self):
        (self.root / 'tile_config.json').write_text(json.dumps(self.config))

    def test_unchanged_and_harmless_json_layout_pass(self):
        (self.root / 'tile_config.json').write_text(json.dumps(self.config, indent=4))
        guard.verify(guard.snapshot(self.root), self.reference)

    def test_atlas_repacking_keeps_the_same_contract(self):
        image = Image.open(self.root / 'sheet.png').convert('RGBA')
        changed = image.copy()
        changed.paste(image.crop((32, 0, 64, 32)), (0, 0))
        changed.paste(image.crop((0, 0, 32, 32)), (32, 0))
        changed.save(self.root / 'sheet.png')
        entry = self.config['tiles-new'][0]['tiles'][0]
        entry['fg'] = [1, 0, 2, 3]
        entry['additional_tiles'][0]['fg'] = [3, 2, 0, 1]
        self.write()
        guard.verify(guard.snapshot(self.root), self.reference)

    def test_tint_mask_change_is_rejected(self):
        self.config['tiles-new'][0]['tiles'][0]['masks'] = [{'type': 'tint', 'fg': 0}]
        self.write()
        with self.assertRaises(ValueError):
            guard.verify(guard.snapshot(self.root), self.reference)

    def test_east_west_swap_is_rejected(self):
        self.config['tiles-new'][0]['tiles'][0]['fg'] = [0, 3, 2, 1]
        self.write()
        with self.assertRaisesRegex(ValueError, 'manual review'):
            guard.verify(guard.snapshot(self.root), self.reference)

    def test_offset_and_open_state_changes_are_rejected(self):
        for kind in ['offset', 'open']:
            with self.subTest(kind=kind):
                sheet = self.config['tiles-new'][0]
                if kind == 'offset':
                    sheet['sprite_offset_y'] = -16
                else:
                    sheet.pop('sprite_offset_y')
                    sheet['tiles'][0]['additional_tiles'][0]['fg'] = [0, 1, 2, 3]
                self.write()
                with self.assertRaises(ValueError):
                    guard.verify(guard.snapshot(self.root), self.reference)

    def test_invalid_sprite_is_rejected(self):
        self.config['tiles-new'][0]['tiles'][0]['fg'] = 99
        self.write()
        with self.assertRaisesRegex(ValueError, 'Out-of-range'):
            guard.snapshot(self.root)

    def test_static_overmap_binding_is_protected(self):
        self.config['tiles-new'][0]['tiles'].append({'id': 'basement', 'fg': 0})
        self.write()
        reference = guard.snapshot(self.root)
        self.config['tiles-new'][0]['tiles'][-1]['fg'] = 1
        self.write()
        with self.assertRaises(ValueError):
            guard.verify(guard.snapshot(self.root), reference)


if __name__ == '__main__':
    unittest.main()
