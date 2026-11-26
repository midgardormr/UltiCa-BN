"""Check frame-bank conversion without modifying artwork."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('orientation', Path(__file__).parents[1] / 'prepare_bn_orientation.py')
orientation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orientation)


class OrientationTest(unittest.TestCase):
    def convert(self, entries, **metadata):
        with tempfile.TemporaryDirectory(prefix='bn-orientation-') as root:
            path = Path(root) / 'tile_config.json'
            path.write_text(json.dumps({'tiles-new': [{'file': 'sheet.png', 'tiles': entries}], **metadata}))
            settings = orientation.prepare(root)
            return json.loads(path.read_text()), settings

    def test_reverse_banks_keep_connection_ends(self):
        tile = {'id': 'f_row', 'flags': ['ALIGN_TO_TERRAIN'], 'multitile': True,
                'additional_tiles': [{'id': 'edge', 'fg': [1, 2]},
                                     {'id': 'edge_reverse', 'fg': [3, 4]},
                                     {'id': 'end_piece', 'fg': [5, 6, 7, 8]},
                                     {'id': 'end_piece_reverse', 'fg': [9, 10, 11, 12]}]}
        config, settings = self.convert([tile])
        banks = config['tiles-new'][0]['tiles'][0]['additional_tiles']
        self.assertEqual(banks[0]['fg'], [1, 2, 3, 4, 1, 2, 1, 2])
        self.assertEqual(banks[1]['fg'], [5, 6, 7, 8, 9, 10, 11, 12, 5, 6, 7, 8, 5, 6, 7, 8])
        self.assertEqual(settings['furniture']['f_row'], {'rotates_to': 'INDOORFLOOR'})

    def test_static_bindings_are_unchanged(self):
        static = {'id': ['house_07', '2Story02_basement'], 'fg': [1, 2, 3, 4]}
        config, settings = self.convert([static, {'id': 'f_appliance', 'flags': ['ALIGN_TO_TERRAIN']},
                                                {'id': 't_gate', 'flags': ['CONNECT_TO_WALL']}],
                                        vehicle_layered_display=True)
        self.assertEqual(config['tiles-new'][0]['tiles'][0], static)
        self.assertNotIn('vehicle_layered_display', config)
        self.assertEqual(settings['furniture']['f_appliance'], {'connects_to': []})
        self.assertEqual(settings['terrain']['t_gate'], {'connects_to': ['WALL']})

    def test_unsupported_bank_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported rotated bank'):
            self.convert([{'id': 'f_row', 'flags': ['ALIGN_TO_TERRAIN'], 'multitile': True,
                           'additional_tiles': [{'id': 'edge', 'fg': [{'sprite': 1}]},
                                                {'id': 'edge_reverse', 'fg': [2]}]}])
