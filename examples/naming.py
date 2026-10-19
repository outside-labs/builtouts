"""Deterministic conventions without global policies or I/O."""

from builtouts.conventions import camel_case, kebab_case, pascal_case, snake_case, words

assert words('HTTPServer version2ID') == ('http', 'server', 'version2', 'id')
assert snake_case('Cafe\u0301Name') == 'café_name'
assert kebab_case('HTTPServer') == 'http-server'
assert camel_case('HTTP_server') == 'httpServer'
assert pascal_case('HTTP_server') == 'HttpServer'
assert snake_case('a b') == snake_case('a-b')  # Conversion can collide.
print('Naming conventions passed')
