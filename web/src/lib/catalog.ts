/** Offline fallbacks for backend catalogs (used before/without the API). */

import type {
	ApiKeys,
	CardStyleId,
	DurationTarget,
	LLMGatewayId,
	LLMProviderId,
	ModelConfig,
	TTSProviderId,
	VoiceOption
} from '@/types/studio';

/**
 * Model Connector presets shown in the node's Provider dropdown.
 *
 * Cloud gateways (OpenAI / Anthropic / OpenRouter / Groq) all ride the
 * backend's OpenAI-compatible provider; the preset base URL routes
 * credentials to the matching vault key (hostname matching in
 * lib/credentials.ts). "custom" points at any OpenAI-compatible endpoint
 * (LM Studio, vLLM, …) with an optional inline key.
 */
export interface LLMProviderPreset {
	/** Stable dropdown value (frontend-only; never sent to the backend). */
	id: LLMGatewayId;
	/** Backend provider id used in API payloads. */
	backend: LLMProviderId;
	label: string;
	hint: string;
	/** Model pre-selected before the endpoint has been queried. */
	defaultModel: string;
	/** Preset base URL ('' = provider default endpoint). */
	baseUrl: string;
	/** Vault key backing this gateway (named cloud gateways only). */
	vaultKey?: keyof ApiKeys;
	/** /health capability flag for the server .env default key. */
	serverFlag?: string;
}

export const LLM_PROVIDERS: LLMProviderPreset[] = [
	{
		id: 'mock',
		backend: 'mock',
		label: 'Mock (offline)',
		hint: 'deterministic stub — no key needed',
		defaultModel: 'memeforge-stub',
		baseUrl: ''
	},
	{
		id: 'ollama',
		backend: 'ollama',
		label: 'Ollama (local)',
		hint: 'installed models via your daemon',
		defaultModel: 'llama3.2',
		baseUrl: 'http://localhost:11434'
	},
	{
		id: 'openai',
		backend: 'openai',
		label: 'OpenAI',
		hint: 'GPT models via api.openai.com',
		defaultModel: 'gpt-4o-mini',
		baseUrl: '',
		vaultKey: 'openaiApiKey',
		serverFlag: 'llm_openai'
	},
	{
		id: 'anthropic',
		backend: 'openai',
		label: 'Anthropic',
		hint: 'Claude models',
		defaultModel: 'claude-sonnet-4-5',
		baseUrl: 'https://api.anthropic.com/v1',
		vaultKey: 'anthropicApiKey',
		serverFlag: 'llm_anthropic'
	},
	{
		id: 'openrouter',
		backend: 'openai',
		label: 'OpenRouter',
		hint: '400+ models, one key',
		defaultModel: 'openrouter/auto',
		baseUrl: 'https://openrouter.ai/api/v1',
		vaultKey: 'openrouterApiKey',
		serverFlag: 'llm_openrouter'
	},
	{
		id: 'groq',
		backend: 'openai',
		label: 'Groq',
		hint: 'ultra-fast open models',
		defaultModel: 'llama-3.3-70b-versatile',
		baseUrl: 'https://api.groq.com/openai/v1',
		vaultKey: 'groqApiKey',
		serverFlag: 'llm_groq'
	},
	{
		id: 'custom',
		backend: 'openai',
		label: 'Custom (OpenAI-compatible)',
		hint: 'LM Studio, vLLM, any endpoint',
		defaultModel: '',
		baseUrl: ''
	}
];

const GATEWAY_BY_ID: Record<LLMGatewayId, LLMProviderPreset> =
	Object.fromEntries(LLM_PROVIDERS.map((p) => [p.id, p])) as Record<
		LLMGatewayId,
		LLMProviderPreset
	>;

/**
 * Resolve the active connector preset from the pipeline model config.
 * The explicit `gateway` choice wins; state without one (legacy/hand
 * edited) is inferred from the backend provider + effective base URL.
 */
export function resolveGateway(
	model: Pick<ModelConfig, 'provider' | 'gateway'>,
	effectiveBaseUrl?: string
): LLMProviderPreset {
	if (model.gateway) {
		const preset = GATEWAY_BY_ID[model.gateway];
		if (preset) return preset;
	}
	if (model.provider === 'mock') return GATEWAY_BY_ID.mock;
	if (model.provider === 'ollama') return GATEWAY_BY_ID.ollama;
	const url = (effectiveBaseUrl ?? '').toLowerCase();
	if (url.includes('openrouter')) return GATEWAY_BY_ID.openrouter;
	if (url.includes('groq')) return GATEWAY_BY_ID.groq;
	if (url.includes('anthropic')) return GATEWAY_BY_ID.anthropic;
	if (url) return GATEWAY_BY_ID.custom;
	return GATEWAY_BY_ID.openai;
}

