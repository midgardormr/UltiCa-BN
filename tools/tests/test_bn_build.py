"""Small real pack fixture: atlas indices, named masks, rotations and exclusions."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from check_bn_compatibility import verify, validate_masks
from prepare_bn_tileset import prepare


class PackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='bn-pack-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.output = self.root / 'built'
        self.info = [{'width': 32, 'height': 32, 'pixelscale': 1},
                     {'filler.png': {'filler': True}},
                     {'normal.png': {'exclude': ['excluded.png', 'skip']}}]
        (self.source / 'tile_info.json').write_text(json.dumps(self.info))
        (self.source / 'tileset.txt').write_text('NAME: Fixture\nJSON: tile_config.json\n')
        folder = self.source / 'pngs_normal_32x32' / 'vehicle'
        folder.mkdir(parents=True)
        for i, name in enumerate(['n', 'e', 's', 'w', 'mask']):
            Image.new('RGBA', (32, 32), (i * 30, 127, 127, 255)).save(folder / f'{name}.png')
        Image.new('RGBA', (32, 32)).save(folder.parent / 'excluded.png')
        skipped = folder.parent / 'skip'
        skipped.mkdir()
        (skipped / 'bad.json').write_text('{bad')
        self.entry = {'id': ['vp_test', 'vp_alias'], 'multitile': True,
                      'fg': ['n', 'e', 's', 'w'],
                      'masks': [{'type': 'tint', 'fg': ['mask'] * 4}],
                      'additional_tiles': [{'id': 'broken', 'bg': ['n', 'e', 's', 'w']}]}
        (folder / 'bindings.json').write_text(json.dumps(self.entry))
        filler = self.source / 'pngs_filler_32x32'
        filler.mkdir()
        (filler / 'bindings.json').write_text(json.dumps({'id': ['vp_test', 'vp_alias'], 'fg': 'n'}))
        Image.new('RGBA', (32, 32), (30, 40, 50, 255)).save(folder / 'main_image.png')
        Image.new('RGBA', (32, 32)).save(folder / 'vp_test_broken.png')
        (filler / 'main-image.json').write_text(json.dumps({'id': 'main_image', 'fg': 'e', 'bg': 'w'}))
        # Execute the shebang too: CI depends on its executable mode.
        env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'])
        subprocess.run([str(TOOLS / 'compose.py'), '--use-all', '--feedback', 'CONCISE',
                        str(self.source), str(self.output)], env=env, check=True,
                       capture_output=True)
        Image.new('RGBA', (512, 256)).save(self.output / 'fallback.png')
        prepare(self.source, self.output)
        self.policy = {'required_bindings': {'shared': ['vp_test', 'vp_alias']},
                       'directions': [{'id': 'vp_test', 'frames': ['n', 'w', 's', 'e']}]}

    def check(self):
        return verify('UltimateCataclysm', self.source, self.output, self.policy)

    def mutate(self, change):
        path = self.output / 'tile_config.json'
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def test_build(self):
        self.check()
        verify('UltimateCataclysm', self.source, self.output)
        policy = self.root / 'local-policy.json'
        policy.write_text(json.dumps({'schema': 3, **self.policy}))
        for extra in ([], ['--policy', str(policy)]):
            subprocess.run([sys.executable, str(TOOLS / 'check_bn_compatibility.py'),
                            'UltimateCataclysm', str(self.output), '--source', str(self.source),
                            *extra], check=True, capture_output=True)
        config = json.loads((self.output / 'tile_config.json').read_text())
        self.assertEqual(config['tiles-new'][0]['file'], 'normal.png')
        ids = [e['id'] for s in config['tiles-new'] for e in s.get('tiles', [])]
        self.assertNotIn('excluded', ids)
        self.assertEqual(sum('vp_test' in ([e] if isinstance(e, str) else e) for e in ids), 1)

    def test_wrong_direction_rejected(self):
        self.mutate(lambda data: data['tiles-new'][0]['tiles'][0]['fg'].reverse())
        with self.assertRaisesRegex(ValueError, 'bindings differ|direction'):
            self.check()

    def test_missing_mask_rejected(self):
        self.mutate(lambda data: data['tiles-new'][0]['tiles'][0].pop('masks'))
        with self.assertRaisesRegex(ValueError, 'bindings differ'):
            self.check()

    def test_wrong_anchor_rejected(self):
        self.mutate(lambda data: data['tiles-new'][0].update(sprite_offset_x=1))
        with self.assertRaisesRegex(ValueError, 'bindings differ'):
            self.check()

    def test_bad_mask_bank_rejected(self):
        entry = copy.deepcopy(self.entry)
        entry['masks'][0]['fg'] = ['mask'] * 2
        with self.assertRaisesRegex(ValueError, 'Mask does not match'):
            validate_masks(entry, 'vp_test')

    def test_context_metadata_rejected(self):
        entry = {**self.entry, 'vehicle_context': 'body'}
        with self.assertRaisesRegex(ValueError, 'Contextual vehicle'):
            validate_masks(entry, 'vp_test')


if __name__ == '__main__':
    unittest.main()
