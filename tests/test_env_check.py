"""Unit tests for environment readiness checks."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from transcriber.env_check import run_environment_check
from transcriber.cli import run_easy_start


class EnvCheckTests(unittest.TestCase):
    """Validate readiness checks with mocked dependencies."""

    def setUp(self) -> None:
        self._cwd = os.getcwd()

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    @mock.patch("transcriber.env_check.platform.system", return_value="Linux")
    @mock.patch("transcriber.env_check.importlib.util.find_spec", return_value=object())
    def test_ready_environment(self, mock_find_spec, mock_system) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            os.chdir(tmp_path)

            (tmp_path / "requirements.txt").write_text("numpy>=1.26\n", encoding="utf-8")
            # Create required files/directories
            required = [
                "transcriber/__init__.py",
                "transcriber/cli.py",
                "transcriber/config.py",
                "transcriber/audio.py",
                "transcriber/pipeline.py",
                "transcriber/asr/speechmatics_backend.py",
            ]
            for rel in required:
                path = tmp_path / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# stub\n", encoding="utf-8")

            (tmp_path / "logs").mkdir()
            (tmp_path / "gen-lang-client-0219123936-d6e117f5a590.json").write_text("{}", encoding="utf-8")
            (tmp_path / ".env").write_text(
                "\n".join(
                    [
                        "SPEECHMATICS_API_KEY=sk_test_123",
                        "AUDIO_DEVICE_INDEX=4",
                        "GOOGLE_TRANSLATE_CREDENTIALS_PATH=gen-lang-client-0219123936-d6e117f5a590.json",
                    ]
                ),
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()):
                ready = run_environment_check()

        self.assertTrue(ready)
        mock_find_spec.assert_called()
        mock_system.assert_called()

    @mock.patch("transcriber.env_check.platform.system", return_value="Linux")
    def test_missing_package_detected(self, mock_system) -> None:
        def fake_find_spec(module_name: str):
            return None if module_name == "numpy" else object()

        with mock.patch("transcriber.env_check.importlib.util.find_spec", side_effect=fake_find_spec):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                os.chdir(tmp_path)

                (tmp_path / "requirements.txt").write_text("numpy>=1.26\n", encoding="utf-8")
                (tmp_path / "transcriber").mkdir()
                (tmp_path / "transcriber/__init__.py").write_text("# stub\n", encoding="utf-8")
                (tmp_path / "logs").mkdir()
                (tmp_path / ".env").write_text("", encoding="utf-8")
                (tmp_path / "gen-lang-client-0219123936-d6e117f5a590.json").write_text("{}", encoding="utf-8")

                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    ready = run_environment_check()

        output = buffer.getvalue()
        self.assertFalse(ready)
        self.assertIn("numpy", output)
        mock_system.assert_called()

    @mock.patch("transcriber.cli._ensure_linux_physical_defaults")
    @mock.patch("transcriber.cli._unload_linux_modules")
    @mock.patch("transcriber.cli._snapshot_linux_modules", return_value={"null": set(), "loop": set()})
    @mock.patch("transcriber.cli._restore_linux_defaults")
    @mock.patch("transcriber.cli._capture_linux_defaults", return_value=("sink", "source"))
    @mock.patch("transcriber.cli.run_environment_check", return_value=True)
    @mock.patch("transcriber.cli.load_settings")
    @mock.patch("transcriber.cli.run_cli_diagnostics")
    def test_easy_start_non_interactive(
        self,
        mock_run_cli_diagnostics,
        mock_load_settings,
        mock_run_env_check,
        mock_capture_linux_defaults,
        mock_restore_linux_defaults,
        mock_snapshot_linux_modules,
        mock_unload_linux_modules,
        mock_ensure_phys,
    ) -> None:
        mock_load_settings.return_value = SimpleNamespace(audio="stub")
        result = run_easy_start(interactive=False)
        self.assertTrue(result)
        mock_run_env_check.assert_called_once()
        mock_run_cli_diagnostics.assert_called_once()
        mock_capture_linux_defaults.assert_called()
        mock_restore_linux_defaults.assert_called()
        mock_snapshot_linux_modules.assert_called()
        mock_unload_linux_modules.assert_not_called()
        mock_ensure_phys.assert_called()

    @mock.patch("transcriber.cli._ensure_linux_physical_defaults")
    @mock.patch("transcriber.cli._unload_linux_modules")
    @mock.patch("transcriber.cli._snapshot_linux_modules")
    @mock.patch("transcriber.cli._restore_linux_defaults")
    @mock.patch("transcriber.cli._capture_linux_defaults", return_value=None)
    @mock.patch("transcriber.cli.run_environment_check", return_value=False)
    def test_easy_start_aborts_when_env_check_fails(
        self,
        mock_run_env_check,
        mock_capture_linux_defaults,
        mock_restore_linux_defaults,
        mock_snapshot_linux_modules,
        mock_unload_linux_modules,
        mock_ensure_phys,
    ) -> None:
        with redirect_stdout(io.StringIO()):
            result = run_easy_start(interactive=False)
        self.assertFalse(result)
        mock_run_env_check.assert_called_once()
        mock_capture_linux_defaults.assert_not_called()
        mock_restore_linux_defaults.assert_not_called()
        mock_snapshot_linux_modules.assert_not_called()
        mock_unload_linux_modules.assert_not_called()
        mock_ensure_phys.assert_not_called()

    @mock.patch("transcriber.cli._ensure_linux_physical_defaults")
    @mock.patch("transcriber.cli.subprocess.run")
    @mock.patch("transcriber.cli._unload_linux_modules")
    @mock.patch(
        "transcriber.cli._snapshot_linux_modules",
        side_effect=[
            {"null": set(), "loop": set()},
            {"null": {"10"}, "loop": {"20"}},
            {"null": {"10"}, "loop": {"20"}},
        ],
    )
    @mock.patch("transcriber.cli._restore_linux_defaults")
    @mock.patch("transcriber.cli._capture_linux_defaults", return_value=("alsa_output.pci-0000_00_1f.3.analog-stereo", "alsa_input.pci-0000_00_1f.3.analog-stereo"))
    @mock.patch("transcriber.cli.run_pipeline")
    @mock.patch("transcriber.cli.run_environment_check", return_value=True)
    @mock.patch("transcriber.cli.load_settings")
    @mock.patch("transcriber.cli.run_cli_diagnostics")
    @mock.patch("platform.system", return_value="Linux")
    def test_easy_start_interactive_linux_restores(
        self,
        mock_platform,
        mock_run_cli_diagnostics,
        mock_load_settings,
        mock_run_env_check,
        mock_run_pipeline,
        mock_capture_linux_defaults,
        mock_restore_linux_defaults,
        mock_snapshot_linux_modules,
        mock_unload_linux_modules,
        mock_subprocess_run,
        mock_ensure_phys,
    ) -> None:
        mock_load_settings.return_value = SimpleNamespace(audio="stub")

        async def fake_pipeline(*args, **kwargs):
            self.assertEqual(os.environ.get("AUDIO_LOOPBACK_ALREADY_SET"), "1")
            self.assertEqual(
                os.environ.get("HEADPHONE_SINK"),
                "alsa_output.pci-0000_00_1f.3.analog-stereo",
            )

        mock_run_pipeline.side_effect = fake_pipeline

        with mock.patch("builtins.input", side_effect=["y", "y"]), mock.patch.dict(os.environ, {}, clear=True):
            result = run_easy_start()

        self.assertTrue(result)
        mock_subprocess_run.assert_any_call(
            ["bash", mock.ANY], check=True
        )
        mock_restore_linux_defaults.assert_called()
        mock_unload_linux_modules.assert_called()
        mock_ensure_phys.assert_called()
        self.assertNotIn("AUDIO_LOOPBACK_ALREADY_SET", os.environ)
        self.assertNotIn("HEADPHONE_SINK", os.environ)
