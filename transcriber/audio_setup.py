"""Helpers for preparing and diagnosing audio capture environments."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

import sounddevice as sd

from .config import AudioCaptureMode, AudioInputConfig


class AudioEnvironmentError(Exception):
    """Raised when the audio capture environment cannot be prepared."""


@dataclass
class AudioDeviceSummary:
    """Represents an audio device entry for diagnostics."""

    index: int
    name: str
    hostapi: str
    inputs: int
    outputs: int
    default_samplerate: Optional[float]


@dataclass
class AudioDiagnosticReport:
    """Aggregated view of the current audio environment."""

    platform: str
    mode: AudioCaptureMode
    input_devices: List[AudioDeviceSummary]
    loopback_candidates: List[AudioDeviceSummary]
    configured_device: Optional[AudioDeviceSummary]
    issues: List[str]
    recommendations: List[str]


class AudioEnvironmentManager:
    """Prepare platform-specific audio routing based on configuration."""

    def __init__(self, config: AudioInputConfig) -> None:
        self._config = config
        self._platform = platform.system().lower()
        self._repo_root = Path(__file__).resolve().parent.parent
        self._scripts_dir = self._repo_root / "scripts"
        self._cleanup_actions: List[Callable[[], None]] = []

    def prepare(self) -> None:
        """Ensure the selected capture mode has a viable device or routing."""

        mode = resolve_capture_mode(self._config)
        logging.debug("Preparing audio environment for mode=%s", mode.value)

        self._cleanup_actions.clear()

        self._ensure_device_presence()

        if mode is AudioCaptureMode.MICROPHONE:
            return

        if mode is AudioCaptureMode.API:
            logging.info(
                "Audio capture mode set to 'api'. Ensure external media ingestion is configured."
            )
            return

        if mode is AudioCaptureMode.LOOPBACK:
            self._prepare_loopback()
            return

    def cleanup(self) -> None:
        """Rollback any environment changes performed during prepare()."""

        while self._cleanup_actions:
            action = self._cleanup_actions.pop()
            try:
                action()
            except Exception as exc:  # noqa: BLE001
                logging.warning("Audio environment cleanup failed: %s", exc)

    def _ensure_device_presence(self) -> None:
        try:
            devices = sd.query_devices()
        except Exception as exc:  # noqa: BLE001
            raise AudioEnvironmentError(f"Failed to enumerate audio devices: {exc}") from exc

        if not devices:
            raise AudioEnvironmentError("No audio devices detected by PortAudio.")

        if self._config.device_index is not None:
            index = self._config.device_index
            if index < 0 or index >= len(devices):
                raise AudioEnvironmentError(
                    f"Configured AUDIO_DEVICE_INDEX {index} is outside the available range (0-{len(devices)-1})."
                )
            device = devices[index]
            if device.get("max_input_channels", 0) <= 0:
                raise AudioEnvironmentError(
                    f"Configured device '{device.get('name', index)}' has no input channels."
                )
            logging.debug(
                "Audio device index %s resolved to '%s' (inputs=%s).",
                index,
                device.get("name", index),
                device.get("max_input_channels"),
            )
        else:
            if not any(dev.get("max_input_channels", 0) > 0 for dev in devices):
                raise AudioEnvironmentError("No input-capable audio devices detected.")

    def _prepare_loopback(self) -> None:
        if self._platform == "linux":
            self._prepare_linux_loopback()
        elif self._platform == "windows":
            self._prepare_windows_loopback()
        elif self._platform == "darwin":
            self._prepare_macos_loopback()
        else:
            logging.warning(
                "Loopback capture not explicitly supported on platform '%s'. Ensure routing manually.",
                self._platform,
            )

    def _prepare_linux_loopback(self) -> None:
        if not shutil.which("pactl"):
            logging.warning(
                "pactl not found; cannot auto-configure PipeWire/PulseAudio loopback. "
                "Ensure a monitor source is selected manually."
            )
            return

        capture_defaults: Optional[tuple[Optional[str], Optional[str]]] = None
        if os.environ.get("AUDIO_LOOPBACK_ALREADY_SET") == "1":
            logging.debug("Loopback already set by launcher; verifying availability only.")
            if self._config.device_index is None and not self._detect_loopback_candidate({"monitor", "loopback"}):
                raise AudioEnvironmentError(
                    "Loopback auto-setup flag set but no monitor source detected."
                )
            return

        if self._config.auto_setup_loopback:
            capture_defaults = self._get_linux_defaults()
            if capture_defaults:
                self._register_linux_defaults_restore(capture_defaults)

            script = self._scripts_dir / "setup_audio_loopback_linux.sh"
            if script.is_file():
                env = os.environ.copy()
                if self._config.linux_loopback_sink:
                    env["HEADPHONE_SINK"] = self._config.linux_loopback_sink
                try:
                    subprocess.run(["bash", str(script)], check=True, env=env)
                except subprocess.CalledProcessError as exc:
                    raise AudioEnvironmentError(
                        "Failed to initialise PipeWire virtual loopback (setup_audio_loopback_linux.sh)."
                    ) from exc
            else:
                logging.debug(
                    "Loopback helper script not found at %s; skipping auto-setup.", script
                )
        if not self._detect_loopback_candidate({"monitor", "loopback"}):
            if self._config.device_index is None:
                raise AudioEnvironmentError(
                    "No loopback-capable input detected after setup. "
                    "Verify that a monitor source is available and not muted."
                )
            logging.debug(
                "Loopback candidates not found, but AUDIO_DEVICE_INDEX=%s is configured; continuing.",
                self._config.device_index,
            )

    def _get_linux_defaults(self) -> Optional[tuple[Optional[str], Optional[str]]]:
        try:
            output = subprocess.check_output(["pactl", "info"], text=True, stderr=subprocess.DEVNULL)
        except Exception:  # noqa: BLE001
            return None

        sink = None
        source = None
        for line in output.splitlines():
            if line.startswith("Default Sink:"):
                sink = line.split(":", 1)[1].strip() or None
            elif line.startswith("Default Source:"):
                source = line.split(":", 1)[1].strip() or None
        if sink or source:
            return (sink, source)
        return None

    def _register_linux_defaults_restore(
        self, defaults: tuple[Optional[str], Optional[str]]
    ) -> None:
        sink, source = defaults

        def restore(sink_name: Optional[str] = sink, source_name: Optional[str] = source) -> None:
            if sink_name:
                subprocess.run(["pactl", "set-default-sink", sink_name], check=False)
            if source_name:
                subprocess.run(["pactl", "set-default-source", source_name], check=False)

        self._cleanup_actions.append(restore)

    def _prepare_windows_loopback(self) -> None:
        if self._config.auto_setup_loopback:
            script = self._scripts_dir / "setup_audio_loopback_windows.ps1"
            powershell = shutil.which("powershell")
            if script.is_file() and powershell:
                try:
                    subprocess.run(
                        [
                            powershell,
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-File",
                            str(script),
                        ],
                        check=True,
                    )
                except subprocess.CalledProcessError as exc:
                    logging.warning(
                        "Windows loopback helper exited with code %s. Continuing with verification.",
                        exc.returncode,
                    )
            else:
                logging.debug(
                    "Skipping Windows loopback helper (script=%s, powershell=%s).",
                    script.exists(),
                    bool(powershell),
                )

        if self._config.device_index is None and not self._detect_loopback_candidate(
            {"loopback", "stereo mix", "cable output", "cable input", "virtual"}
        ):
            raise AudioEnvironmentError(
                "No Windows loopback-capable input detected. "
                "Configure 'Stereo Mix', WASAPI loopback, or a virtual cable."
            )

    def _prepare_macos_loopback(self) -> None:
        if self._config.auto_setup_loopback:
            script = self._scripts_dir / "setup_audio_loopback_macos.sh"
            if script.is_file():
                try:
                    subprocess.run(["bash", str(script)], check=True)
                except subprocess.CalledProcessError as exc:
                    logging.warning(
                        "macOS loopback helper exited with code %s. Continuing with verification.",
                        exc.returncode,
                    )
            else:
                logging.debug("macOS loopback helper script not found at %s.", script)

        if self._config.device_index is None and not self._detect_loopback_candidate(
            {"blackhole", "loopback", "soundflower", "aggregate", "multi-output"}
        ):
            raise AudioEnvironmentError(
                "No macOS loopback device detected. Install BlackHole or create an aggregate device."
            )

    def _detect_loopback_candidate(self, keywords: Iterable[str]) -> bool:
        try:
            devices = sd.query_devices()
        except Exception as exc:  # noqa: BLE001
            raise AudioEnvironmentError(f"Failed to enumerate audio devices: {exc}") from exc

        keyword_set = {kw.lower() for kw in keywords}
        sink_hint = (
            self._config.linux_loopback_sink.lower()
            if self._platform == "linux" and self._config.linux_loopback_sink
            else None
        )

        for index, device in enumerate(devices):
            inputs = device.get("max_input_channels", 0)
            if inputs <= 0:
                continue

            name = device.get("name", "").lower()
            is_candidate = any(keyword in name for keyword in keyword_set)

            if self._platform == "linux":
                if not is_candidate and sink_hint and sink_hint in name:
                    is_candidate = True
                if not is_candidate and name in {"pipewire", "default"} and inputs >= 2:
                    is_candidate = True
            elif self._platform == "windows":
                if not is_candidate and "loopback" in name and "wasapi" in name:
                    is_candidate = True
            elif self._platform == "darwin":
                if not is_candidate and "blackhole" in name:
                    is_candidate = True

            if is_candidate:
                logging.debug(
                    "Detected loopback candidate #%s: %s (inputs=%s)",
                    index,
                    device.get("name", index),
                    inputs,
                )
                return True

        return False


def _hostapi_name(index: int) -> str:
    try:
        hostapis = sd.query_hostapis()
        if 0 <= index < len(hostapis):
            return hostapis[index].get("name", str(index))
    except Exception:  # noqa: BLE001
        return str(index)
    return str(index)


def _summarise_devices(devices: List[dict]) -> List[AudioDeviceSummary]:
    summaries: List[AudioDeviceSummary] = []
    for idx, device in enumerate(devices):
        summaries.append(
            AudioDeviceSummary(
                index=idx,
                name=device.get("name", f"Device {idx}"),
                hostapi=_hostapi_name(device.get("hostapi", -1)),
                inputs=device.get("max_input_channels", 0),
                outputs=device.get("max_output_channels", 0),
                default_samplerate=device.get("default_samplerate"),
            )
        )
    return summaries


def collect_audio_diagnostics(config: AudioInputConfig) -> AudioDiagnosticReport:
    """Gather cross-platform audio diagnostics for the current configuration."""

    try:
        devices = sd.query_devices()
    except Exception as exc:  # noqa: BLE001
        raise AudioEnvironmentError(f"Failed to enumerate audio devices: {exc}") from exc

    input_devices = [dev for dev in devices if dev.get("max_input_channels", 0) > 0]
    summaries = _summarise_devices(devices)
    input_summaries = [summaries[idx] for idx, dev in enumerate(devices) if dev in input_devices]

    loopback_keywords = {
        "linux": {"monitor", "loopback"},
        "windows": {"loopback", "stereo mix", "cable output", "cable input", "virtual"},
        "darwin": {"blackhole", "loopback", "soundflower", "aggregate", "multi-output"},
    }
    platform_key = platform.system().lower()
    loopback_candidates: List[AudioDeviceSummary] = []
    keywords = loopback_keywords.get(platform_key, set())
    keyword_set = {kw.lower() for kw in keywords}
    sink_hint = (
        config.linux_loopback_sink.lower()
        if platform_key == "linux" and config.linux_loopback_sink
        else None
    )
    for summary in input_summaries:
        lowered = summary.name.lower()
        is_candidate = any(keyword in lowered for keyword in keyword_set)
        if platform_key == "linux":
            if not is_candidate and sink_hint and sink_hint in lowered:
                is_candidate = True
            if not is_candidate and lowered in {"pipewire", "default"} and summary.inputs >= 2:
                is_candidate = True
        elif platform_key == "windows":
            if not is_candidate and "loopback" in lowered and "wasapi" in lowered:
                is_candidate = True
        elif platform_key == "darwin":
            if not is_candidate and "blackhole" in lowered:
                is_candidate = True

        if is_candidate:
            loopback_candidates.append(summary)

    configured_device: Optional[AudioDeviceSummary] = None
    if config.device_index is not None:
        if 0 <= config.device_index < len(summaries):
            configured_device = summaries[config.device_index]

    effective_mode = resolve_capture_mode(config)

    issues: List[str] = []
    if not input_summaries:
        issues.append("入力デバイスが見つかりませんでした。サウンド設定を確認してください。")

    recommendations: List[str] = []
    if config.device_index is None and input_summaries:
        recommendations.append(
            "AUDIO_DEVICE_INDEX を設定するとデバイス切り替えの影響を受けにくくなります。"
        )
    if effective_mode is AudioCaptureMode.LOOPBACK and not loopback_candidates:
        if config.device_index is None:
            issues.append("ループバック入力候補が検出できませんでした。仮想デバイスやモニターを準備してください。")
        else:
            recommendations.append(
                "現在の AUDIO_DEVICE_INDEX がループバック経路を指しているかオーディオ設定で確認してください。"
            )
    if effective_mode is AudioCaptureMode.LOOPBACK and loopback_candidates:
        names = ", ".join(candidate.name for candidate in loopback_candidates[:3])
        recommendations.append(f"ループバック候補: {names}")

    return AudioDiagnosticReport(
        platform=platform.system(),
        mode=effective_mode,
        input_devices=input_summaries,
        loopback_candidates=loopback_candidates,
        configured_device=configured_device,
        issues=issues,
        recommendations=recommendations,
    )


def render_diagnostic_report(report: AudioDiagnosticReport) -> str:
    """Render a diagnostic report into a human-friendly multi-line string."""

    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  オーディオ診断レポート")
    lines.append("=" * 60)
    lines.append(f"プラットフォーム: {report.platform}")
    lines.append(f"キャプチャモード: {report.mode.value}")
    lines.append("")

    lines.append("[入力デバイス一覧]")
    if not report.input_devices:
        lines.append("  (入力デバイスなし)")
    else:
        for device in report.input_devices:
            lines.append(
                f"  #{device.index:>3}: {device.name} | {device.inputs}ch in / {device.outputs}ch out | {device.hostapi}"
            )

    if report.configured_device:
        lines.append("")
        lines.append(
            f"設定済みデバイス: #{report.configured_device.index} {report.configured_device.name}"
        )

    lines.append("")
    lines.append("[ループバック候補]")
    if not report.loopback_candidates:
        lines.append("  (候補なし)")
    else:
        for candidate in report.loopback_candidates:
            lines.append(f"  #{candidate.index:>3}: {candidate.name}")

    if report.issues:
        lines.append("")
        lines.append("[課題]")
        for issue in report.issues:
            lines.append(f"  - {issue}")

    if report.recommendations:
        lines.append("")
        lines.append("[推奨事項]")
        for recommendation in report.recommendations:
            lines.append(f"  - {recommendation}")

    lines.append("")
    lines.append("詳細なルーティング手順は docs/audio_loopback.md を参照してください。")
    return "\n".join(lines)


def run_cli_diagnostics(config: AudioInputConfig) -> None:
    """Execute diagnostics and print the rendered report."""

    report = collect_audio_diagnostics(config)
    output = render_diagnostic_report(report)
    print(output)


def resolve_capture_mode(config: AudioInputConfig) -> AudioCaptureMode:
    """Derive the effective capture mode given configuration and platform defaults."""

    if config.mode is AudioCaptureMode.AUTO:
        system = platform.system().lower()
        if system in {"linux", "windows", "darwin"}:
            return AudioCaptureMode.LOOPBACK
        return AudioCaptureMode.MICROPHONE
    return config.mode
def resolve_capture_mode(config: AudioInputConfig) -> AudioCaptureMode:
    """Derive the effective capture mode given configuration and platform defaults."""

    if config.mode is AudioCaptureMode.AUTO:
        system = platform.system().lower()
        if system in {"linux", "windows", "darwin"}:
            return AudioCaptureMode.LOOPBACK
        return AudioCaptureMode.MICROPHONE
    return config.mode
