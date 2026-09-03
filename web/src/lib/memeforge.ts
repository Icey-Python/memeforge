// Desc: Memeforge FastAPI client (server/).
// All routes live under /api/v1 on the backend (see src/lib/config.ts).

import axios from 'axios';
import { apiBase, serverUrl } from '@/lib/config';
import type {
	GameplayClip,
	ModelCatalogEntry,
	ModelDiscoveryResult,
	RenderJobInfo,
	ScriptResponse,
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

	async listModels(): Promise<ModelCatalogEntry[]> {
		const { data } = await apiBase.get('/models');
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

	async listVoices(provider: TTSProviderId): Promise<VoiceOption[]> {
		const { data } = await apiBase.get('/voices', {
			params: { provider }
		});
		return data;
	},

	async synthesizeSpeech(payload: {
		text: string;
		provider: string;
		voice?: string;
	}): Promise<{ provider: string; voice: string; audio_url: string }> {
		const { data } = await apiBase.post('/tts', payload);
		return data;
	},

	async listGameplays(): Promise<GameplayClip[]> {
		const { data } = await apiBase.get('/render/gameplays');
		return data;
	},

	async startRender(payload: {
		topic: string;
		title: string;
		script: string[];
		tts_provider: string;
		tts_voice?: string;
		gameplay_id: string;
		/** Top card overlay: 'hook' (headline), 'quote', or 'none'. */
		card_style?: 'hook' | 'quote' | 'none';
		sfx_on_punchlines: boolean;
	}): Promise<{ job_id: string; status: string; status_url: string }> {
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
