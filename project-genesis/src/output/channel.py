"""
Output Channels — M13.

Genesis can express itself through any channel available on the hardware.
Channels are pluggable: if a dependency isn't installed, that channel
degrades gracefully to the next available one.

Priority order:
    AudioChannel (pyttsx3)  → speaks aloud
    TextChannel             → prints to stdout (always available)

Usage:
    channel = OutputChannel.best_available()
    channel.send("overgrazing causes erosion")

Channels are not responsible for generating the content — that is
GenesisVoice's job. Channels are responsible for delivery.
"""

import sys
from abc import ABC, abstractmethod


class OutputChannel(ABC):
    """Base class for all Genesis output channels."""

    @abstractmethod
    def send(self, text: str) -> None:
        """Deliver text through this channel."""

    @abstractmethod
    def available(self) -> bool:
        """Return True if this channel can currently deliver output."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable channel name."""

    @staticmethod
    def best_available(prefer_audio: bool = True) -> "OutputChannel":
        """
        Return the best available channel.

        Tries AudioChannel first (if prefer_audio=True and pyttsx3 installed),
        falls back to TextChannel.
        """
        if prefer_audio:
            audio = AudioChannel()
            if audio.available():
                return audio
        return TextChannel()

    @staticmethod
    def all_available() -> list["OutputChannel"]:
        """Return all channels that can currently deliver output."""
        channels = []
        audio = AudioChannel()
        if audio.available():
            channels.append(audio)
        channels.append(TextChannel())
        return channels


class TextChannel(OutputChannel):
    """
    Always-available text output to stdout.

    Genesis's baseline output mode. Never fails. If all other channels
    are unavailable, text is always possible.
    """

    def __init__(self, prefix: str = "[Genesis] "):
        self._prefix = prefix

    def send(self, text: str) -> None:
        print(f"{self._prefix}{text}", flush=True)

    def available(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "text"


class AudioChannel(OutputChannel):
    """
    Text-to-speech output via pyttsx3.

    Optional — gracefully unavailable if pyttsx3 is not installed.
    pyttsx3 works offline; no API calls, no internet required.

    Install: pip install pyttsx3
    """

    def __init__(self, rate: int = 150, volume: float = 0.9):
        self._engine = None
        self._rate = rate
        self._volume = volume
        self._tried_init = False

    def _init_engine(self):
        if self._tried_init:
            return
        self._tried_init = True
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
            engine.setProperty("volume", self._volume)
            self._engine = engine
        except Exception:
            self._engine = None

    def send(self, text: str) -> None:
        self._init_engine()
        if self._engine is None:
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            self._engine = None  # mark failed, won't retry

    def available(self) -> bool:
        self._init_engine()
        return self._engine is not None

    @property
    def name(self) -> str:
        return "audio"


class NullChannel(OutputChannel):
    """Silences all output — used by the UI to capture expressions via queue."""

    def send(self, text: str) -> None:
        pass

    def available(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "null"


class MultiChannel(OutputChannel):
    """Broadcasts to multiple channels simultaneously."""

    def __init__(self, channels: list[OutputChannel]):
        self._channels = [c for c in channels if c.available()]

    def send(self, text: str) -> None:
        for channel in self._channels:
            try:
                channel.send(text)
            except Exception:
                pass

    def available(self) -> bool:
        return bool(self._channels)

    @property
    def name(self) -> str:
        return "+".join(c.name for c in self._channels)
