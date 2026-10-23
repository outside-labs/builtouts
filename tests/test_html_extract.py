from dataclasses import dataclass
import unittest

from builtouts.html import Document, ExtractionError, Field, SelectorSyntaxError, extract, extract_all


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document.from_html('<main><article data-id="1"><h2> One </h2><a href="/one">a</a><a href="/two">b</a></article><article data-id="2"><h2>Two</h2></article></main>')

    def test_records_are_dataclass_friendly_and_scoped(self):
        @dataclass
        class Entry:
            id: int
            title: str
        fields = {'id': Field(attribute='DATA-ID', convert=int), 'title': Field('h2')}
        records = extract_all(self.doc, 'article', fields)
        self.assertEqual([Entry(**record) for record in records], [Entry(1, 'One'), Entry(2, 'Two')])
        self.assertEqual(extract(self.doc.find('h2'), {'raw': Field(strip=False)}), {'raw': ' One '})
        with self.assertRaises(ExtractionError):
            extract(self.doc.find('article'), {'outside': Field('main h2')})

    def test_many_and_optional_fallbacks(self):
        fields = {'links': Field('a', attribute='href', many=True, required=False),
                  'missing': Field('.absent', required=False),
                  'label': Field('.absent', required=False, default='unknown')}
        records = extract_all(self.doc, 'article', fields)
        self.assertEqual(records[0], {'links': ['/one', '/two'], 'missing': None, 'label': 'unknown'})
        self.assertEqual(records[1]['links'], [])
        self.assertIsNot(records[1]['links'], extract(self.doc.find_all('article')[1], fields)['links'])
        factories = {'missing': Field('.absent', required=False, default_factory=list)}
        rows = extract_all(self.doc, 'article', factories)
        self.assertIsNot(rows[0]['missing'], rows[1]['missing'])

    def test_missing_and_multiple_cardinality_errors(self):
        for fields, reason in [({'value': Field('aside')}, 'missing'), ({'value': Field('a')}, 'multiple')]:
            with self.assertRaises(ExtractionError) as raised:
                extract(self.doc.find('article'), fields)
            self.assertEqual((raised.exception.field, raised.exception.reason, raised.exception.record), ('value', reason, None))
        with self.assertRaises(ExtractionError) as raised:
            extract_all(self.doc, 'article', {'link': Field('a', many=True)})
        self.assertEqual(raised.exception.record, 1)

    def test_boolean_missing_and_empty_attributes(self):
        doc = Document.from_html('<a href><a href=""><a>')
        optional = {'href': Field(attribute='href', required=False)}
        self.assertEqual(extract_all(doc, 'a', optional), [{'href': None}, {'href': ''}, {'href': None}])
        with self.assertRaises(ExtractionError) as raised:
            extract(doc, {'href': Field('a', attribute='href', many=True)})
        self.assertEqual((raised.exception.reason, raised.exception.item), ('attribute', 0))

    def test_conversion_and_factory_causes_are_preserved_without_source_values(self):
        original = LookupError('converter detail')
        def fail(value):
            raise original
        with self.assertRaises(ExtractionError) as raised:
            extract_all(self.doc, 'article', {'title': Field('h2', convert=fail)})
        self.assertIs(raised.exception.__cause__, original)
        self.assertEqual(raised.exception.reason, 'conversion')
        self.assertNotIn('One', str(raised.exception))
        def factory():
            raise original
        with self.assertRaises(ExtractionError) as raised:
            extract(self.doc, {'value': Field('aside', required=False, default_factory=factory)})
        self.assertEqual(raised.exception.reason, 'default')
        self.assertIs(raised.exception.__cause__, original)

    def test_base_exceptions_propagate(self):
        def stop(value):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            extract(self.doc, {'value': Field('h2', many=True, convert=stop)})

    def test_schema_and_selectors_validated_on_empty_input(self):
        empty = Document.from_html('')
        for fields in ([], {'x': 'h2'}, {1: Field()}, {'': Field()}):
            with self.subTest(fields=fields), self.assertRaises(TypeError):
                extract_all(empty, 'article', fields)
        with self.assertRaises(SelectorSyntaxError):
            Field('a:hover')
        with self.assertRaises(SelectorSyntaxError):
            extract_all(empty, 'a:hover', {})
        for kwargs in ({'many': 1}, {'required': 1}, {'strip': 1}, {'convert': 1},
                       {'attribute': 1}, {'default_factory': 1}):
            with self.assertRaises(TypeError):
                Field(**kwargs)
        for kwargs in ({'attribute': ''}, {'default': 1},
                       {'required': False, 'default': 1, 'default_factory': list}):
            with self.assertRaises(ValueError):
                Field(**kwargs)
        with self.assertRaises(TypeError):
            extract(None, {})
        self.assertEqual(extract_all(empty, 'article', {}), [])


if __name__ == '__main__':
    unittest.main()
