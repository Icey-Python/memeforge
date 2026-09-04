// Desc: Memeforge FastAPI client (server/).
// All routes live under /api/v1 on the backend (see src/lib/config.ts).

import axios from 'axios';
import { apiBase, serverUrl } from '@/lib/config';
import type {
	GameplayClip,
	KeywordExtractResponse,
	ModelDiscoveryResult,
	RenderJobInfo,
	ScriptResponse,
	StockAutoSelectResponse,
	StockClipSelection,
	StockCredentialParams,
	StockSearchResponse,
	TTSCredentialParams,
	TTSProviderId,
	VoiceOption
} from '@/types/studio';

export interface GenerateScriptPayload {
	topic: string;
	provider: string;
	model?: string;
	base_url?: string;
	api_key?: string;
	tone?: string;
	/** Target spoken length in seconds (30/60/90 presets). */
	duration_target?: number;
	max_lines?: number;
}

export const MemeforgeAPI = {
	async health(): Promise<{
		status: string;
		capabilities: Record<string, boolean>;
	}> {
		// /health is mounted at the app root (container probes), not /api/v1.
		const { data } = await axios.get(`${serverUrl}/health`);
		return data;
	},

	async discoverModels(payload: {
		provider: string;
		baseUrl?: string;
		apiKey?: string;
	}): Promise<ModelDiscoveryResult> {
		const { data } = await apiBase.post('/models/discover', {
			provider: payload.provider,
			base_url: payload.baseUrl || undefined,
			api_key: payload.apiKey || undefined
		});
		return data;
	},

	async generateScript(
		payload: GenerateScriptPayload
	): Promise<ScriptResponse> {
		const { data } = await apiBase.post('/generate-script', payload);
		return data;
	},

	async listVoices(
		provider: TTSProviderId,
		creds?: TTSCredentialParams
	): Promise<VoiceOption[]> {
		const { data } = await apiBase.get('/voices', {
			params: { provider, ...creds }
		});
		return data;
	},

	async synthesizeSpeech(
		payload: {
			text: string;
			provider: string;
			voice?: string;
		} & TTSCredentialParams
	): Promise<{ provider: string; voice: string; audio_url: string }> {
		const { data } = await apiBase.post('/tts', payload);
		return data;
	},

	async listGameplays(): Promise<GameplayClip[]> {
		const { data } = await apiBase.get('/render/gameplays');
		return data;
	},

	/** Search Pexels / Pixabay for vertical stock clips.
	 * Falls back to curated demo clips when no API keys are set.
	 * Client vault keys (creds) take priority over the server .env. */
	async searchStock(
		query: string,
		creds?: StockCredentialParams
	): Promise<StockSearchResponse> {
		const { data } = await apiBase.get('/stock/search', {
			params: { q: query, ...creds }
		});
		return data;
	},

	/** Ask the configured LLM for 3-5 visual search queries from a script.
	 * Falls back to a deterministic heuristic when the LLM is offline. */
	async extractKeywords(payload: {
		script: string;
		provider: string;
		model?: string;
		base_url?: string;
		api_key?: string;
	}): Promise<KeywordExtractResponse> {
		const { data } = await apiBase.post('/stock/extract-keywords', payload);
		return data;
	},

	/** Auto-build a fast-switching montage: round-robin stock searches over
	 * the script's keyword set, sized to the script duration. Each clip
	 * plays a ~1.5-3s cut in the render. A fresh seed reshuffles the picks;
	 * `exclude` powers the per-clip swap. Vault keys ride in the body
	 * (same priority as /stock/search: headers > body > server .env). */
	async autoSelectStock(
		payload: {
			keywords?: string[];
			script?: string[];
			duration_s?: number;
			segment_s?: number;
			seed?: number;
			exclude?: StockClipSelection[];
		} & StockCredentialParams
	): Promise<StockAutoSelectResponse> {
		const { data } = await apiBase.post('/stock/auto-select', payload);
		return data;
	},

	async startRender(
		payload: {
			topic: string;
			title: string;
			script: string[];
			tts_provider: string;
			tts_voice?: string;
			/** Preset gameplay loop id (when the background is a preset clip). */
			gameplay_id?: string;
			/** Stock clips stitched into the background (stock mode). */
			stock_clips?: StockClipSelection[];
			/** Fast-switching cuts (~1.5-3s per clip) on the stock picks. */
			stock_montage?: boolean;
			/** Top card overlay: 'hook' (headline), 'quote', or 'none'. */
			card_style?: 'hook' | 'quote' | 'none';
			sfx_on_punchlines: boolean;
		} & TTSCredentialParams
	): Promise<{ job_id: string; status: string; status_url: string }> {
		const { data } = await apiBase.post('/render', payload);
		return data;
	},

	async getRenderJob(jobId: string): Promise<RenderJobInfo> {
		const { data } = await apiBase.get(`/render/${jobId}`);
		return {
			id: data.job_id,
			status: data.status,
			progress: data.progress,
			message: data.message,
			videoUrl: data.video_url,
			error: data.error
		};
	}
};

/** Media served by the backend static mount. */
export function mediaUrl(path: string): string {
	if (/^https?:\/\//.test(path)) return path;
	return `${serverUrl}${path}`;
}