/** Fallback model ids offered in the dropdown while live discovery is
 * unavailable (key not set yet / endpoint unreachable). Live results
 * always replace them once a discovery succeeds. */
export const SUGGESTED_MODELS: Partial<Record<LLMGatewayId, string[]>> = {
	openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini'],
	anthropic: [
		'claude-sonnet-4-5',
		'claude-opus-4-1',
		'claude-3-5-haiku-latest'
	],
	openrouter: [
		'openrouter/auto',
		'openai/gpt-4o-mini',
		'anthropic/claude-sonnet-4.5'
	],
	groq: [
		'llama-3.3-70b-versatile',
		'llama-3.1-8b-instant',
		'openai/gpt-oss-120b'
	]
};

export const TTS_PROVIDERS: {
	id: TTSProviderId;
	label: string;
	hint: string;
	free: boolean;
}[] = [
	{
		id: 'edge',
		label: 'Edge-TTS',
		hint: 'Free Azure neural voices',
		free: true
	},
	{
		id: 'meme_classic',
		label: 'Meme Classic (Brian)',
		hint: 'Brian, Justin, Matthew — the iconic meme voices',
		free: true
	},
	{
		id: 'tiktok',
		label: 'TikTok Meme Voices (legacy)',
		hint: 'Unofficial — may fail, falls back to Brian',
		free: true
	},
	{
		id: 'google',
		label: 'Google Translate TTS',
		hint: 'Reliability fallback engine',
		free: true
	},
	{
		id: 'azure',
		label: 'Azure Speech',
		hint: 'Paid tier — same voices, SLA',
		free: false
	},
	{
		id: 'elevenlabs',
		label: 'ElevenLabs',
		hint: 'Premium expressive voices',
		free: false
	}
];

export const EDGE_VOICES: VoiceOption[] = [
	{
		id: 'en-US-ChristopherNeural',
		label: 'Christopher',
		language: 'en-US',
		gender: 'male',
		tags: ['meme', 'narration']
	},
	{
		id: 'en-US-GuyNeural',
		label: 'Guy',
		language: 'en-US',
		gender: 'male',
		tags: ['meme', 'energetic']
	},
	{
		id: 'en-US-EricNeural',
		label: 'Eric',
		language: 'en-US',
		gender: 'male',
		tags: ['meme', 'casual']
	},
	{
		id: 'en-US-RogerNeural',
		label: 'Roger',
		language: 'en-US',
		gender: 'male',
		tags: ['deadpan']
	},
	{
		id: 'en-US-JennyNeural',
		label: 'Jenny',
		language: 'en-US',
		gender: 'female',
		tags: ['meme', 'narration']
	},
	{
		id: 'en-US-MichelleNeural',
		label: 'Michelle',
		language: 'en-US',
		gender: 'female',
		tags: ['casual']
	},
	{
		id: 'en-GB-RyanNeural',
		label: 'Ryan',
		language: 'en-GB',
		gender: 'male',
		tags: ['meme']
	},
	{
		id: 'en-GB-SoniaNeural',
		label: 'Sonia',
		language: 'en-GB',
		gender: 'female',
		tags: ['narration']
	},
	{
		id: 'en-AU-NatashaNeural',
		label: 'Natasha',
		language: 'en-AU',
		gender: 'female',
		tags: ['casual']
	},
	{
		id: 'en-IE-EmilyNeural',
		label: 'Emily',
		language: 'en-IE',
		gender: 'female',
		tags: ['deadpan']
	}
];

/** Classic TikTok meme voices (free, keyless — mirrors the backend catalog). */
export const TIKTOK_VOICES: VoiceOption[] = [
	{
		id: 'en_us_002',
		label: 'Jessie — classic TikTok voice',
		language: 'en-US',
		gender: 'female',
		tags: ['meme']
	},
	{
		id: 'en_male_cody',
		label: 'Serious Male (Cody)',
		language: 'en-US',
		gender: 'male',
		tags: ['meme', 'narration']
	},
	{
		id: 'en_male_narration',
		label: 'Narrator',
		language: 'en-US',
		gender: 'male',
		tags: ['meme', 'narration']
	},
	{
		id: 'en_us_ghostface',
		label: 'Ghostface (Scream)',
		language: 'en-US',
		gender: 'male',
		tags: ['meme']
	},
	{
		id: 'en_us_trickster',
		label: 'Trickster',
		language: 'en-US',
		gender: 'male',
		tags: ['meme']
	}
];

