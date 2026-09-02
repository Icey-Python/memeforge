/** Shared types for the memeforge studio pipeline. */

export type LLMProviderId = 'openai' | 'ollama' | 'mock';
export type TTSProviderId = 'edge' | 'tiktok' | 'azure' | 'elevenlabs';
export type RenderJobStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface ModelConfig {
	provider: LLMProviderId;
	model: string;
	baseUrl?: string;
	apiKey?: string;
}

export interface ModelCatalogEntry {
	id: LLMProviderId;
	label: string;
	default_model: string;
	configured: boolean;
}

export interface GameplayClip {
	id: string;
	label: string;
	game: string;
	description: string;
	source: string | null;
	available: boolean;
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
