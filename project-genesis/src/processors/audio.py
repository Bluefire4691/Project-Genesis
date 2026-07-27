"""
Audio sensory processor — M35 rich-input modality.

Extracts structure from raw sound the way Genesis extracts structure from
everything: with no pretrained knowledge.  A newborn auditory system doesn't
know what a word is — it notices loudness, rhythm, brightness, repetition.
That is exactly what this processor reports, computed from the raw samples
with the stdlib only (wave + math): no ML models, no learned weights, which
keeps the blank-start individuality claim intact for hearing too.

What it measures per recording:
  - duration, loudness (RMS), dynamic range, silence ratio
  - loudness envelope over time → trend (rising / falling / steady)
  - onset events (bursts above the ambient floor) → event rate
  - rhythm: autocorrelation of the envelope → dominant period, tempo
    estimate (BPM) and a regularity score (how metronomic it is)
  - timbre brightness via zero-crossing rate (bright vs dark)

The extraction feeds the normal pipeline: findings become memory + archive
entries, the envelope series is shaped so the PatternProcessor can vote on
it (cross-modal confirmation), and structural observations are emitted as
typed relation triples via the modality-agnostic extracted["relations"]
hook — sound becomes part of the same graph Genesis reasons over.

Input forms accepted:
    "path/to/file.wav"
    {"path": "...", "label": "rain on window"}
    {"samples": [floats -1..1], "rate": 16000, "label": "..."}
"""

import math
import os
import wave
from typing import Any

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput
from processors.base import BaseProcessor

# Envelope analysis windows per recording — enough to see shape, cheap to sort
_N_WINDOWS = 48

# A window is an "onset" when its RMS jumps this far above the running floor
_ONSET_RATIO = 2.0

# Rhythm regularity above this counts as "steady rhythm"
_REGULAR_MIN = 0.55


