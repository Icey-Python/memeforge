'use client';

// Desc: Studio pipeline state shared by every canvas node.
// React Flow graph state (nodes/edges) lives in the canvas component;
// this store holds the pipeline config, stepwise reveal progress,
// and the render job lifecycle.

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { backendLLMProvider, llmBaseUrl } from '@/lib/catalog';
import { MemeforgeAPI } from '@/lib/memeforge';
import { deriveScriptTitle, splitScriptText } from '@/lib/script-split';
import type {
	CardStyleId,
	DurationTarget,
	ModelConfig,
	RenderJobInfo,
	StockClipSelection,
	TTSProviderId
} from '@/types/studio';

export type BackgroundMode = 'preset' | 'stock';

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
	/** API key for the selected keyed TTS provider (ElevenLabs / Azure) —
	 * hydrated from the encrypted vault, never persisted. */
	ttsApiKey: string;
	/** Azure Speech region (e.g. 'eastus') — not secret, persisted. */
	azureRegion: string;
	/** Preset gameplay loop id (background mode "preset"). */
	gameplayId: string;
	/** Which background tab is active / what the render will use. */
	backgroundMode: BackgroundMode;
	/** Ordered background clip picks (mode "stock"), in order. */
	stockClips: StockClipSelection[];
	/** Stock provider keys (Pexels / Pixabay) — hydrated from the
	 * encrypted vault, never persisted. */
	stockPexelsKey: string;
	stockPixabayKey: string;
	sfxEnabled: boolean;
	/** Top card overlay style for the render. */
	cardStyle: CardStyleId;

	// --- Stepwise reveal ---
	/** Wizard mode: nodes reveal progressively (default ON). */
	stepwise: boolean;
	/** User confirmed the script — unlocks the voiceover node. */
	scriptConfirmed: boolean;
	/** User confirmed the voice — unlocks the video background node. */
	voiceConfirmed: boolean;
	/** User confirmed the background — unlocks the preview & export node. */
	backgroundChosen: boolean;

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
	/** Split the pasted text into lines; unlocks the voiceover step. */
	applyCustomScript: () => void;
	setTtsProvider: (provider: TTSProviderId) => void;
	setTtsVoice: (voice: string) => void;
	setTtsApiKey: (key: string) => void;
	setAzureRegion: (region: string) => void;
	setStockKeys: (keys: { pexels?: string; pixabay?: string }) => void;
	/** Vault hydration entry point: patch every credential field at once. */
	setCredentials: (creds: {
		llmApiKey: string;
		ttsApiKey: string;
		stockPexelsKey: string;
		stockPixabayKey: string;
	}) => void;
	/** Select a preset gameplay clip (background mode "preset"). */
	setGameplay: (id: string) => void;
	/** Switch between the preset loop + stock video background tabs. */
	setBackgroundMode: (mode: BackgroundMode) => void;
	/** Add/remove a stock clip from the ordered background selection. */
	toggleStockClip: (clip: StockClipSelection) => void;
	setCardStyle: (style: CardStyleId) => void;
	toggleSfx: () => void;
	setStepwise: (stepwise: boolean) => void;
	confirmScript: () => void;
	/** Complete Step 3 (voice) — reveals the video background node. */
	confirmVoice: () => void;
	/** Complete Step 4 (background) — reveals the preview & export node. */
	confirmBackground: () => void;
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
		title: 'Voice',
		hint: 'Choose a voice, preview it, then confirm to continue.'
	},
	{
		title: 'Video Background',
		hint: 'Pick a preset gameplay loop or search stock video, then confirm.'
	},
	{
		title: 'Render',
		hint: 'All wired up — render your short.'
	}
] as const;

export type StudioStage = 1 | 2 | 3 | 4 | 5;

/** Current wizard stage (1–5), derived from pipeline progress. */
export function studioStage(s: {
	scriptLines: string[];
	scriptConfirmed: boolean;
	voiceConfirmed: boolean;
	backgroundChosen: boolean;
}): StudioStage {
	if (s.scriptConfirmed && s.backgroundChosen) return 5;
	if (s.scriptConfirmed && s.voiceConfirmed) return 4;
	if (s.scriptConfirmed) return 3;
	if (s.scriptLines.length > 0) return 2;
	return 1;
}