/** Classic meme voices via ttsmp3.com / AWS Polly (free, keyless —
 * mirrors the backend meme_classic catalog). Brian is THE meme voice. */
export const MEME_CLASSIC_VOICES: VoiceOption[] = [
	{
		id: 'Brian',
		label: 'Brian — iconic meme voice (British)',
		language: 'en-GB',
		gender: 'male',
		tags: ['meme', 'iconic']
	},
	{
		id: 'Justin',
		label: 'Justin — kid/teen story voice',
		language: 'en-US',
		gender: 'male',
		tags: ['meme', 'kid']
	},
	{
		id: 'Matthew',
		label: 'Matthew — deep serious narrator',
		language: 'en-US',
		gender: 'male',
		tags: ['meme', 'narration']
	},
	{
		id: 'Kendra',
		label: 'Kendra',
		language: 'en-US',
		gender: 'female',
		tags: ['meme']
	},
	{
		id: 'Salli',
		label: 'Salli',
		language: 'en-US',
		gender: 'female',
		tags: ['meme']
	},
	{
		id: 'Joey',
		label: 'Joey',
		language: 'en-US',
		gender: 'male',
		tags: ['meme']
	},
	{
		id: 'Ivy',
		label: 'Ivy — kid voice',
		language: 'en-US',
		gender: 'female',
		tags: ['meme', 'kid']
	},
	{
		id: 'Joanna',
		label: 'Joanna',
		language: 'en-US',
		gender: 'female',
		tags: ['meme', 'narration']
	}
];

/** Google Translate TTS voices (free, keyless — tl language codes). */
export const GOOGLE_VOICES: VoiceOption[] = [
	{
		id: 'en',
		label: 'Google US English — reliability fallback',
		language: 'en-US',
		gender: 'female',
		tags: ['fallback']
	},
	{
		id: 'en-GB',
		label: 'Google UK English',
		language: 'en-GB',
		gender: 'female',
		tags: ['fallback']
	},
	{
		id: 'en-AU',
		label: 'Google Australian English',
		language: 'en-AU',
		gender: 'female',
		tags: ['fallback']
	},
	{
		id: 'en-IN',
		label: 'Google Indian English',
		language: 'en-IN',
		gender: 'female',
		tags: ['fallback']
	}
];

export const TONE_OPTIONS = [
	{ id: 'casual-commenter', label: 'Casual commenter' },
	{ id: 'unhinged-gamer', label: 'Unhinged gamer' },
	{ id: 'deadpan', label: 'Deadpan narrator' },
	{ id: 'hype', label: 'Hype commentator' }
];

/** Target duration presets: ~2.3 words/sec of spoken speech. */
export const DURATION_OPTIONS: {
	value: DurationTarget;
	label: string;
	hint: string;
}[] = [
	{ value: 30, label: '30 seconds', hint: '~70 words' },
	{ value: 60, label: '60 seconds (default)', hint: '~140 words' },
	{ value: 90, label: '90 seconds', hint: '~210 words' }
];

/** Top card overlay presets (rendered by the backend compositor). */
export const CARD_STYLE_OPTIONS: { value: CardStyleId; label: string }[] = [
	{ value: 'hook', label: 'Hook headline card' },
	{ value: 'quote', label: 'Quote card' },
	{ value: 'none', label: 'Clean full video (no card)' }
];

export const GAMEPLAY_FALLBACK = [
	{
		id: 'minecraft-parkour',
		label: 'Minecraft Parkour',
		game: 'Minecraft',
		description: 'Classic endless parkour jump loop.',
		source: null,
		available: false
	},
	{
		id: 'subway-surfers',
		label: 'Subway Surfers Run',
		game: 'Subway Surfers',
		description: 'Endless runner with trains and coins.',
		source: null,
		available: false
	},
	{
		id: 'gta5-stunts',
		label: 'GTA 5 Stunt Track',
		game: 'Grand Theft Auto V',
		description: 'San Andreas stunt jumps on repeat.',
		source: null,
		available: false
	}
];
