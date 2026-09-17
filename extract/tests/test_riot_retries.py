import io
import unittest
from unittest.mock import patch
from loadData import RiotClient


class RetryTests(unittest.TestCase):
    @patch('loadData.time.sleep')
    @patch('loadData.urlopen')
    def test_read_timeout_retries_the_request(self, request, sleep):
        request.side_effect = [TimeoutError('read timed out'), io.StringIO('{"ok": true}')]
        self.assertEqual(RiotClient('test', interval=0).get('https://example.test'), {'ok': True})
        self.assertEqual(request.call_count, 2)

    @patch('loadData.time.sleep')
    @patch('loadData.urlopen', side_effect=TimeoutError('read timed out'))
    def test_persistent_timeouts_fail_after_bounded_retries(self, request, sleep):
        with self.assertRaisesRegex(RuntimeError, 'Network error'):
            RiotClient('test', interval=0).get('https://example.test')
        self.assertEqual(request.call_count, 6)
