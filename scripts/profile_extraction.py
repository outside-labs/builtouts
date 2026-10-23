"""Bounded diagnostic measurements; no benchmark threshold or speed claim."""

import argparse
import gc
import json
import platform
import sys
from time import perf_counter
import tracemalloc

from builtouts import __version__
from builtouts.html import Document, Field, extract_all


def _measure(source: str) -> dict[str, object]:
    tracemalloc.start()
    try:
        started = perf_counter()
        document = Document.from_html(source)
        records = extract_all(document, 'article', {
            'id': Field(attribute='data-id', convert=int), 'title': Field('h2'),
        })
        elapsed = perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        return {'records': len(records), 'elapsed_seconds': elapsed, 'traced_peak_bytes': peak}
    finally:
        tracemalloc.stop()


def profile(records: int = 1000, iterations: int = 3) -> dict[str, object]:
    for name, value, maximum in (('records', records, 10000), ('iterations', iterations, 20)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f'{name} must be an integer')
        if not 1 <= value <= maximum:
            raise ValueError(f'{name} must be between 1 and {maximum}')
    if tracemalloc.is_tracing():
        raise RuntimeError('run this diagnostic in its own tracemalloc session')
    source = ''.join(f'<article data-id="{n}"><h2>Entry {n}</h2></article>' for n in range(records))
    samples = []
    for _ in range(iterations):
        gc.collect()
        samples.append(_measure(source))
    return {
        'environment': {'builtouts': __version__, 'python': sys.version,
                        'implementation': platform.python_implementation(), 'platform': platform.platform()},
        'workload': {'records': records, 'input_characters': len(source), 'iterations': iterations,
                     'measured_stage': 'parse, select and extract; excludes input generation/imports',
                     'memory_scope': 'traced Python allocations, not process RSS'},
        'samples': samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=int, default=1000)
    parser.add_argument('--iterations', type=int, default=3)
    args = parser.parse_args()
    try:
        result = profile(args.records, args.iterations)
    except (ValueError, TypeError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
