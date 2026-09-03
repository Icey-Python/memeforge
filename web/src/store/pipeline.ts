'use client';

// Desc: Studio pipeline state shared by every canvas node.
// React Flow graph state (nodes/edges) lives in the canvas component;
// this store holds the pipeline config, stepwise reveal progress,
// and the render job lifecycle.

import { create } from 'zustand';
import { MemeforgeAPI } from '@/lib/memeforge';
import { deriveScriptTitle, splitScriptText } from '@/lib/script-split';
import type {
	CardStyleId,
	DurationTarget,
	ModelConfig,
	RenderJobInfo,
	TTSProviderId
} from '@/types/studio';

interface PipelineStore {
	// --- Config (one value per node type) ---
	topic: string;
	tone: string;
	/** Target spoken length for script generation (seconds). */
	durationTarget: DurationTarget;
	model: ModelConfig;
	scriptMode: 'generated' | 'custom';
	scriptTitle: string;
	scriptLines: string[];
	/** Raw text block for the paste/write custom script flow. */
	customScriptText: string;
	ttsProvider: TTSProviderId;
	ttsVoice: string;
	gameplayId: string;
	sfxEnabled: boolean;
	/** Top card overlay style for the render. */
	cardStyle: CardStyleId;

	// --- Stepwise reveal ---
	/** Wizard mode: nodes reveal progressively (default ON). */
	stepwise: boolean;
	/** User confirmed the script — unlocks voiceover + gameplay. */
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
	setDurationTarget: (target: DurationTarget) => void;
	setModel: (patch: Partial<ModelConfig>) => void;
	setScriptMode: (mode: 'generated' | 'custom') => void;
	setScriptLines: (lines: string[]) => void;
	setScriptTitle: (title: string) => void;
	setCustomScriptText: (text: string) => void;
	/** Split the pasted text into lines; unlocks voiceover & gameplay. */
	applyCustomScript: () => void;
	setTtsProvider: (provider: TTSProviderId) => void;
	setTtsVoice: (voice: string) => void;
	setGameplay: (id: string) => void;
	setCardStyle: (style: CardStyleId) => void;
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
		hint: 'Pick a model and enter your video topic.'
	},
	{
		title: 'Script',
		hint: 'Generate a script or paste your own, then confirm it.'
	},
	{
		title: 'Voice & gameplay',
		hint: 'Choose a voice, then click a background clip.'
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
	tone: 'casual-commenter',
	durationTarget: 60,
	model: {
		provider: 'mock',
		model: 'memeforge-stub'
	},
	scriptMode: 'generated',
	scriptTitle: '',
	scriptLines: [],
	customScriptText: '',
	ttsProvider: 'edge',
	ttsVoice: VOICE_DEFAULTS.edge,
	gameplayId: 'minecraft-parkour',
	sfxEnabled: true,
	cardStyle: 'hook',

	stepwise: true,
	scriptConfirmed: false,
	gameplayChosen: false,

	generating: false,
	generatingError: null,
	renderJob: null,
	rendering: false,

	setTopic: (topic) => set({ topic }),
	setTone: (tone) => set({ tone }),
	setDurationTarget: (durationTarget) => set({ durationTarget }),
	setModel: (patch) => set((s) => ({ model: { ...s.model, ...patch } })),
	setScriptMode: (scriptMode) => set({ scriptMode }),
	setScriptLines: (lines) => set({ scriptLines: lines }),
	setScriptTitle: (scriptTitle) => set({ scriptTitle }),
	setCustomScriptText: (customScriptText) => set({ customScriptText }),
	applyCustomScript: () => {
		const lines = splitScriptText(get().customScriptText);
		if (lines.length === 0) {
			set({ generatingError: 'Paste or write some script text first.' });
			return;
		}
		// A custom script needs no LLM round-trip: splitting it directly
		// unlocks the voiceover & gameplay steps (lines stay editable).
		set({
			scriptTitle: deriveScriptTitle(lines),
			scriptLines: lines,
			scriptConfirmed: true,
			generatingError: null
		});
	},
	setTtsProvider: (provider) =>
		set({ ttsProvider: provider, ttsVoice: VOICE_DEFAULTS[provider] }),
	setTtsVoice: (ttsVoice) => set({ ttsVoice }),
	setGameplay: (gameplayId) => set({ gameplayId, gameplayChosen: true }),
	setCardStyle: (cardStyle) => set({ cardStyle }),
	toggleSfx: () => set((s) => ({ sfxEnabled: !s.sfxEnabled })),
	setStepwise: (stepwise) => set({ stepwise }),
	confirmScript: () => set({ scriptConfirmed: true }),

	generateScript: async () => {
		const { topic, tone, model, durationTarget } = get();
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
				tone,
				duration_target: durationTarget
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
				card_style: s.cardStyle,
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
