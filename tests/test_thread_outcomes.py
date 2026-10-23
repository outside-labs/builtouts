import itertools
import threading
import unittest

from builtouts.concurrent import Outcome, thread_iter, thread_map, thread_outcomes


class OutcomeTests(unittest.TestCase):
    def test_mixed_results_original_errors_and_none(self):
        error = LookupError('original')
        def work(value):
            if value == 1:
                raise error
            return None if value == 0 else value * 2
        with thread_outcomes(work, range(3), max_workers=2) as results:
            rows = list(results)
        self.assertEqual([row.index for row in rows], [0, 1, 2])
        self.assertTrue(rows[0].ok)
        self.assertIsNone(rows[0].result())
        self.assertFalse(rows[1].ok)
        self.assertIs(rows[1].error, error)
        with self.assertRaises(LookupError) as raised:
            rows[1].result()
        self.assertIs(raised.exception, error)
        self.assertEqual(rows[2].result(), 4)
        self.assertFalse(hasattr(rows[0], 'input'))

    def test_ready_results_keep_original_indices(self):
        release = threading.Event()
        def work(value):
            if value == 0 and not release.wait(5):
                raise TimeoutError('test safety timeout')
            return value
        try:
            with thread_outcomes(work, [0, 1], max_workers=2, ordered=False) as results:
                self.assertEqual(next(results).index, 1)
                release.set()
                self.assertEqual(next(results).index, 0)
        finally:
            release.set()

    def test_callbacks_run_on_consumer_and_before_yield(self):
        consumer = threading.get_ident()
        seen = []
        def observe(row):
            self.assertEqual(threading.get_ident(), consumer)
            seen.append(row.index)
        with thread_outcomes(threading.get_ident, [None]) as results:
            # Wrong call arity is captured as a normal worker failure.
            self.assertIsInstance(next(results).error, TypeError)
        with thread_iter(lambda value: threading.get_ident(), [1, 2], on_result=observe) as results:
            self.assertNotEqual(next(results), consumer)
            self.assertEqual(seen, [0])
        self.assertEqual(seen, [0])

    def test_fail_fast_behavior_and_error_callback(self):
        error = ValueError('worker')
        observed = []
        def work(value):
            raise error
        with self.assertRaises(ValueError) as raised:
            thread_map(work, [0, 1], max_pending=1, on_result=observed.append)
        self.assertIs(raised.exception, error)
        self.assertEqual(len(observed), 1)
        self.assertIs(observed[0].error, error)

    def test_callback_failures_propagate_and_join_workers(self):
        error = RuntimeError('observer')
        workers = []
        def work(value):
            workers.append(threading.current_thread())
            return value
        def observer(row):
            raise error
        with self.assertRaises(RuntimeError) as raised:
            with thread_outcomes(work, range(10), max_workers=2, on_result=observer) as results:
                next(results)
        self.assertIs(raised.exception, error)
        self.assertTrue(all(not worker.is_alive() for worker in workers))

    def test_input_failures_and_base_exceptions_remain_failures(self):
        def source():
            yield 1
            raise OSError('producer')
        with self.assertRaises(OSError):
            with thread_outcomes(str, source()) as results:
                list(results)
        def stop(value):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            with thread_outcomes(stop, [0]) as results:
                next(results)

    def test_bounds_empty_inputs_and_unused_context(self):
        seen = []
        def source():
            for value in itertools.count():
                seen.append(value)
                yield value
        with thread_outcomes(str, source(), max_pending=2) as results:
            self.assertEqual(seen, [])
            self.assertEqual(next(results).index, 0)
            self.assertEqual(seen, [0, 1])
        self.assertEqual(list(results), [])
        with thread_outcomes(str, []) as results:
            self.assertEqual(list(results), [])
        with thread_outcomes(str, source()) as results:
            pass
        self.assertEqual(seen, [0, 1])
        for ordered in (True, False):
            with thread_outcomes(str, range(9), max_pending=2, ordered=ordered) as results:
                rows = sorted(results, key=lambda row: row.index)
            self.assertEqual([row.index for row in rows], list(range(9)))
            self.assertEqual([row.value for row in rows], list(map(str, range(9))))

    def test_record_and_callback_validation(self):
        for kwargs in ({'index': True}, {'index': -1}, {'index': 0, 'error': KeyboardInterrupt()},
                       {'index': 0, 'value': 1, 'error': ValueError()}):
            with self.assertRaises((TypeError, ValueError)):
                Outcome(**kwargs)
        for api in (thread_iter, thread_outcomes):
            with self.assertRaises(TypeError):
                with api(str, [], on_result=1):
                    pass
        with self.assertRaises(TypeError):
            thread_map(str, [], on_result=1)


if __name__ == '__main__':
    unittest.main()
