import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import httpx
from web_research import public_url, read_page, Research


class WebTests(unittest.TestCase):
    def test_private_addresses_and_schemes_blocked(self):
        for url in ('file:///etc/passwd', 'http://user:pass@example.com', 'http://example.com:8097'):
            with self.assertRaises(ValueError):
                public_url(url)
        with patch('web_research.socket.getaddrinfo', return_value=[(0, 0, 0, '', ('127.0.0.1', 80))]):
            with self.assertRaises(ValueError):
                public_url('https://example.com')

    def test_redirect_destination_checked(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'location': 'http://127.0.0.1'})))
        with patch('web_research.httpx.Client', return_value=client), patch('web_research.public_url', side_effect=['https://example.com', ValueError('private')]) as guard:
            with self.assertRaises(ValueError):
                read_page('https://example.com')
            self.assertEqual(guard.call_count, 2)

    def test_sources_progress_and_report_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            progress = []
            research = Research(Mock(), Path(folder), progress.append)
            research.generate = Mock(side_effect=['Evidence from the page.', 'Supported answer [1].'])
            with patch('web_research.DDGS') as search, patch('web_research.read_page', return_value=('https://example.com', 'Page text')):
                search.return_value.text.return_value = [{'href': 'https://example.com', 'title': 'Example'}]
                report = research.run('A topic')
            self.assertIn('https://example.com', report)
            self.assertTrue(research.path.with_suffix('.md').exists())
            self.assertTrue(any('Reading:' in p for p in progress))

    def test_no_sources_never_produces_unsupported_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            research = Research(Mock(), Path(folder), lambda x: None)
            research.generate = Mock()
            with patch('web_research.DDGS') as search:
                search.return_value.text.return_value = []
                with self.assertRaises(RuntimeError):
                    research.run('A topic')
            research.generate.assert_not_called()

    def test_research_runs_multiple_queries_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            research = Research(Mock(), Path(folder), lambda x: None)
            research.generate = Mock(side_effect=['First angle\nSecond angle', 'Evidence.', 'Report [1].'])
            with patch('web_research.DDGS') as search, patch('web_research.read_page', return_value=('https://example.com', 'text')) as read:
                search.return_value.text.return_value = [{'href': 'https://example.com', 'title': 'Example'}]
                research.run('Original topic', deep=True)
                self.assertEqual(search.return_value.text.call_count, 3)
                self.assertEqual(read.call_count, 1)

    def test_invalid_citation_fails_instead_of_publishing(self):
        with tempfile.TemporaryDirectory() as folder:
            research = Research(Mock(), Path(folder), lambda x: None)
            research.generate = Mock(side_effect=['Evidence.', 'Unsupported [99].'])
            with patch('web_research.DDGS') as search, patch('web_research.read_page', return_value=('https://example.com', 'text')):
                search.return_value.text.return_value = [{'href': 'https://example.com', 'title': 'Example'}]
                with self.assertRaises(RuntimeError):
                    research.run('Topic')
            self.assertFalse(research.path.with_suffix('.md').exists())
