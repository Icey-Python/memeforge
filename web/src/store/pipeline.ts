'use client';

// Desc: Studio pipeline state shared by every canvas node.
// React Flow graph state (nodes/edges) lives in the canvas component;
// this store holds the pipeline config + render job lifecycle.

import { create } from 'zustand';
import { MemeforgeAPI } from '@/lib/memeforge';
import type { ModelConfig, RenderJobInfo, TTSProviderId } from '@/types/studio';

interface PipelineStore {
	// --- Config (one value per node type) ---
	topic: string;
	tone: string;
	model: ModelConfig;
	scriptTitle: string;
	scriptLines: string[];
	ttsProvider: TTSProviderId;
	ttsVoice: string;
	gameplayId: string;
	sfxEnabled: boolean;

	// --- Lifecycle ---
	generating: boolean;
	generatingError: string | null;
	renderJob: RenderJobInfo | null;
	rendering: boolean;

	// --- Actions ---
	setTopic: (topic: string) => void;
	setTone: (tone: string) => void;
	setModel: (patch: Partial<ModelConfig>) => void;
	setScriptLines: (lines: string[]) => void;
	setScriptTitle: (title: string) => void;
	setTtsProvider: (provider: TTSProviderId) => void;
	setTtsVoice: (voice: string) => void;
	setGameplay: (id: string) => void;
	toggleSfx: () => void;
	generateScript: () => Promise<void>;
	startRender: () => Promise<void>;
	pollRenderJob: (jobId: string) => Promise<void>;
	resetRender: () => void;
}

const VOICE_DEFAULTS: Record<TTSProviderId, string> = {
	edge: 'en-US-ChristopherNeural',
	azure: 'en-US-ChristopherNeural',
	elevenlabs: '21m00Tcm4TlvDq8ikWAM'
};

export const usePipelineStore = create<PipelineStore>((set, get) => ({
	topic: '',
	tone: 'reddit-commenter',
	model: {
		provider: 'mock',
		model: 'memeforge-stub'
	},
	scriptTitle: '',
	scriptLines: [],
	ttsProvider: 'edge',
	ttsVoice: VOICE_DEFAULTS.edge,
	gameplayId: 'minecraft-parkour',
	sfxEnabled: true,

	generating: false,
	generatingError: null,
	renderJob: null,
	rendering: false,

	setTopic: (topic) => set({ topic }),
	setTone: (tone) => set({ tone }),
	setModel: (patch) => set((s) => ({ model: { ...s.model, ...patch } })),
	setScriptLines: (lines) => set({ scriptLines: lines }),
	setScriptTitle: (scriptTitle) => set({ scriptTitle }),
	setTtsProvider: (provider) =>
		set({ ttsProvider: provider, ttsVoice: VOICE_DEFAULTS[provider] }),
	setTtsVoice: (ttsVoice) => set({ ttsVoice }),
	setGameplay: (gameplayId) => set({ gameplayId }),
	toggleSfx: () => set((s) => ({ sfxEnabled: !s.sfxEnabled })),

	generateScript: async () => {
		const { topic, tone, model } = get();
		if (!topic.trim()) {
			set({ generatingError: 'Enter a topic first.' });
			return;
		}
		set({ generating: true, generatingError: null });
		try {
			const script = await MemeforgeAPI.generateScript({
				topic,
				provider: model.provider,
				model: model.model || undefined,
				base_url: model.baseUrl || undefined,
				api_key: model.apiKey || undefined,
				tone
			});
			set({
				generating: false,
				scriptTitle: script.title,
				scriptLines: script.lines.map((l) => l.text)
			});
		} catch (err: any) {
			set({
				generating: false,
				generatingError:
					err?.response?.data?.detail ?? 'Script generation failed.'
			});
		}
	},

	startRender: async () => {
		const s = get();
		if (s.rendering) return;
		set({ rendering: true, renderJob: null });
		try {
			const accepted = await MemeforgeAPI.startRender({
				topic: s.topic,
				title: s.scriptTitle || s.topic,
				script: s.scriptLines.filter((l) => l.trim().length > 0),
				tts_provider: s.ttsProvider,
				tts_voice: s.ttsVoice,
				gameplay_id: s.gameplayId,
				sfx_on_punchlines: s.sfxEnabled
			});
			set({
				renderJob: {
					id: accepted.job_id,
					status: 'queued',
					progress: 0
				}
			});
		} catch (err: any) {
			set({ rendering: false });
			throw new Error(err?.response?.data?.detail ?? 'Failed to queue render.');
		}
	},

	pollRenderJob: async (jobId) => {
		try {
			const job = await MemeforgeAPI.getRenderJob(jobId);
			set({ renderJob: job });
			if (job.status === 'completed' || job.status === 'failed') {
				set({ rendering: false });
			}
		} catch {
			// transient network hiccup — keep polling
		}
	},

	resetRender: () => set({ renderJob: null, rendering: false })
}));
