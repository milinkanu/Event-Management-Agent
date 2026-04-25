"""
Transcript Processor — parses raw conferencing transcripts into clean text.

Handles:
  • Zoom VTT (WebVTT) — produced by Zoom cloud auto-transcription
  • Zoom TRANSCRIPT (.txt) — plain-text variant
  • Google Meet transcript (.sbv or .srt — Workspace Recorder feature)
  • Plain text (any other format)

The cleaned text is used downstream by the LLM summarisation pipeline.
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from wimlds.core.logger import get_logger

logger = get_logger("transcript_processor")


class TranscriptFormat(Enum):
    VTT    = "vtt"       # WebVTT (Zoom cloud transcription)
    SRT    = "srt"       # SubRip (Google Meet, some Zoom exports)
    SBV    = "sbv"       # SubViewer (Google Meet)
    PLAIN  = "plain"     # Already clean text
    ZOOM   = "zoom"      # Zoom plain-text format (Speaker: text\n[timestamp])
    UNKNOWN = "unknown"


@dataclass
class TranscriptSegment:
    speaker:    Optional[str]
    start_time: str
    text:       str


@dataclass
class ParsedTranscript:
    raw_text:       str        # original bytes as utf-8 string
    clean_text:     str        # stripped of markup, ready for LLM
    segments:       list[TranscriptSegment]
    format_detected: TranscriptFormat
    word_count:     int
    duration_hint:  str        # e.g. "58 min" parsed from timestamps


class TranscriptProcessor:

    def process_file(self, path: str) -> ParsedTranscript:
        """Load a transcript file from disk and return a ParsedTranscript."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Transcript file not found: {path}")
        raw = p.read_text(encoding="utf-8", errors="replace")
        logger.info(f"Processing transcript: {p.name} ({len(raw)} chars)")
        return self.process_text(raw, filename=p.name)

    def process_text(self, raw: str, filename: str = "") -> ParsedTranscript:
        """Parse raw transcript text into a ParsedTranscript."""
        fmt = self._detect_format(raw, filename)
        logger.debug(f"Detected transcript format: {fmt.value}")

        if fmt == TranscriptFormat.VTT:
            segments = self._parse_vtt(raw)
        elif fmt == TranscriptFormat.SRT:
            segments = self._parse_srt(raw)
        elif fmt == TranscriptFormat.SBV:
            segments = self._parse_sbv(raw)
        elif fmt == TranscriptFormat.ZOOM:
            segments = self._parse_zoom_txt(raw)
        else:
            segments = self._parse_plain(raw)

        clean = self._segments_to_clean_text(segments)
        duration = self._estimate_duration(segments)
        wc = len(clean.split())

        logger.info(
            f"Transcript parsed — {len(segments)} segments, "
            f"{wc} words, ~{duration}"
        )
        return ParsedTranscript(
            raw_text        = raw,
            clean_text      = clean,
            segments        = segments,
            format_detected = fmt,
            word_count      = wc,
            duration_hint   = duration,
        )

    # ── Format detection ──────────────────────────────────────────────────────

    @staticmethod
    def _detect_format(raw: str, filename: str) -> TranscriptFormat:
        fn_lower = filename.lower()
        if fn_lower.endswith(".vtt") or raw.strip().startswith("WEBVTT"):
            return TranscriptFormat.VTT
        if fn_lower.endswith(".srt") or re.search(r"^\d+\n\d{2}:\d{2}:\d{2}", raw, re.M):
            return TranscriptFormat.SRT
        if fn_lower.endswith(".sbv") or re.search(r"^\d:\d{2}:\d{2}\.\d{3},", raw, re.M):
            return TranscriptFormat.SBV
        # Zoom plain-text: lines like "John Doe: text\n[HH:MM:SS]"
        if re.search(r"^\S.+:\s.+$", raw, re.M) and re.search(r"\[\d{2}:\d{2}", raw):
            return TranscriptFormat.ZOOM
        return TranscriptFormat.PLAIN

    # ── Parsers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_vtt(raw: str) -> list[TranscriptSegment]:
        """
        Parse WebVTT format.
        Example block:
            00:01:23.456 --> 00:01:27.000
            John Doe: Hello everyone, welcome to WiMLDS Pune.
        """
        segments = []
        blocks = re.split(r"\n\n+", raw.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            # Skip header / metadata lines
            if not lines or lines[0].startswith("WEBVTT") or "NOTE" in lines[0]:
                continue
            # Find timestamp line
            ts_line = next(
                (l for l in lines if "-->" in l), None
            )
            if not ts_line:
                continue
            start_ts = ts_line.split("-->")[0].strip()[:8]   # HH:MM:SS
            # Text lines (after timestamp)
            ts_idx  = lines.index(ts_line)
            text_lines = lines[ts_idx + 1:]
            text = " ".join(text_lines).strip()
            if not text:
                continue
            # Extract speaker from "Speaker Name: text"
            speaker, body = _split_speaker(text)
            segments.append(TranscriptSegment(
                speaker    = speaker,
                start_time = start_ts,
                text       = body,
            ))
        return segments

    @staticmethod
    def _parse_srt(raw: str) -> list[TranscriptSegment]:
        """
        Parse SRT format.
        Example:
            1
            00:00:03,000 --> 00:00:07,000
            Jane Smith: Good morning everyone!
        """
        segments = []
        blocks = re.split(r"\n\n+", raw.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            ts_line = next((l for l in lines if "-->" in l), None)
            if not ts_line:
                continue
            start_ts = ts_line.split("-->")[0].strip()[:8]
            ts_idx   = lines.index(ts_line)
            text     = " ".join(lines[ts_idx + 1:]).strip()
            # Remove SRT HTML tags e.g. <font color="...">
            text = re.sub(r"<[^>]+>", "", text).strip()
            speaker, body = _split_speaker(text)
            segments.append(TranscriptSegment(
                speaker=speaker, start_time=start_ts, text=body
            ))
        return segments

    @staticmethod
    def _parse_sbv(raw: str) -> list[TranscriptSegment]:
        """
        Parse SBV format (Google Meet).
        Example:
            0:00:03.000,0:00:07.000
            Priya Desai: Hello and welcome!
        """
        segments = []
        blocks = re.split(r"\n\n+", raw.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 2:
                continue
            # Timestamp line: H:MM:SS.mmm,H:MM:SS.mmm
            ts_match = re.match(r"(\d+:\d{2}:\d{2})", lines[0])
            if not ts_match:
                continue
            start_ts = ts_match.group(1)
            text     = " ".join(lines[1:]).strip()
            speaker, body = _split_speaker(text)
            segments.append(TranscriptSegment(
                speaker=speaker, start_time=start_ts, text=body
            ))
        return segments

    @staticmethod
    def _parse_zoom_txt(raw: str) -> list[TranscriptSegment]:
        """
        Parse Zoom plain-text transcript.
        Format:
            [00:02:10]
            John Doe: Welcome to our session on RAG systems.

            [00:02:45]
            Jane: Great, let me start with the agenda.
        """
        segments  = []
        cur_ts    = "00:00:00"
        cur_lines: list[str] = []

        def flush():
            if cur_lines:
                text    = " ".join(cur_lines).strip()
                speaker, body = _split_speaker(text)
                segments.append(TranscriptSegment(
                    speaker=speaker, start_time=cur_ts, text=body
                ))
            cur_lines.clear()

        for line in raw.splitlines():
            ts_match = re.match(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]", line.strip())
            if ts_match:
                flush()
                raw_ts   = ts_match.group(1)
                # Normalise H:MM → 00:H:MM if needed
                cur_ts   = raw_ts if raw_ts.count(":") == 2 else f"00:{raw_ts}"
            elif line.strip():
                cur_lines.append(line.strip())
        flush()
        return segments

    @staticmethod
    def _parse_plain(raw: str) -> list[TranscriptSegment]:
        """Fallback — split on blank lines, no timestamp parsing."""
        segments = []
        for para in re.split(r"\n{2,}", raw.strip()):
            text = para.strip()
            if text:
                speaker, body = _split_speaker(text)
                segments.append(TranscriptSegment(
                    speaker=speaker, start_time="", text=body
                ))
        return segments

    # ── Output ────────────────────────────────────────────────────────────────

    @staticmethod
    def _segments_to_clean_text(segments: list[TranscriptSegment]) -> str:
        """
        Build a clean, speaker-attributed string for LLM consumption.
        Format: [HH:MM] Speaker: text
        """
        lines = []
        for seg in segments:
            ts   = f"[{seg.start_time}] " if seg.start_time else ""
            spkr = f"{seg.speaker}: " if seg.speaker else ""
            lines.append(f"{ts}{spkr}{seg.text}")
        return "\n".join(lines)

    @staticmethod
    def _estimate_duration(segments: list[TranscriptSegment]) -> str:
        """Estimate session duration from first/last timestamps."""
        ts_list = [s.start_time for s in segments if s.start_time]
        if len(ts_list) < 2:
            return "unknown"
        try:
            def to_sec(t: str) -> int:
                parts = list(map(int, t.replace(",", ".").split(".")[0].split(":")))
                if len(parts) == 2:
                    return parts[0] * 60 + parts[1]
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            total = to_sec(ts_list[-1]) - to_sec(ts_list[0])
            mins  = max(1, total // 60)
            return f"{mins} min"
        except Exception:
            return "unknown"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_speaker(text: str) -> tuple[Optional[str], str]:
    """
    Split "Speaker Name: text body" → ("Speaker Name", "text body").
    Returns (None, text) if no recognisable speaker prefix.
    """
    # Match "First Last: " or "First: " but NOT "https://..."
    m = re.match(r"^([A-Z][a-zA-Z\s\-\.]{1,35}):\s+(.+)", text)
    if m and not m.group(1).startswith("http"):
        return m.group(1).strip(), m.group(2).strip()
    return None, text


# Singleton
transcript_processor = TranscriptProcessor()


