"""Tests for the report server's port."""

import importlib
import os
import socket
import sys
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_hover  # noqa: F401  installs the sublime stubs and the KodiDevKit package

server = importlib.import_module("KodiDevKit.libs.reporting.server")


class TestServerPort(unittest.TestCase):
    """Port the report server listens on, which every report link names."""

    def setUp(self):
        """Set up a held port as the preferred one, with no server running."""
        server.stop_server()
        self.blocker = socket.socket()
        self.blocker.bind(("localhost", 0))
        self.blocker.listen()
        self.saved = server._PREFERRED_PORT
        setattr(server, "_PREFERRED_PORT", self.blocker.getsockname()[1])

    def tearDown(self):
        """Stop the server, free the port and restore the preferred one."""
        server.stop_server()
        self.blocker.close()
        setattr(server, "_PREFERRED_PORT", self.saved)
        setattr(server, "_server_port", self.saved)

    def test_taken_port_falls_back_to_a_free_one(self):
        """A refused port leaves the server on another port, the one reports then name."""
        port = server.get_server_port()
        self.assertNotEqual(port, server._PREFERRED_PORT)
        with urllib.request.urlopen(f"http://localhost:{port}/ping", timeout=5) as reply:
            self.assertEqual(reply.read(), b"OK")


if __name__ == "__main__":
    unittest.main()
