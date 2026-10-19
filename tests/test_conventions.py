import unicodedata
import unittest

from builtouts.conventions import camel_case, kebab_case, pascal_case, snake_case, words


class ConventionTests(unittest.TestCase):
    def test_acronyms_case_boundaries_and_digits(self):
        fixtures = {
            'HTTPServer': ('http', 'server'),
            'XMLHttpRequest': ('xml', 'http', 'request'),
            'getHTTPResponse': ('get', 'http', 'response'),
            'version2ID': ('version2', 'id'),
            'HTTP2Server': ('http2', 'server'),
            'sha256sum': ('sha256sum',),
            '42things': ('42things',),
            'ALLCAPS': ('allcaps',),
            'lowercase': ('lowercase',),
        }
        for source, expected in fixtures.items():
            with self.subTest(source=source):
                self.assertEqual(words(source), expected)

    def test_conversions_and_separators(self):
        self.assertEqual(snake_case('HTTPServer version2ID'), 'http_server_version2_id')
        self.assertEqual(kebab_case('  hello...world__foo/bar\tbaz '), 'hello-world-foo-bar-baz')
        self.assertEqual(camel_case('HTTP_server name'), 'httpServerName')
        self.assertEqual(pascal_case('HTTP_server name'), 'HttpServerName')
        for convert in (words, snake_case, kebab_case, camel_case, pascal_case):
            for source in ('', ' _-/...\t', '😀'):
                self.assertEqual(convert(source), () if convert is words else '')

    def test_unicode_normalization_marks_and_uncased_scripts(self):
        self.assertEqual(snake_case('Cafe\u0301Name'), 'café_name')
        self.assertEqual(snake_case('élanHTTPServer'), 'élan_http_server')
        self.assertEqual(words('日本語 名前'), ('日本語', '名前'))
        self.assertEqual(words('हिन्दी शब्द'), ('हिन्दी', 'शब्द'))
        self.assertEqual(words('\u0301Cafe'), ('cafe',))
        for convert in (snake_case, kebab_case, camel_case, pascal_case):
            result = convert('Cafe\u0301 name')
            self.assertEqual(result, unicodedata.normalize('NFC', result))
        self.assertEqual(pascal_case('ßeta name'), 'SSetaName')

    def test_collisions_are_explicit_and_identifiers_not_guaranteed(self):
        self.assertEqual(snake_case('a-b'), snake_case('a b'))
        self.assertEqual(snake_case('42'), '42')
        self.assertFalse(snake_case('42').isidentifier())
        self.assertEqual(snake_case('class'), 'class')

    def test_types(self):
        for convert in (words, snake_case, kebab_case, camel_case, pascal_case):
            for value in (None, 1, b'text', ['a']):
                with self.subTest(convert=convert, value=value), self.assertRaises(TypeError):
                    convert(value)


if __name__ == '__main__':
    unittest.main()
