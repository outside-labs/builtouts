import unittest

from builtouts.html import Document, LinkCollector, ParseLimitError, TextCollector


class CollectorTests(unittest.TestCase):
    def test_links_resolution_boolean_empty_and_self_closing(self):
        parser = LinkCollector(base_url='https://example.test/base/')
        parser.feed('<base href="https://untrusted.test/"><a href="../x">A &amp; <b>B</b><script>hidden</script></a><a href=""/><a href><a>skip</a>')
        parser.close()
        self.assertEqual([(x.href, x.text, x.url) for x in parser.links],
                         [('../x', 'A & B', 'https://example.test/x'), ('', '', 'https://example.test/base/')])
        parser = LinkCollector()
        parser.feed('<div><a href=x>open</div>')
        parser.close()
        self.assertEqual(parser.links[0].url, 'x')

    def test_chunked_equivalence_for_both_collectors(self):
        source = 'before<a href="x?x=1&amp;y=2">A &amp; <b>B</b><br>C</a><style>hide</style>after'
        for split in range(len(source) + 1):
            links, text = LinkCollector(), TextCollector()
            for parser in (links, text):
                parser.feed(source[:split])
                parser.feed(source[split:])
                parser.close()
            self.assertEqual(text.text, Document.from_html(source).text)
            self.assertEqual(links.links[0].text, 'A & BC')
            self.assertEqual(links.links[0].href, 'x?x=1&y=2')

    def test_callback_only_and_eof_closure(self):
        seen = []
        links = LinkCollector(on_link=seen.append, collect=False)
        links.feed('<a href=x>unfinished')
        self.assertEqual(seen, [])
        links.close()
        links.close()
        self.assertEqual(seen[0].text, 'unfinished')
        self.assertEqual(links.links, ())
        pieces = []
        text = TextCollector(on_text=pieces.append, collect=False)
        for chunk in ('a', '<b>b</b>', '<script>x</script>', 'c'):
            text.feed(chunk)
        text.close()
        self.assertEqual(''.join(pieces), 'abc')
        self.assertEqual(text.text, '')

    def test_nested_anchor_emission_order(self):
        links = LinkCollector()
        links.feed('<a href=outer>A<a href=inner>B</a>C')
        links.close()
        self.assertEqual([(x.href, x.text) for x in links.links], [('inner', 'B'), ('outer', 'ABC')])

    def test_limits_callback_failure_and_lifecycle(self):
        for cls in (LinkCollector, TextCollector):
            for source, limits in [('<a>', {'max_chars': 2}), ('<a>x', {'max_nodes': 1}),
                                   ('<a><b>', {'max_depth': 1})]:
                with self.subTest(cls=cls, limits=limits), self.assertRaises(ParseLimitError):
                    cls(**limits).feed(source)
            parser = cls()
            parser.close()
            with self.assertRaises(RuntimeError):
                parser.feed('x')
            with self.assertRaises(RuntimeError):
                parser.reset()
        def fail(_):
            raise LookupError('callback')
        parser = LinkCollector(on_link=fail)
        with self.assertRaisesRegex(LookupError, 'callback'):
            parser.feed('<a href="x"/>')
        with self.assertRaises(RuntimeError):
            parser.close()
        for constructor in (lambda: LinkCollector(base_url=2), lambda: LinkCollector(on_link=1),
                            lambda: TextCollector(on_text=1), lambda: TextCollector(collect=1)):
            with self.assertRaises(TypeError):
                constructor()


if __name__ == '__main__':
    unittest.main()
