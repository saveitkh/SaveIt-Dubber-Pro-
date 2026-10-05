export interface Line {
  id: string;
  characterId: string | null;
  startSec: number;
  endSec: number;
  sourceText: string;
  khmerText: string;
  emotion: string;
  speed: number;
  audioUrl: string | null;
  flags: string[];
  dirty: boolean;
}

export interface CharacterDetail {
  id: string;
  name: string;
  gender: string | null;
  voiceId: string | null;
  color: string;
  faceThumbUrl: string | null;
  emotionDefault: string;
  speed: number;
}

export interface ReviewItem {
  id: string;
  lineId: string | null;
  kind: string;
  payload: Record<string, unknown> | null;
}

export interface JobDetail {
  id: string;
  stage: string;
  status: string;
  progress: number;
  message: string | null;
  error: string | null;
}

export interface ProjectDetail {
  project: {
    id: string;
    name: string;
    status: string;
    outputVideoUrl: string | null;
    outputAudioUrl: string | null;
    outputSrtUrl: string | null;
    originalAudioUrl: string | null;
  };
  lines: Line[];
  characters: CharacterDetail[];
  reviewItems: ReviewItem[];
  jobs: JobDetail[];
}

export interface WaveformPeaks {
  buckets: number;
  sampleRate: number;
  durationSec?: number;
  min: number[];
  max: number[];
}

export interface VoiceGroup {
  groupId: number;
  gender: string;
  totalSeconds: number;
  clipCount: number;
  quality: string;
  previewPath: string | null;
}

export interface VoiceItem {
  id: string;
  seriesId: string | null;
  name: string;
  referencePath: string | null;
  fingerprint: Record<string, unknown> | null;
  providerIds: Record<string, string> | null;
}

export interface ProviderStatus {
  gemini: { configured: boolean; model: string };
  elevenlabs: { configured: boolean };
  voxcpm: { configured: boolean; url: string; mode: string };
}

export interface HealthStatus {
  status: string;
  ffmpeg: boolean;
  demucs: boolean;
  gpu: boolean;
  providers: { gemini: boolean; elevenlabs: boolean; voxcpm: boolean };
  telegram: boolean;
}
