"""Interactive-style guidance for first-time setup."""

from __future__ import annotations

import platform


def _print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _print_steps(title: str, steps: list[str]) -> None:
    _print_header(title)
    for idx, step in enumerate(steps, 1):
        print(f"{idx}. {step}")


def run_setup_wizard() -> None:
    """Display step-by-step instructions for the detected OS."""

    system = platform.system().lower()

    common_steps = [
        "Create/activate your Python 3.11 virtual environment (.venv311).",
        "Run `python -m pip install -r requirements.txt` with the venv active.",
        "Copy `.env.example` to `.env` and fill in API keys (Speechmatics, Google, etc.).",
        "Execute `python -m transcriber.cli --check-environment` to verify dependencies/files.",
        "Adjust `AUDIO_DEVICE_INDEX`, `AUDIO_DEVICE_SAMPLE_RATE`, and translation targets as needed.",
    ]

    _print_steps("共通ステップ / Common steps", common_steps)

    if system == "windows":
        windows_steps = [
            "Install a loopback driver (VB-Audio Virtual Cable or VoiceMeeter).",
            "Launch an elevated PowerShell and run `scripts\\check_environment.py` for a quick health check.",
            "Run `powershell -ExecutionPolicy Bypass -File scripts\\setup_audio_loopback_windows.ps1` "
            "to list Stereo Mix / VB-Audio devices. The script opens the Recording tab if nothing matches.",
            "Set `AUDIO_DEVICE_INDEX` to the loopback device number from `python -m transcriber.cli --list-devices`.",
            "Execute `python -m transcriber.cli --diagnose-audio` to ensure the loopback path is detected.",
            "Start the pipeline with `python -m transcriber.cli --log-level=INFO` (or use your existing 起動.bat equivalent).",
        ]
        _print_steps("Windows setup hints", windows_steps)
    elif system == "darwin":
        mac_steps = [
            "Install Homebrew if needed (`/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"`).",
            "Install BlackHole 2ch via `brew install blackhole-2ch` and create a Multi-Output Device in Audio MIDI Setup (headphones + BlackHole).",
            "Run `scripts/setup_audio_loopback_macos.sh` to confirm the driver is detected.",
            "Leave `AUDIO_DEVICE_INDEX` unset to use the default, or specify the BlackHole monitor explicitly.",
            "Run `python -m transcriber.cli --diagnose-audio` to verify that BlackHole appears as a loopback candidate.",
            "Launch the pipeline: `python -m transcriber.cli --log-level=INFO`.",
        ]
        _print_steps("macOS setup hints", mac_steps)
    elif system == "linux":
        linux_steps = [
            "Confirm PipeWire/PulseAudio is running (`pactl info`).",
            "Run `scripts/setup_audio_loopback_linux.sh` (optionally set HEADPHONE_SINK) to create the virtual sink; defaults are restored automatically on exit.",
            "Set `AUDIO_DEVICE_SAMPLE_RATE` to your hardware rate (48kHz is common) and leave `AUDIO_DEVICE_INDEX` blank to use the monitor.",
            "Run `python -m transcriber.cli --diagnose-audio` to ensure `pipewire` or `default` monitors are recognised.",
            "If you prefer a fixed device, capture its index with `--list-devices` and set `.env` accordingly.",
            "Start the pipeline with `python -m transcriber.cli --log-level=INFO`.",
        ]
        _print_steps("Linux setup hints", linux_steps)
    else:
        generic_steps = [
            "Install or enable an audio-loopback mechanism appropriate for your OS.",
            "Use `python -m transcriber.cli --list-devices` to locate monitor inputs.",
            "Configure `.env` following the common steps and re-run `--diagnose-audio` until the loopback is recognised.",
            "Launch the pipeline once audio routing is confirmed.",
        ]
        _print_steps(f"{system} setup hints", generic_steps)

    _print_header("Next actions")
    print("• Run `python -m transcriber.cli --diagnose-audio` whenever routing changes.")
    print("• Use `python -m transcriber.cli --setup-wizard` again if you switch OS or hardware.")
    print("• Refer to docs/audio_loopback.md and README for deeper troubleshooting tips.")
