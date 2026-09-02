'use client';

// Desc: Studio pipeline state shared by every canvas node.
// React Flow graph state (nodes/edges) lives in the canvas component;
// this store holds the pipeline config, stepwise reveal progress,
// and the render job lifecycle.

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

	// --- Stepwise reveal ---
	/** Wizard mode: nodes reveal progressively (default ON). */
	stepwise: boolean;
	/** User confirmed the generated script — unlocks voiceover + gameplay. */
	scriptConfirmed: boolean;
	/** User picked a gameplay clip — unlocks the preview & export node. */
	gameplayChosen: boolean;

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
	setStepwise: (stepwise: boolean) => void;
	confirmScript: () => void;
	generateScript: () => Promise<void>;
	startRender: () => Promise<void>;
	pollRenderJob: (jobId: string) => Promise<void>;
	resetRender: () => void;
}

const VOICE_DEFAULTS: Record<TTSProviderId, string> = {
	edge: 'en-US-ChristopherNeural',
	meme_classic: 'Brian',
	tiktok: 'en_us_002',
	google: 'en',
	azure: 'en-US-ChristopherNeural',
	elevenlabs: '21m00Tcm4TlvDq8ikWAM'
};

/** Wizard step metadata shown in the studio header + canvas hint. */
export const STUDIO_STEPS = [
	{
		title: 'Connect',
		hint: 'Pick a model and enter your meme topic.'
	},
	{
		title: 'Script',
		hint: 'Review your script, then confirm it to continue.'
	},
	{
		title: 'Voice & gameplay',
		hint: 'Choose a voice, then click a gameplay clip.'
	},
	{
		title: 'Render',
		hint: 'All wired up — render your short.'
	}
] as const;

export type StudioStage = 1 | 2 | 3 | 4;

/** Current wizard stage (1–4), derived from pipeline progress. */
export function studioStage(s: {
	scriptLines: string[];
	scriptConfirmed: boolean;
	gameplayChosen: boolean;
}): StudioStage {
	if (s.scriptConfirmed && s.gameplayChosen) return 4;
	if (s.scriptConfirmed) return 3;
	if (s.scriptLines.length > 0) return 2;
	return 1;
}

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

	stepwise: true,
	scriptConfirmed: false,
	gameplayChosen: false,

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
	setGameplay: (gameplayId) => set({ gameplayId, gameplayChosen: true }),
	toggleSfx: () => set((s) => ({ sfxEnabled: !s.sfxEnabled })),
	setStepwise: (stepwise) => set({ stepwise }),
	confirmScript: () => set({ scriptConfirmed: true }),

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
