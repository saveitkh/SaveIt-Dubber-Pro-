import { useEffect, useRef, useState } from "react";

import { api } from "../../lib/api";
import type { CharacterDetail, Line, WaveformPeaks } from "../../lib/types";

interface TimelineProps {
  projectId: string;
  durationSec: number;
  lines: Line[];
  characters: CharacterDetail[];
  currentTime: number;
  onSeek: (seconds: number) => void;
}

const HEIGHT = 96;
const LANE_HEIGHT = 28;
const WAVEFORM_HEIGHT = HEIGHT - LANE_HEIGHT;
const PX_PER_SEC = 40;

export function Timeline({ projectId, durationSec, lines, characters, currentTime, onSeek }: TimelineProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [peaks, setPeaks] = useState<WaveformPeaks | null>(null);
  const charById = new Map(characters.map((c) => [c.id, c]));

  useEffect(() => {
    api
      .get<WaveformPeaks>(`/api/projects/${projectId}/waveform?track=original`)
      .then(setPeaks)
      .catch(() => setPeaks(null));
  }, [projectId]);

  const width = Math.max(1, Math.round(durationSec * PX_PER_SEC));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !peaks) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = width;
    canvas.height = WAVEFORM_HEIGHT;
    ctx.clearRect(0, 0, width, WAVEFORM_HEIGHT);

    const mid = WAVEFORM_HEIGHT / 2;
    ctx.fillStyle = "#475569";
    const n = peaks.min.length;
    for (let i = 0; i < n; i++) {
      const x = (i / n) * width;
      const barWidth = Math.max(1, width / n);
      const y1 = mid + peaks.min[i] * mid;
      const y2 = mid + peaks.max[i] * mid;
      ctx.fillRect(x, y1, barWidth, Math.max(1, y2 - y1));
    }
  }, [peaks, width]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left + e.currentTarget.scrollLeft;
    onSeek(Math.max(0, x / PX_PER_SEC));
  };

  return (
    <div className="overflow-x-auto rounded-xl bg-slate-900" onClick={handleClick}>
      <div className="relative" style={{ width, height: HEIGHT }}>
        <canvas ref={canvasRef} className="absolute left-0 top-0" style={{ width, height: WAVEFORM_HEIGHT }} />

        <div className="absolute left-0 right-0" style={{ top: WAVEFORM_HEIGHT, height: LANE_HEIGHT }}>
          {lines.map((line) => {
            const character = line.characterId ? charById.get(line.characterId) : undefined;
            const x = line.startSec * PX_PER_SEC;
            const w = Math.max(3, (line.endSec - line.startSec) * PX_PER_SEC);
            const flagged = line.flags.length > 0;
            return (
              <div
                key={line.id}
                title={line.khmerText || line.sourceText}
                className={`absolute top-0.5 h-6 rounded-sm ${flagged ? "ring-2 ring-amber-400" : ""}`}
                style={{ left: x, width: w, backgroundColor: character?.color ?? "#475569" }}
              />
            );
          })}
        </div>

        <div
          className="absolute top-0 w-px bg-brand-400"
          style={{ left: currentTime * PX_PER_SEC, height: HEIGHT }}
        />
      </div>
    </div>
  );
}
