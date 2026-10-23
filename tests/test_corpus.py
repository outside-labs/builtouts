from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import runpy
import tracemalloc
import unittest

from builtouts.html import Document, DocumentParser, Field, LinkCollector, ParseLimitError, TextCollector, extract_all

ROOT = Path(__file__).resolve().parents[1]


class CorpusTests(unittest.TestCase):
    def test_synthetic_corpus_whole_and_chunked_equivalence(self):
        corpus = json.loads((ROOT / 'tests/fixtures/html-corpus.json').read_text(encoding='utf-8'))
        self.assertEqual(corpus['license'], 'MIT')
        for case in corpus['cases']:
            source = case['html']
            whole = Document.from_html(source)
            for size in (1, 2, 7, len(source)):
                with self.subTest(case=case['name'], chunk=size):
                    tree, links, text = DocumentParser(), LinkCollector(), TextCollector()
                    for offset in range(0, len(source), size):
                        for parser in (tree, links, text):
                            parser.feed(source[offset:offset + size])
                    for parser in (tree, links, text):
                        parser.close()
                    doc = tree.document
                    self.assertEqual(doc.text, case['text'])
                    self.assertEqual(text.text, case['text'])
                    self.assertEqual(doc.title, case['title'])
                    self.assertEqual([(link.href, link.text) for link in links.links],
                                     [tuple(link) for link in case['links']])
                    for selector, expected in case['selectors'].items():
                        self.assertEqual([node.text for node in doc.select(selector)], expected)
                    self.assertEqual([(node.kind, node.tag, node.data, dict(node.attrs)) for node in doc.descendants()],
                                     [(node.kind, node.tag, node.data, dict(node.attrs)) for node in whole.descendants()])
                    if 'records' in case:
                        self.assertEqual(extract_all(doc, 'article', {
                            'id': Field(attribute='data-id', convert=int), 'title': Field('h2'),
                        }), case['records'])

    def test_adversarial_limits_invalidate_all_parser_modes(self):
        for cls in (DocumentParser, LinkCollector, TextCollector):
            for source, limits in [('<x>' * 1000, {'max_depth': 32}),
                                   ('<br>' * 1000, {'max_nodes': 32}),
                                   ('x' * 1000, {'max_chars': 32})]:
                parser = cls(**limits)
                with self.subTest(parser=cls, limits=limits), self.assertRaises(ParseLimitError):
                    parser.feed(source)
                with self.assertRaises(RuntimeError):
                    parser.feed('more')

    def test_offline_end_to_end_example(self):
        output = io.StringIO()
        with redirect_stdout(output):
            runpy.run_path(str(ROOT / 'examples/scrape_pipeline.py'), run_name='__main__')
        self.assertIn('2 successes, 1 explicit field failure', output.getvalue())

    def test_diagnostic_samples_and_input_bounds(self):
        spec = importlib.util.spec_from_file_location('extraction_diagnostic', ROOT / 'scripts/profile_extraction.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = module.profile(records=10, iterations=2)
        self.assertEqual(report['workload']['records'], 10)
        self.assertEqual(len(report['samples']), 2)
        self.assertIn('python', report['environment'])
        for sample in report['samples']:
            self.assertEqual(sample['records'], 10)
            self.assertGreaterEqual(sample['elapsed_seconds'], 0)
            self.assertGreater(sample['traced_peak_bytes'], 0)
        self.assertFalse(tracemalloc.is_tracing())
        for values in ((0, 1), (10001, 1), (1, 21), (True, 1)):
            with self.assertRaises((ValueError, TypeError)):
                module.profile(*values)

    def test_distribution_readme_metadata_is_utf8(self):
        spec = importlib.util.spec_from_file_location('distribution_checker', ROOT / 'scripts/check_distribution.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        readme = 'Café — 日本語\n'.encode('utf-8')
        metadata = ('Metadata-Version: 2.4\nName: builtouts\nVersion: 0.2.0\n'
                    'Requires-Python: >=3.14\nLicense-Expression: MIT\nLicense-File: LICENSE\n'
                    'Classifier: Typing :: Typed\nDescription-Content-Type: text/markdown\n\n').encode() + readme
        module.verify_metadata(metadata, readme, '0.2.0')
        with self.assertRaisesRegex(RuntimeError, 'README metadata differs'):
            module.verify_metadata(metadata, b'different', '0.2.0')


if __name__ == '__main__':
    unittest.main()
