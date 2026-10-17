"""Tests for running a Kodi builtin through script.toolbox."""

import importlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_hover  # noqa: F401  installs the sublime stubs and the KodiDevKit package

commands = importlib.import_module("KodiDevKit.commands")
Command = commands.KodidevkitExecuteBuiltinCommand


class TestExecuteBuiltin(unittest.TestCase):
    """What the user is told when Kodi refuses a builtin."""

    def setUp(self):
        """Set up a fresh session whose dialogs are recorded and timers run at once."""
        Command._refusal_shown = False
        self.dialogs = []
        for patch in (mock.patch.object(commands.sublime, "set_timeout", lambda fn, *_: fn()),
                      mock.patch.object(commands.sublime, "message_dialog", self.dialogs.append, create=True)):
            patch.start()
            self.addCleanup(patch.stop)

    def run_builtin(self, reply):
        """Run ReloadSkin() against a Kodi that gives the reply, waiting for the worker thread."""
        with mock.patch.object(commands.kodi, "request", return_value=reply):
            Command.run(object(), "ReloadSkin()").join()

    def test_refusal_is_explained_once_a_session(self):
        """A refused builtin names Kodi's error and script.toolbox; a second one stays quiet."""
        refusal = {"error": {"code": -32602, "message": "Invalid params."}}
        self.run_builtin(refusal)
        self.run_builtin(refusal)
        self.assertEqual(len(self.dialogs), 1)
        self.assertIn("Kodi did not run ReloadSkin(): Invalid params.", self.dialogs[0])
        self.assertIn("script.toolbox", self.dialogs[0])

    def test_success_and_an_unreachable_kodi_say_nothing(self):
        """A builtin Kodi accepts, or a Kodi that never answers, shows no dialog."""
        self.run_builtin({"result": "OK"})
        self.run_builtin(None)
        self.assertEqual(self.dialogs, [])


if __name__ == "__main__":
    unittest.main()