class AudioProcessor(BaseProcessor):
    name = "audio"

    # ------------------------------------------------------------------
    # Decode
    # ------------------------------------------------------------------

    def _load(self, data: Any) -> tuple[list[float], int, str]:
        """Return (samples -1..1 mono, sample_rate, label)."""
        if isinstance(data, dict) and "samples" in data:
            return (list(data["samples"]),
                    int(data.get("rate", 16000)),
                    str(data.get("label", "sound")))

        path = data.get("path") if isinstance(data, dict) else str(data)
        label = (data.get("label") if isinstance(data, dict) else None) \
            or os.path.splitext(os.path.basename(str(path)))[0].replace("_", " ")

        with wave.open(str(path), "rb") as wf:
            rate     = wf.getframerate()
            n_chan   = wf.getnchannels()
            width    = wf.getsampwidth()
            raw      = wf.readframes(wf.getnframes())

        # Decode PCM to floats; mixdown to mono
        if width == 2:
            import array
            ints = array.array("h")
            ints.frombytes(raw)
            scale = 32768.0
        elif width == 1:
            ints = [b - 128 for b in raw]
            scale = 128.0
        else:                       # 24/32-bit: take high 16 bits
            import array
            ints = array.array("h")
            step = width
            ints.frombytes(b"".join(
                raw[i + width - 2: i + width]
                for i in range(0, len(raw) - width + 1, step)))
            scale = 32768.0

        if n_chan > 1:
            mono = [sum(ints[i:i + n_chan]) / n_chan / scale
                    for i in range(0, len(ints) - n_chan + 1, n_chan)]
        else:
            mono = [v / scale for v in ints]
        return mono, rate, label

    # ------------------------------------------------------------------
    # Analysis (stdlib only, no learned weights)
    # ------------------------------------------------------------------

    @staticmethod
    def _rms(xs: list[float]) -> float:
        return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else 0.0

    def _envelope(self, samples: list[float]) -> list[float]:
        n = max(1, len(samples) // _N_WINDOWS)
        return [self._rms(samples[i:i + n])
                for i in range(0, len(samples), n)][:_N_WINDOWS]

    @staticmethod
    def _zero_cross_rate(samples: list[float]) -> float:
        if len(samples) < 2:
            return 0.0
        crossings = sum(1 for a, b in zip(samples, samples[1:])
                        if (a >= 0) != (b >= 0))
        return crossings / (len(samples) - 1)

    @staticmethod
    def _trend(env: list[float]) -> str:
        if len(env) < 4:
            return "steady"
        half = len(env) // 2
        first, second = sum(env[:half]) / half, sum(env[half:]) / (len(env) - half)
        if second > first * 1.35:
            return "rising"
        if second < first * 0.65:
            return "falling"
        return "steady"

    def _rhythm(self, env: list[float], win_dur: float) -> tuple[float, float]:
        """(tempo_bpm, regularity 0..1) from envelope autocorrelation."""
        n = len(env)
        if n < 8:
            return 0.0, 0.0
        mean = sum(env) / n
        dev = [e - mean for e in env]
        denom = sum(d * d for d in dev) or 1e-9
        best_lag, best_r = 0, 0.0
        for lag in range(2, n // 2):
            r = sum(dev[i] * dev[i + lag] for i in range(n - lag)) / denom
            if r > best_r:
                best_lag, best_r = lag, r
        if best_lag == 0:
            return 0.0, 0.0
        period_s = best_lag * win_dur
        bpm = 60.0 / period_s if period_s > 0 else 0.0
        return round(bpm, 1), round(max(0.0, min(1.0, best_r)), 2)

    # ------------------------------------------------------------------
    # Processor interface
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_audio(data: Any) -> bool:
        if isinstance(data, dict):
            return "samples" in data or "path" in data
        if isinstance(data, (str, os.PathLike)):
            return str(data).lower().endswith((".wav", ".wave"))
        return False

    def _process(self, data: Any) -> ProcessorOutput:
        # All processors see all input; quietly pass on non-audio rather
        # than storing an error memory every text cycle.
        if not self._looks_like_audio(data):
            return ProcessorOutput(
                source=self.name, input_data=None,
                extracted={"skipped": "not audio input"},
                importance=0.0, suggested_key="audio:none",
                context="", confidence=0.0,
            )
        samples, rate, label = self._load(data)
        duration = len(samples) / rate if rate else 0.0

        env      = self._envelope(samples)
        win_dur  = duration / max(1, len(env))
        loudness = self._rms(samples)
        peak     = max((abs(s) for s in samples), default=0.0)
        floor    = sorted(env)[max(0, len(env) // 5)] if env else 0.0
        silence  = (sum(1 for e in env if e < max(0.005, floor * 0.5))
                    / len(env)) if env else 1.0
        onsets   = sum(
            1 for a, b in zip(env, env[1:])
            if b > max(0.01, a * _ONSET_RATIO)
        )
        event_rate = round(onsets / duration, 2) if duration else 0.0
        trend      = self._trend(env)
        bpm, regularity = self._rhythm(env, win_dur)
        zcr        = self._zero_cross_rate(samples)
        timbre     = "bright" if zcr > 0.08 else "dark"
        rhythmic   = regularity >= _REGULAR_MIN and bpm > 0

        # Structural observations become graph relations — hearing feeds the
        # same substrate everything else does.  Confidences are honest about
        # signal analysis being approximate.
        key  = f"audio:{label.replace(' ', '_')}"
        relations = [
            {"subject": label, "relation": "IS_A",
             "object": "sound recording", "confidence": 0.9},
            {"subject": label, "relation": "CONTAINS",
             "object": f"{timbre} timbre", "confidence": 0.6},
        ]
        if rhythmic:
            relations.append(
                {"subject": label, "relation": "CONTAINS",
                 "object": "steady rhythm", "confidence": 0.5 + regularity / 2})
        if event_rate > 1.0:
            relations.append(
                {"subject": label, "relation": "CONTAINS",
                 "object": "frequent sound events", "confidence": 0.6})

        rhythm_part = (f", steady rhythm ~{bpm:.0f} bpm" if rhythmic
                       else ", irregular timing")
        context = (
            f"Audio '{label}': {duration:.1f}s, {timbre} timbre, "
            f"{trend} loudness, {onsets} onset event(s)"
            f"{rhythm_part}, {silence:.0%} near-silence"
        )

        extracted = {
            "label":       label,
            "duration_s":  round(duration, 2),
            "sample_rate": rate,
            "loudness":    round(loudness, 4),
            "peak":        round(peak, 4),
            "silence_ratio": round(silence, 2),
            "envelope":    [round(e, 4) for e in env],
            "trend":       trend,
            "onsets":      onsets,
            "event_rate":  event_rate,
            "tempo_bpm":   bpm,
            "regularity":  regularity,
            "zero_cross_rate": round(zcr, 4),
            "timbre":      timbre,
            "relations":   relations,
            # Shaped for the NumericProcessor/PatternProcessor voting path
            "values":      [round(e, 4) for e in env],
        }

        # Structured sound (rhythm, events, dynamics) matters more than hiss
        importance = min(1.0, 0.35 + regularity * 0.3
                         + min(0.2, event_rate / 10) + (0.1 if trend != "steady" else 0))

        return ProcessorOutput(
            source=self.name,
            input_data={"label": label, "duration_s": round(duration, 2)},
            extracted=extracted,
            importance=round(importance, 2),
            suggested_key=key,
            context=context,
        )
