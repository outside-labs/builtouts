import unittest

from builtouts.html import Document, SelectorSyntaxError


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document.from_html('<main id="root"><article class="card hot" data-x="a,b > c"><h2>A</h2><a href="" disabled>one</a><section><a href="x">two</a></section></article><article class="card"><a href=x>three</a></article></main>')

    def test_subset_and_document_order_deduplication(self):
        self.assertEqual([n.text for n in self.doc.select('article.card > a[href], #root h2, .hot a')], ['A', 'one', 'two', 'three'])
        self.assertEqual(len(self.doc.select('MAIN#root article.hot[data-x="a,b > c"]')), 1)
        self.assertEqual(len(self.doc.select('a[disabled]')), 1)
        self.assertEqual(len(self.doc.select('[href=""]')), 1)
        self.assertEqual(len(self.doc.select('a[href=x]')), 2)
        self.assertEqual(len(self.doc.select('*')), 8)
        self.assertEqual(self.doc.select_one('.card').tag, 'article')
        self.assertIsNone(self.doc.select_one('footer'))

    def test_scoping_and_receiver_exclusion(self):
        article = self.doc.find('article')
        self.assertEqual(len(article.select('article > a')), 1)
        self.assertEqual(article.select('main a'), [])
        self.assertEqual(article.select('article'), [])
        self.assertEqual(len(article.select('a')), 2)

    def test_descendant_backtracking_and_long_queries(self):
        doc = Document.from_html('<div class=a><div class=b><div><div class=b><i class=c></i></div></div></div></div>')
        self.assertEqual(len(doc.select('.a > .b .c')), 1)
        deep = Document.from_html('<x>' * 1000 + '<i>', max_depth=1001)
        self.assertEqual(len(deep.select('x > i')), 1)

    def test_rejects_unsupported_and_malformed_even_without_nodes(self):
        empty = Document.from_html('')
        for selector in ['', ' ', 'a,', ',a', 'a,,b', '> a', 'a >', 'a >> b',
                         'a + b', 'a ~ b', ':first-child', 'a:hover', 'a::text',
                         '[x^=a]', '[x~=a]', '[x=a i]', '[x=]', '[x', 'a..b',
                         '[x="abc]', 'a\\b', 'svg|a', '[x="a\nb"]', '*' * 2,
                         'x' * 4097, ' '.join(['a'] * 65)]:
            with self.subTest(selector=selector), self.assertRaises(SelectorSyntaxError):
                empty.select(selector)
        with self.assertRaises(TypeError):
            empty.select(None)


if __name__ == '__main__':
    unittest.main()
