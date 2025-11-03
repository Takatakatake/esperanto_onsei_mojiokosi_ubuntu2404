"""Unit tests for audio environment helpers."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from transcriber.audio_setup import (
    AudioEnvironmentError,
    AudioEnvironmentManager,
    collect_audio_diagnostics,
)
from transcriber.config import AudioInputConfig


class AudioSetupTests(unittest.TestCase):
    """Verify detection heuristics and guard rails."""

    @mock.patch("transcriber.audio_setup.sd.query_devices", return_value=[])
    def test_ensure_device_presence_without_inputs(self, mock_query_devices) -> None:
        manager = AudioEnvironmentManager(AudioInputConfig())
        with self.assertRaises(AudioEnvironmentError):
            manager._ensure_device_presence()
        mock_query_devices.assert_called()

    @mock.patch("transcriber.audio_setup.platform.system", return_value="Linux")
    @mock.patch(
        "transcriber.audio_setup.sd.query_devices",
        return_value=[
            {"name": "pipewire", "max_input_channels": 64, "max_output_channels": 64, "hostapi": 0},
            {"name": "default", "max_input_channels": 64, "max_output_channels": 64, "hostapi": 0},
        ],
    )
    def test_linux_pipewire_detected_as_loopback(self, mock_query_devices, mock_system) -> None:
        config = AudioInputConfig()
        report = collect_audio_diagnostics(config)
        self.assertTrue(report.loopback_candidates, "PipeWire/default monitors should be treated as candidates")
        self.assertFalse(report.issues, "No issues expected when monitors exist")
        mock_query_devices.assert_called()
        mock_system.assert_called()

    @mock.patch("transcriber.audio_setup.platform.system", return_value="Linux")
    @mock.patch(
        "transcriber.audio_setup.sd.query_devices",
        return_value=[
            {"name": "alsa_input.usb-Logitech_Webcam-00", "max_input_channels": 2, "max_output_channels": 0, "hostapi": 0},
        ],
    )
    def test_collect_diagnostics_warns_when_no_loopback(self, mock_query_devices, mock_system) -> None:
        config = AudioInputConfig()
        diagnostics = collect_audio_diagnostics(config)
        self.assertIn(
            "ループバック入力候補が検出できませんでした。仮想デバイスやモニターを準備してください。",
            diagnostics.issues,
        )
        mock_query_devices.assert_called()
        mock_system.assert_called()

    @mock.patch("transcriber.audio_setup.subprocess.run")
    @mock.patch(
        "transcriber.audio_setup.AudioEnvironmentManager._detect_loopback_candidate",
        return_value=True,
    )
    @mock.patch(
        "transcriber.audio_setup.sd.query_devices",
        return_value=[{"name": "pipewire", "max_input_channels": 2, "max_output_channels": 2, "hostapi": 0}],
    )
    @mock.patch("transcriber.audio_setup.platform.system", return_value="Linux")
    def test_loopback_setup_skipped_when_flag_set(
        self,
        mock_system,
        mock_query_devices,
        mock_detect,
        mock_subprocess_run,
    ) -> None:
        config = AudioInputConfig()
        manager = AudioEnvironmentManager(config)
        with mock.patch.dict(os.environ, {"AUDIO_LOOPBACK_ALREADY_SET": "1"}, clear=False):
            manager._prepare_loopback()
        mock_subprocess_run.assert_not_called()
        mock_detect.assert_called()


if __name__ == "__main__":
    unittest.main()
