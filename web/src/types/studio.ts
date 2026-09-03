/** Shared types for the memeforge studio pipeline. */

/** Backend LLM connector ids (what the API accepts). */
export type LLMBackendId = 'openai' | 'ollama' | 'mock';

/** Studio provider presets (several map onto the backend 'openai'
 * connector with a fixed base URL, e.g. Anthropic / Groq / OpenRouter). */
export type LLMProviderId =
	| 'mock'
	| 'ollama'
	| 'openai'
	| 'anthropic'
	| 'groq'
	| 'openrouter'
	| 'custom';
export type TTSProviderId =
	| 'edge'
	| 'meme_classic'
	| 'tiktok'
	| 'google'
	| 'azure'
	| 'elevenlabs';
export type RenderJobStatus = 'queued' | 'running' | 'completed' | 'failed';

/** Target spoken length presets for script generation (seconds). */
export type DurationTarget = 30 | 60 | 90;

/** Top card overlay style for the rendered video. */
export type CardStyleId = 'hook' | 'quote' | 'none';

export interface ModelConfig {
	provider: LLMProviderId;
	model: string;
	baseUrl?: string;
	/** Session-only key from the encrypted vault — never persisted. */
	apiKey?: string;
}

export interface ModelCatalogEntry {
	id: LLMProviderId;
	label: string;
	default_model: string;
	configured: boolean;
}

export interface DiscoveredModel {
	/** Exact model name to send back to the provider. */
	id: string;
	/** Display label for dropdowns. */
	label: string;
	size_bytes: number | null;
	family: string | null;
	parameter_size: string | null;
	quantization: string | null;
	modified_at: string | null;
	available: boolean;
}

export interface ModelDiscoveryResult {
	provider: string;
	base_url: string | null;
	/** False when the provider endpoint could not be queried (daemon down,
	 * bad URL, auth failure) — `error` carries the reason. */
	reachable: boolean;
	error: string | null;
	models: DiscoveredModel[];
}

export interface GameplayClip {
	id: string;
	label: string;
	game: string;
	description: string;
	source: string | null;
	available: boolean;
}

/** One normalized vertical stock clip (Pexels / Pixabay). */
export interface StockVideoResult {
	id: string;
	/** "pexels" | "pixabay" */
	provider: string;
	title: string;
	duration_s: number;
	width: number;
	height: number;
	thumbnail_url: string;
	video_url: string;
	author: string;
	/** Curated fallback clip (unkeyed demo mode). */
	is_demo: boolean;
}

export interface StockProviderInfo {
	id: string;
	label: string;
	/** API key configured server-side? */
	keyed: boolean;
}

export interface StockSearchResponse {
	query: string;
	videos: StockVideoResult[];
	providers: StockProviderInfo[];
	notice: string | null;
}

/** A stock clip picked for the render background (sent to /render). */
export interface StockClipSelection {
	provider: string;
	id: string;
	url: string;
	duration_s: number;
	label: string;
}

export interface VoiceOption {
	id: string;
	label: string;
	language: string;
	gender: string;
	/** category tags from the backend (e.g. 'meme') for grouping */
	tags?: string[];
}

export interface ScriptResponse {
	topic: string;
	title: string;
	provider: string;
	model: string | null;
	lines: { index: number; text: string; is_punchline: boolean }[];
	generated_at: string;
}

export interface RenderJobInfo {
	id: string;
	status: RenderJobStatus;
	progress: number;
	message?: string | null;
	videoUrl?: string | null;
	error?: string | null;
}

export interface KeywordExtractResponse {
	queries: string[];
	source: 'llm' | 'heuristic';
}
