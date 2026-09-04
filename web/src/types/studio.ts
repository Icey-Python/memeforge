/** Shared types for the memeforge studio pipeline. */

export type LLMProviderId = 'openai' | 'ollama' | 'mock';

/** Frontend-only connector preset picked in the Model node dropdown.
 * Cloud gateways (openai/anthropic/openrouter/groq) all ride the backend
 * 'openai' provider with a preset base URL; see LLM_PROVIDERS in
 * lib/catalog.ts. */
export type LLMGatewayId =
	| 'mock'
	| 'ollama'
	| 'openai'
	| 'anthropic'
	| 'openrouter'
	| 'groq'
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
	/** Backend provider id sent to the API. */
	provider: LLMProviderId;
	/** Chosen connector preset (frontend dropdown state, not sent). */
	gateway?: LLMGatewayId;
	model: string;
	baseUrl?: string;
	apiKey?: string;
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
	/** The script keyword that pulled this clip (auto-selected montages;
	 * powers the per-clip swap refresh). */
	keyword?: string;
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
	/** Visual stock-video search phrases tied to the script (10+ by
	 * default) — editable in the script node, consumed by the stock
	 * montage auto-select. */
	keywords: string[];
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

/** POST /stock/auto-select — a planned fast-switching montage sequence. */
export interface StockAutoSelectResponse {
	clips: StockClipSelection[];
	keywords: string[];
	duration_s: number;
	segment_s: number;
	segments_needed: number;
	notice: string | null;
	providers: StockProviderInfo[];
}

// --- Encrypted API-key vault (Settings → API Keys) --------------------------

/** Lifecycle of the local encrypted key vault. */
export type VaultStatus = 'uninitialized' | 'locked' | 'unlocked';

/**
 * Every credential the studio vault can hold. Values live in memory only
 * while the vault is unlocked; localStorage keeps just the AES-GCM
 * ciphertext (see lib/vault-crypto.ts).
 */
export interface ApiKeys {
	// LLM
	openaiApiKey: string;
	anthropicApiKey: string;
	openrouterApiKey: string;
	groqApiKey: string;
	/** Custom OpenAI-compatible base URL (OpenRouter, Groq, LM Studio...). */
	llmBaseUrl: string;
	// TTS
	elevenlabsApiKey: string;
	azureSpeechKey: string;
	azureSpeechRegion: string;
	// Stock video
	pexelsApiKey: string;
	pixabayApiKey: string;
}

/** Client TTS credentials sent with /voices, /tts and /render requests. */
export interface TTSCredentialParams {
	elevenlabs_api_key?: string;
	azure_speech_key?: string;
	azure_speech_region?: string;
}

/** Client stock credentials sent with /stock/search requests. */
export interface StockCredentialParams {
	pexels_api_key?: string;
	pixabay_api_key?: string;
}