export const usePipelineStore = create<PipelineStore>()(
	persist(
		(set, get) => ({
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
			ttsApiKey: '',
			azureRegion: '',
			gameplayId: 'minecraft-parkour',
			backgroundMode: 'preset',
			stockClips: [],
			stockPexelsKey: '',
			stockPixabayKey: '',
			sfxEnabled: true,
			cardStyle: 'hook',

			stepwise: true,
			scriptConfirmed: false,
			voiceConfirmed: false,
			backgroundChosen: false,

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
				// unlocks the voiceover step (lines stay editable).
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
			setTtsApiKey: (ttsApiKey) => set({ ttsApiKey }),
			setAzureRegion: (azureRegion) => set({ azureRegion }),
			setStockKeys: (keys) =>
				set((s) => ({
					stockPexelsKey: keys.pexels ?? s.stockPexelsKey,
					stockPixabayKey: keys.pixabay ?? s.stockPixabayKey
				})),
			setCredentials: (creds) =>
				set((s) => ({
					model: { ...s.model, apiKey: creds.llmApiKey || undefined },
					ttsApiKey: creds.ttsApiKey,
					stockPexelsKey: creds.stockPexelsKey,
					stockPixabayKey: creds.stockPixabayKey
				})),
			setGameplay: (gameplayId) =>
				set({ gameplayId, backgroundMode: 'preset' }),
			setBackgroundMode: (backgroundMode) => set({ backgroundMode }),
			toggleStockClip: (clip) =>
				set((s) => {
					const picked = s.stockClips.some((c) => c.url === clip.url);
					return {
						backgroundMode: 'stock',
						stockClips: picked
							? s.stockClips.filter((c) => c.url !== clip.url)
							: [...s.stockClips, clip]
					};
				}),
			setCardStyle: (cardStyle) => set({ cardStyle }),
			toggleSfx: () => set((s) => ({ sfxEnabled: !s.sfxEnabled })),
			setStepwise: (stepwise) => set({ stepwise }),
			confirmScript: () => set({ scriptConfirmed: true }),
			confirmVoice: () => set({ voiceConfirmed: true }),
			confirmBackground: () => set({ backgroundChosen: true }),

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
						provider: backendLLMProvider(model.provider),
						model: model.model || undefined,
						base_url: llmBaseUrl(model) || undefined,
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
				const useStock =
					s.backgroundMode === 'stock' && s.stockClips.length > 0;
				try {
					const accepted = await MemeforgeAPI.startRender({
						topic: s.topic,
						title: s.scriptTitle || s.topic,
						script: s.scriptLines.filter((l) => l.trim().length > 0),
						tts_provider: s.ttsProvider,
						tts_voice: s.ttsVoice,
						// Vault-hydrated TTS credentials ride along so keyed
						// providers (ElevenLabs / Azure) render without server .env.
						tts_api_key: s.ttsApiKey || undefined,
						tts_region:
							s.ttsProvider === 'azure'
								? s.azureRegion || undefined
								: undefined,
						// Background: stitched stock clips (stock mode) or the preset
						// gameplay loop — the backend requires exactly one of them.
						gameplay_id: useStock ? undefined : s.gameplayId,
						stock_clips: useStock ? s.stockClips : undefined,
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
					throw new Error(
						err?.response?.data?.detail ?? 'Failed to queue render.'
					);
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
		}),
		{
			name: 'memeforge.pipeline.v1',
			version: 1,
			// /studio prerenders statically: rehydrate after mount (not
			// during React hydration) to avoid server/client mismatches.
			skipHydration: true,
			// Persist the wizard's choices so a reload keeps the flow —
			// but NEVER secrets: API keys live only in the encrypted vault
			// (see store/vault.ts) and transient lifecycle state is skipped.
			partialize: (state) => ({
				topic: state.topic,
				tone: state.tone,
				durationTarget: state.durationTarget,
				model: {
					provider: state.model.provider,
					model: state.model.model,
					baseUrl: state.model.baseUrl
				},
				scriptMode: state.scriptMode,
				scriptTitle: state.scriptTitle,
				scriptLines: state.scriptLines,
				customScriptText: state.customScriptText,
				ttsProvider: state.ttsProvider,
				ttsVoice: state.ttsVoice,
				azureRegion: state.azureRegion,
				gameplayId: state.gameplayId,
				backgroundMode: state.backgroundMode,
				stockClips: state.stockClips,
				cardStyle: state.cardStyle,
				sfxEnabled: state.sfxEnabled,
				stepwise: state.stepwise,
				scriptConfirmed: state.scriptConfirmed,
				voiceConfirmed: state.voiceConfirmed,
				backgroundChosen: state.backgroundChosen
			})
		}
	)
);
