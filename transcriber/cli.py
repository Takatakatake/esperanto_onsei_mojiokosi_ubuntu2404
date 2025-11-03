"""Command line interface for the realtime transcription pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import sounddevice as sd

from .audio_setup import AudioEnvironmentError, run_cli_diagnostics
from .config import BackendChoice, load_settings
from .env_check import run_environment_check
from .pipeline import TranscriptionPipeline
from .setup_wizard import run_setup_wizard


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def list_audio_devices() -> None:
    devices = sd.query_devices()
    for index, device in enumerate(devices):
        io_type = []
        if device["max_input_channels"]:
            io_type.append("IN")
        if device["max_output_channels"]:
            io_type.append("OUT")
        print(f"{index:>3}: {'/'.join(io_type):<7} {device['name']}  ({device['hostapi']})")


def print_settings() -> None:
    settings = load_settings()
    filtered: Dict[str, Any] = {
        "backend": settings.backend.value,
        "audio": settings.audio.model_dump(),
        "zoom": settings.zoom.model_dump(),
        "logging": settings.logging.model_dump(),
        "web": settings.web.model_dump(),
        "discord": settings.discord.model_dump(),
    }
    if settings.speechmatics:
        filtered["speechmatics"] = {
            **settings.speechmatics.model_dump(),
            "api_key": "***redacted***",
        }
    if settings.vosk:
        filtered["vosk"] = settings.vosk.model_dump()
    if settings.whisper:
        filtered["whisper"] = settings.whisper.model_dump()
    translation_dump = settings.translation.model_dump()
    if translation_dump.get("libre_api_key"):
        translation_dump["libre_api_key"] = "***redacted***"
    filtered["translation"] = translation_dump
    print(json.dumps(filtered, indent=2, ensure_ascii=False))


def _capture_linux_defaults() -> Optional[tuple[Optional[str], Optional[str]]]:
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
        return sink, source
    return None


def _restore_linux_defaults(defaults: Optional[tuple[Optional[str], Optional[str]]]) -> None:
    if not defaults:
        return
    sink, source = defaults
    if sink:
        subprocess.run(["pactl", "set-default-sink", sink], check=False)
    if source:
        subprocess.run(["pactl", "set-default-source", source], check=False)


def _list_linux_devices(kind: str) -> List[str]:
    assert kind in {"sinks", "sources"}
    try:
        output = subprocess.check_output(
            ["pactl", "list", "short", kind], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:  # noqa: BLE001
        return []
    names: List[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            names.append(parts[1].strip())
    return names


def _ensure_linux_physical_defaults() -> None:
    try:
        info = subprocess.check_output(
            ["pactl", "info"], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:  # noqa: BLE001
        return

    current_sink: Optional[str] = None
    current_source: Optional[str] = None
    for line in info.splitlines():
        if line.startswith("Default Sink:"):
            current_sink = line.split(":", 1)[1].strip() or None
        elif line.startswith("Default Source:"):
            current_source = line.split(":", 1)[1].strip() or None

    sinks = _list_linux_devices("sinks")
    sources = _list_linux_devices("sources")

    physical_sinks = [n for n in sinks if "codex_transcribe" not in n]
    physical_sources = [
        n for n in sources if ".monitor" not in n and "codex_transcribe" not in n
    ]

    if current_sink and "codex_transcribe" in current_sink and physical_sinks:
        subprocess.run(["pactl", "set-default-sink", physical_sinks[0]], check=False)

    if current_source and (
        "codex_transcribe" in current_source or current_source.endswith(".monitor")
    ):
        if physical_sources:
            subprocess.run(
                ["pactl", "set-default-source", physical_sources[0]], check=False
            )


def _snapshot_linux_modules() -> Dict[str, Set[str]]:
    result: Dict[str, Set[str]] = {"null": set(), "loop": set()}
    try:
        output = subprocess.check_output(
            ["pactl", "list", "short", "modules"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001
        return result

    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        idx, name = parts[0].strip(), parts[1].strip()
        if name == "module-null-sink":
            result["null"].add(idx)
        elif name == "module-loopback":
            result["loop"].add(idx)
    return result


def _unload_linux_modules(modules: Dict[str, Set[str]]) -> None:
    for module_id in modules.get("loop", set()):
        subprocess.run(["pactl", "unload-module", module_id], check=False)
    for module_id in modules.get("null", set()):
        subprocess.run(["pactl", "unload-module", module_id], check=False)


def run_easy_start(
    backend_override: Optional[str] = None,
    log_file_override: Optional[str] = None,
    interactive: bool = True,
) -> bool:
    """Perform ready checks and optionally start the pipeline."""

    ready = run_environment_check()
    if not ready:
        print("環境チェックで問題が見つかりました。表示された項目を修正して再実行してください。")
        return False

    settings = load_settings()
    try:
        run_cli_diagnostics(settings.audio)
    except AudioEnvironmentError as exc:
        print(f"オーディオ環境エラー: {exc}")
        return False

    system = platform.system().lower()
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    script_path: Optional[Path] = None
    command: Optional[list[str]] = None
    defaults_before_script: Optional[tuple[Optional[str], Optional[str]]] = None
    modules_before_script: Optional[Dict[str, Set[str]]] = None
    modules_to_unload: Dict[str, Set[str]] = {"null": set(), "loop": set()}

    if system == "linux":
        script_path = scripts_dir / "setup_audio_loopback_linux.sh"
        command = ["bash", str(script_path)]
        defaults_before_script = _capture_linux_defaults()
        modules_before_script = _snapshot_linux_modules()
    elif system == "darwin":
        script_path = scripts_dir / "setup_audio_loopback_macos.sh"
        command = ["bash", str(script_path)]
    elif system == "windows":
        script_path = scripts_dir / "setup_audio_loopback_windows.ps1"
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]

    if not interactive:
        if defaults_before_script:
            _restore_linux_defaults(defaults_before_script)
        if system == "linux":
            _ensure_linux_physical_defaults()
        return True

    if script_path and script_path.exists() and command:
        answer = input(
            f"{script_path.name} を実行してループバック設定を整えますか？ [y/N]: "
        ).strip().lower()
        if answer in {"y", "yes"}:
            try:
                subprocess.run(command, check=True)
                if system == "linux":
                    modules_after = _snapshot_linux_modules()
                    if modules_before_script is None:
                        modules_before_script = {"null": set(), "loop": set()}
                    modules_to_unload["null"] = modules_after["null"] - modules_before_script.get("null", set())
                    modules_to_unload["loop"] = modules_after["loop"] - modules_before_script.get("loop", set())
            except Exception as exc:  # noqa: BLE001
                print(f"スクリプト実行中に問題が発生しました: {exc}")
                if defaults_before_script:
                    _restore_linux_defaults(defaults_before_script)
                if system == "linux":
                    modules_after = _snapshot_linux_modules()
                    if modules_before_script is None:
                        modules_before_script = {"null": set(), "loop": set()}
                    modules_to_unload["null"] = modules_after["null"] - modules_before_script.get("null", set())
                    modules_to_unload["loop"] = modules_after["loop"] - modules_before_script.get("loop", set())
                    _unload_linux_modules(modules_to_unload)
                return False
        else:
            defaults_before_script = None
            modules_before_script = None

    start = input("環境準備が整いました。文字起こしを今すぐ開始しますか？ [Y/n]: ").strip().lower()
    headphone_env_previous: Optional[str] = None
    loopback_flag_previous: Optional[str] = None
    if start in {"", "y", "yes"}:
        try:
            if system == "linux":
                if defaults_before_script:
                    sink_hint = defaults_before_script[0]
                    if sink_hint:
                        headphone_env_previous = os.environ.get("HEADPHONE_SINK")
                        os.environ["HEADPHONE_SINK"] = sink_hint
                loopback_flag_previous = os.environ.get("AUDIO_LOOPBACK_ALREADY_SET")
                os.environ["AUDIO_LOOPBACK_ALREADY_SET"] = "1"
            asyncio.run(run_pipeline(backend_override, log_file_override))
        finally:
            if defaults_before_script:
                _restore_linux_defaults(defaults_before_script)
            if system == "linux":
                if headphone_env_previous is not None:
                    os.environ["HEADPHONE_SINK"] = headphone_env_previous
                else:
                    os.environ.pop("HEADPHONE_SINK", None)
                if loopback_flag_previous is not None:
                    os.environ["AUDIO_LOOPBACK_ALREADY_SET"] = loopback_flag_previous
                else:
                    os.environ.pop("AUDIO_LOOPBACK_ALREADY_SET", None)
                _unload_linux_modules(modules_to_unload)
                _ensure_linux_physical_defaults()
    else:
        print("パイプラインの起動をスキップしました。`python -m transcriber.cli --log-level=INFO` でいつでも開始できます。")
        if defaults_before_script:
            _restore_linux_defaults(defaults_before_script)
        if system == "linux":
            os.environ.pop("AUDIO_LOOPBACK_ALREADY_SET", None)
            os.environ.pop("HEADPHONE_SINK", None)
            _unload_linux_modules(modules_to_unload)
            _ensure_linux_physical_defaults()
    return True


async def run_pipeline(
    backend_override: Optional[str] = None, log_file_override: Optional[str] = None
) -> None:
    settings = load_settings()
    pipeline = TranscriptionPipeline(
        settings,
        backend_override=backend_override,
        transcript_log_override=log_file_override,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_stop(*_args):
        logging.info("Received stop signal, shutting down.")
        stop_event.set()

    def handle_suspend(*_args):
        logging.warning(
            "Ctrl+Z (suspend) detected; cleaning up instead of leaving audio in a loopback state."
        )
        handle_stop()

    loop.add_signal_handler(signal.SIGINT, handle_stop)
    loop.add_signal_handler(signal.SIGTERM, handle_stop)
    if hasattr(signal, "SIGTSTP"):
        try:
            loop.add_signal_handler(signal.SIGTSTP, handle_suspend)
        except (NotImplementedError, RuntimeError):
            logging.debug("SIGTSTP handler not supported on this platform.")

    run_task = asyncio.create_task(pipeline.run())
    await stop_event.wait()
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        logging.info("Pipeline task cancelled.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Realtime Esperanto transcription using Speechmatics and Zoom captions."
    )
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit.")
    parser.add_argument(
        "--show-config", action="store_true", help="Print loaded configuration and exit."
    )
    parser.add_argument(
        "--diagnose-audio",
        action="store_true",
        help="Run audio environment diagnostics and exit.",
    )
    parser.add_argument(
        "--check-environment",
        action="store_true",
        help="Run dependency/configuration readiness checks and exit.",
    )
    parser.add_argument(
        "--setup-wizard",
        action="store_true",
        help="Show guided setup steps tailored to the detected OS.",
    )
    parser.add_argument(
        "--easy-start",
        action="store_true",
        help="Run environment checks and optionally launch transcription with minimal prompts.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    parser.add_argument(
        "--backend",
        choices=[choice.value for choice in BackendChoice],
        help="Override transcription backend selection.",
    )
    parser.add_argument(
        "--log-file",
        help="Override transcript log file output path.",
    )
    args = parser.parse_args()

    configure_logging(args.log_level)

    if args.list_devices:
        list_audio_devices()
        return

    if args.show_config:
        print_settings()
        return

    if args.diagnose_audio:
        try:
            run_cli_diagnostics(load_settings().audio)
        except AudioEnvironmentError as exc:
            print(f"オーディオ環境エラー: {exc}")
        return

    if args.check_environment:
        ready = run_environment_check()
        if not ready:
            sys.exit(1)
        return

    if args.setup_wizard:
        run_setup_wizard()
        return

    if args.easy_start:
        run_easy_start(args.backend, args.log_file)
        return

    asyncio.run(run_pipeline(args.backend, args.log_file))


if __name__ == "__main__":
    main()
