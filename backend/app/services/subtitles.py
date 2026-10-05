"""SRT generation, ported from the reference `audio_processor.create_srt_content`
(subtitle burning/ASS styling from that file is deferred to M4/M5's export options)."""


def _format_srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(lines: list[dict]) -> str:
    blocks = []
    for idx, line in enumerate(sorted(lines, key=lambda ln: ln["start_sec"]), start=1):
        text = (line.get("khmer_text") or "").strip()
        if not text:
            continue
        blocks.append(
            f"{idx}\n{_format_srt_time(line['start_sec'])} --> {_format_srt_time(line['end_sec'])}\n{text}\n"
        )
    return "\n".join(blocks)
