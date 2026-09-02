/** Offline fallbacks for backend catalogs (used before/without the API). */

import type { LLMProviderId, TTSProviderId, VoiceOption } from '@/types/studio';

export const LLM_PROVIDERS: {
	id: LLMProviderId;
	label: string;
	hint: string;
	defaultModel: string;
}[] = [
	{
		id: 'mock',
		label: 'Mock (offline)',
		hint: 'Deterministic stub — no model required',
		defaultModel: 'memeforge-stub'
	},
	{
		id: 'openai',
		label: 'OpenAI-compatible',
		hint: 'OpenAI, OpenRouter, LM Studio, vLLM…',
		defaultModel: 'gpt-4o-mini'
	},
	{
		id: 'ollama',
		label: 'Ollama (local)',
		hint: 'Local models via your Ollama daemon',
		defaultModel: 'llama3.2'
	}
];

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
		id: 'tiktok',
		label: 'TikTok Meme Voices',
		hint: 'Jessie, Ghostface, Trickster…',
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

export const TONE_OPTIONS = [
	{ id: 'reddit-commenter', label: 'Reddit commenter' },
	{ id: 'unhinged-gamer', label: 'Unhinged gamer' },
	{ id: 'deadpan', label: 'Deadpan narrator' },
	{ id: 'hype', label: 'Hype commentator' }
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
