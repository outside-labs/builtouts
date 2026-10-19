import unittest

from builtouts.html import Document, DocumentParser, ParseLimitError


class TreeTests(unittest.TestCase):
    def test_structure_attributes_and_traversal(self):
        doc = Document.from_html('<!DOCTYPE html><!--hi--><DIV ID=x id=y disabled><p>A &amp; <b>B</b></p></DIV>')
        div = doc.find('DIV')
        self.assertIs(div.parent, doc)
        self.assertEqual(div.attrs, {'id': 'y', 'disabled': None})
        self.assertIsInstance(div.children, tuple)
        with self.assertRaises(TypeError):
            div.attrs['id'] = 'z'
        with self.assertRaises(AttributeError):
            div.tag = 'span'
        self.assertEqual([n.kind for n in doc.children], ['declaration', 'comment', 'element'])
        self.assertEqual([n.tag for n in doc.descendants() if n.kind == 'element'], ['div', 'p', 'b'])
        self.assertIsNone(doc.find('aside'))

    def test_filters_include_boolean_absent_empty_and_class_tokens(self):
        doc = Document.from_html('<input disabled><a href="" class="item active"></a><a></a>')
        self.assertEqual(len(doc.find_all('a', href=True)), 1)
        self.assertEqual(len(doc.find_all('a', href=False)), 1)
        self.assertIsNotNone(doc.find('input', disabled=None))
        self.assertIsNone(doc.find('input', missing=None))
        self.assertEqual(doc.find(class_='active'), doc.find('a', attrs={'href': ''}))
        self.assertIsNone(doc.find(class_='act'))
        self.assertIsNone(doc.find('a').find('a'))
        with self.assertRaises(TypeError):
            doc.find(href=1)

    def test_visible_raw_and_separated_text(self):
        doc = Document.from_html('<title> A &amp; B </title><p> Hello <b>world</b>!<br>next</p><!--omit--><script>x < y &amp;</script><style>.a{}</style>')
        self.assertEqual(doc.title, 'A & B')
        self.assertEqual(doc.find('p').text, ' Hello world!next')
        self.assertEqual(doc.find('p').get_text(' ', strip=True), 'Hello world ! next')
        self.assertNotIn('x < y', doc.text)
        self.assertIn('x < y &amp;', doc.get_text(include_hidden=True))
        self.assertEqual(doc.find('script').text, '')
        self.assertIsNone(Document.from_html('').title)

    def test_void_self_closing_and_recovery(self):
        doc = Document.from_html('</unknown><div>A<br>B<img src=x>C<x/>D<p>E</div>F</p>')
        div = doc.find('div')
        self.assertEqual([n.tag for n in div.children if n.kind == 'element'], ['br', 'img', 'x', 'p'])
        self.assertEqual(div.text, 'ABCDE')
        self.assertEqual(doc.children[-1].data, 'F')
        # Optional closing tags are intentionally not inferred.
        nested = Document.from_html('<ul><li>a<li>b</ul>')
        self.assertIs(nested.find_all('li')[1].parent, nested.find('li'))

    def test_incremental_every_split_and_coalescing(self):
        source = '<p title="&amp;">alpha &amp; beta<b>ok</b></p>'
        expected = Document.from_html(source)
        for split in range(len(source) + 1):
            parser = DocumentParser()
            parser.feed(source[:split])
            parser.feed(source[split:])
            parser.close()
            self.assertEqual(parser.document.text, expected.text)
            self.assertEqual(parser.document.find('p').attrs, {'title': '&'})
            self.assertEqual(len(list(parser.document.descendants())), len(list(expected.descendants())))
        parser = DocumentParser(max_nodes=2)
        for chunk in ['<p>', 'a', 'b', 'c', '</p>']:
            parser.feed(chunk)
        parser.close()
        self.assertEqual(parser.document.text, 'abc')

    def test_lifecycle_and_incomplete_input(self):
        parser = DocumentParser()
        parser.feed('<p>done &')
        parser.close()
        parser.close()
        self.assertEqual(parser.document.text, 'done &')
        with self.assertRaises(RuntimeError):
            parser.feed('more')
        with self.assertRaises(RuntimeError):
            parser.reset()
        with self.assertRaises(TypeError):
            Document.from_html(b'<p>')

    def test_limits_boundaries_and_failure_reuse(self):
        self.assertEqual(Document.from_html('abc', max_chars=3).text, 'abc')
        self.assertEqual(Document.from_html('<p>x</p>', max_nodes=2, max_depth=1).text, 'x')
        for source, limits in [('abcd', {'max_chars': 3}), ('<p>x</p>', {'max_nodes': 1}),
                               ('<p><b>', {'max_depth': 1})]:
            with self.subTest(limits=limits), self.assertRaises(ParseLimitError):
                Document.from_html(source, **limits)
        parser = DocumentParser(max_chars=2)
        parser.feed('a')
        with self.assertRaises(ParseLimitError):
            parser.feed('bc')
        with self.assertRaises(RuntimeError):
            parser.feed('x')
        with self.assertRaises(RuntimeError):
            parser.close()
        for value in (True, 1.5, '2', 0, -1):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                DocumentParser(max_depth=value)

    def test_deep_traversal_is_iterative(self):
        doc = Document.from_html('<x>' * 1500 + 'yes', max_depth=1500)
        self.assertEqual(doc.text, 'yes')
        self.assertEqual(len(doc.find_all('x')), 1500)


if __name__ == '__main__':
    unittest.main()
