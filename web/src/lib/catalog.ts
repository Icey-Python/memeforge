/** Offline fallbacks for backend catalogs (used before/without the API). */

import type {
	CardStyleId,
	DurationTarget,
	LLMBackendId,
	LLMProviderId,
	ModelConfig,
	TTSProviderId,
	VoiceOption
} from '@/types/studio';

export interface LLMProviderPreset {
	id: LLMProviderId;
	/** Backend connector the preset maps onto. */
	backend: LLMBackendId;
	label: string;
	hint: string;
	defaultModel: string;
	/** Fixed endpoint for cloud presets; starting value for editable ones. */
	defaultBaseUrl: string;
	/** Cloud presets require an API key before model discovery works. */
	requiresApiKey: boolean;
	/** Whether the Base URL field is shown (ollama / custom only). */
	baseUrlEditable: boolean;
	/** Live model discovery via /models/discover (anthropic's compat
	 * endpoint is flaky there — it uses the curated catalog instead). */
	discoverable: boolean;
	/** Standard catalog models — shown before discovery (or when offline). */
	models: string[];
}

export const LLM_PROVIDERS: LLMProviderPreset[] = [
	{
		id: 'mock',
		backend: 'mock',
		label: 'Mock (offline)',
		hint: 'Deterministic stub — no model or key needed',
		defaultModel: 'memeforge-stub',
		defaultBaseUrl: '',
		requiresApiKey: false,
		baseUrlEditable: false,
		discoverable: false,
		models: ['memeforge-stub']
	},
	{
		id: 'ollama',
		backend: 'ollama',
		label: 'Ollama (local)',
		hint: 'Local daemon — installed models auto-detected',
		defaultModel: 'llama3.2',
		defaultBaseUrl: 'http://localhost:11434',
		requiresApiKey: false,
		baseUrlEditable: true,
		discoverable: true,
		models: ['llama3.2', 'llama3.1', 'qwen2.5', 'mistral']
	},
	{
		id: 'openai',
		backend: 'openai',
		label: 'OpenAI',
		hint: 'GPT-4o / GPT-4.1 family',
		defaultModel: 'gpt-4o-mini',
		defaultBaseUrl: 'https://api.openai.com/v1',
		requiresApiKey: true,
		baseUrlEditable: false,
		discoverable: true,
		models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-4.1']
	},
	{
		id: 'anthropic',
		backend: 'openai',
		label: 'Anthropic',
		hint: 'Claude models (OpenAI-compatible endpoint)',
		defaultModel: 'claude-sonnet-4-5',
		defaultBaseUrl: 'https://api.anthropic.com/v1',
		requiresApiKey: true,
		baseUrlEditable: false,
		discoverable: false,
		models: ['claude-sonnet-4-5', 'claude-haiku-4-5', 'claude-opus-4-1']
	},
	{
		id: 'groq',
		backend: 'openai',
		label: 'Groq',
		hint: 'Llama / GPT-OSS — blazing fast',
		defaultModel: 'llama-3.3-70b-versatile',
		defaultBaseUrl: 'https://api.groq.com/openai/v1',
		requiresApiKey: true,
		baseUrlEditable: false,
		discoverable: true,
		models: [
			'llama-3.3-70b-versatile',
			'llama-3.1-8b-instant',
			'openai/gpt-oss-120b'
		]
	},
	{
		id: 'openrouter',
		backend: 'openai',
		label: 'OpenRouter',
		hint: 'One key, every provider',
		defaultModel: 'openai/gpt-4o-mini',
		defaultBaseUrl: 'https://openrouter.ai/api/v1',
		requiresApiKey: true,
		baseUrlEditable: false,
		discoverable: true,
		models: [
			'openai/gpt-4o-mini',
			'anthropic/claude-sonnet-4.5',
			'google/gemini-2.5-flash',
			'meta-llama/llama-3.3-70b-instruct'
		]
	},
	{
		id: 'custom',
		backend: 'openai',
		label: 'Custom OpenAI-compatible',
		hint: 'LM Studio, vLLM, LiteLLM — any /v1 endpoint',
		defaultModel: '',
		defaultBaseUrl: '',
		requiresApiKey: false,
		baseUrlEditable: true,
		discoverable: true,
		models: []
	}
];

/** Backend connector id a studio preset maps onto. */
export function backendLLMProvider(providerId: LLMProviderId): LLMBackendId {
	return LLM_PROVIDERS.find((p) => p.id === providerId)?.backend ?? 'mock';
}

/** Effective endpoint URL for a model config (fixed cloud presets use
 * their preset URL; ollama / custom use the user's Base URL field). */
export function llmBaseUrl(model: ModelConfig): string {
	const preset = LLM_PROVIDERS.find((p) => p.id === model.provider);
	if (!preset) return '';
	if (preset.baseUrlEditable) return model.baseUrl?.trim() ?? '';
	return preset.defaultBaseUrl;
}

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
