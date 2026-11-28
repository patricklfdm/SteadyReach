from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch
from http.client import HTTPConnection
from urllib.parse import urlsplit

from ras_workflow import app_server, intake_server, launcher, native_import_ui, review_server
from ras_workflow import site_review, team_review
from ras_workflow.interface_style import embedded_interface_style


class InterfaceAssets(unittest.TestCase):
    def test_all_live_entry_points_serve_the_same_local_stylesheet(self):
        templates = Path(app_server.__file__).parent / 'templates'
        css = (templates / 'interface.css').read_bytes()
        factories = (app_server.create, launcher.create, lambda: intake_server.create('project.json'),
                     lambda: native_import_ui.create('project.json'), lambda: review_server.create(session='review.json'))
        for make_server in factories:
            with (self.subTest(factory=make_server), patch.object(launcher, 'Controller'),
                  patch.object(native_import_ui,'view'), make_server() as server):
                thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
                thread.start()
                try:
                    prefix = urlsplit(server.url).path
                    for route in ('', 'interface.css'):
                        client = HTTPConnection(*server.server_address, timeout=5)
                        try:
                            client.request('GET', prefix + route)
                            response = client.getresponse()
                            self.assertEqual(response.status, 200)
                            if route:
                                self.assertEqual(response.headers.get_content_type(), 'text/css')
                                self.assertEqual(response.read(), css)
                            else:
                                self.assertIn(b'href="interface.css"', response.read())
                        finally:
                            client.close()
                finally:
                    server.shutdown()
                    thread.join()

    def test_offline_map_and_review_form_embed_the_stylesheet(self):
        submitted = dict(head='original',state='SUBMITTED',schema='example',edition={},stations=[],dependencies=[])
        with patch.object(team_review,'inspect',return_value=submitted):
            form = team_review.offline_form('test','original')['html']
        for page in (site_review.render_html({}, {}), form):
            self.assertIn(embedded_interface_style(),page)
            self.assertNotIn('__INTERFACE_STYLE__',page)
            self.assertNotIn('href="interface.css"',page)
