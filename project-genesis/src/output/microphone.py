"""
Microphone Input — M13.

Genesis can listen through the microphone and process spoken input.

Optional — gracefully unavailable if speech_recognition or pyaudio
are not installed. When available, spoken words are transcribed and
fed into Genesis's processing pipeline exactly as text input.

Install: pip install SpeechRecognition pyaudio

The loop:
    Human speaks → mic captures → speech_recognition transcribes
    → Genesis processes as text → GenesisVoice responds

This closes the loop that was previously text-only: Genesis listens,
processes, and speaks back from its own internal state.
"""

from typing import Optional


def is_available() -> bool:
    """Return True if microphone input dependencies are installed."""
    try:
        import speech_recognition  # noqa: F401
        return True
    except ImportError:
        return False


class MicrophoneInput:
    """
    Captures spoken input from the microphone and returns transcribed text.

    Gracefully unavailable if dependencies are not installed.

    Usage:
        mic = MicrophoneInput()
        if mic.available():
            text = mic.listen()   # blocks until speech detected
            if text:
                brain.process_input("text", text)
    """

    def __init__(self, timeout: float = 5.0, phrase_limit: float = 10.0):
        self._timeout = timeout
        self._phrase_limit = phrase_limit
        self._recognizer = None
        self._total_captures = 0
        self._failed_captures = 0
        self._tried_init = False

    def _init(self) -> bool:
        if self._tried_init:
            return self._recognizer is not None
        self._tried_init = True
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            self._sr = sr
            return True
        except ImportError:
            return False

    def available(self) -> bool:
        """Return True if mic input is available on this system."""
        return self._init()

    def listen(self, language: str = "en-US") -> Optional[str]:
        """
        Listen for a single spoken phrase and return the transcription.

        Blocks until speech is detected or timeout is reached.
        Returns None if nothing was heard or transcription failed.
        """
        if not self._init():
            return None
        try:
            sr = self._sr
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self._recognizer.listen(
                    source,
                    timeout=self._timeout,
                    phrase_time_limit=self._phrase_limit,
                )
            text = self._recognizer.recognize_google(audio, language=language)
            self._total_captures += 1
            return text.strip() if text else None
        except Exception:
            self._failed_captures += 1
            return None

    def listen_loop(self, callback, stop_phrase: str = "goodbye genesis"):
        """
        Continuously listen and call callback(text) for each phrase.

        Stops when stop_phrase is spoken or callback returns False.
        """
        if not self.available():
            return

        while True:
            text = self.listen()
            if text is None:
                continue
            if stop_phrase and stop_phrase.lower() in text.lower():
                break
            result = callback(text)
            if result is False:
                break

    def stats(self) -> dict:
        return {
            "available":       self.available(),
            "total_captures":  self._total_captures,
            "failed_captures": self._failed_captures,
        }
