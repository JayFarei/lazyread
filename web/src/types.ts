export type ArticleStatus = "processing" | "ready" | "failed" | "trashed";

export type Progress = {
  completed: number;
  total: number;
  percent: number;
  etaSeconds?: number;
};

export type WordTiming = {
  index: number;
  text: string;
  start: number;
  end: number;
};

export type AudioManifest = {
  audio: string;
  duration: number;
  bytes?: number;
  revision?: string;
  voice?: string;
  model?: string;
  modelRevision?: string;
  aligner?: string;
  alignerRevision?: string;
  words: WordTiming[];
};

export type Article = {
  id: string;
  status: ArticleStatus;
  state?: string;
  title: string;
  description?: string;
  author?: string;
  site?: string;
  sourceUrl?: string;
  publishedAt?: string;
  createdAt?: string;
  updatedAt?: string;
  wordCount?: number;
  durationSeconds?: number;
  route: string;
  phase?: string;
  progress?: Progress;
  error?: string;
  markdown?: string;
  html?: string;
  audioUrl?: string;
  timingsUrl?: string;
  audioRevision?: string;
  manifest?: AudioManifest;
  voice?: string;
  model?: string;
  provider?: string;
  productionSeconds?: number;
  peakMemoryBytes?: number;
  artifactBytes?: number;
  warnings: string[];
};

export type Highlight = {
  id: string;
  text: string;
  startIndex: number;
  endIndex: number;
};
