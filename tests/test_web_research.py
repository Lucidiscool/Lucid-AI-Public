import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import httpx
from web_research import public_url, read_page, Research, PublicHTTPTransport


class WebTests(unittest.TestCase):
    def test_connection_pins_validated_ip_and_preserves_tls_hostname(self):
        answers = [[(0, 0, 0, '', ('93.184.216.34', 443))],
                   [(0, 0, 0, '', ('127.0.0.1', 443))]]
        with patch('web_research.socket.getaddrinfo', side_effect=answers) as dns:
            with PublicHTTPTransport() as transport, patch.object(httpx.HTTPTransport, 'handle_request') as send:
                transport.handle_request(httpx.Request('GET', 'https://example.com/article'))
                pinned = send.call_args.args[0]
                self.assertEqual(pinned.url.host, '93.184.216.34')
                self.assertEqual(pinned.headers['host'], 'example.com')
                self.assertEqual(pinned.extensions['sni_hostname'], 'example.com')
                self.assertEqual(dns.call_count, 1)
                with self.assertRaises(ValueError):
                    transport.handle_request(httpx.Request('GET', 'https://example.com/article'))
                self.assertEqual(send.call_count, 1)

    def test_long_evidence_is_reduced_without_breaking_json(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            backend = Mock()
            backend.answer.side_effect = [ValueError('Message is too long for the local context.'),
                                         [{'content': 'Extracted evidence.'}]]
            research = Research(backend, Path(folder), lambda _: None)
            data = json.dumps({'question': 'Topic', 'page_text': 'a' * 12000})
            self.assertEqual(research.generate('Extract', data, 230), 'Extracted evidence.')
            reduced = json.loads(backend.answer.call_args.args[0][1]['content'])
            self.assertEqual(reduced['question'], 'Topic')
            self.assertLess(len(reduced['page_text']), 12000)

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
