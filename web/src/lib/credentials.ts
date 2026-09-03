// Pure helpers that map vault keys onto backend request payloads.
//
// Resolution order for every credential:
//   1. inline input in the node (model connector key field)
//   2. the unlocked vault key matching the provider/endpoint
//   3. the server .env default (backend side)
// Keys never touch localStorage in plaintext — see lib/vault-crypto.ts.

import type {
	ApiKeys,
	ModelConfig,
	StockCredentialParams,
	TTSCredentialParams,
	TTSProviderId
} from '@/types/studio';

export const EMPTY_API_KEYS: ApiKeys = {
	openaiApiKey: '',
	anthropicApiKey: '',
	openrouterApiKey: '',
	groqApiKey: '',
	llmBaseUrl: '',
	elevenlabsApiKey: '',
	azureSpeechKey: '',
	azureSpeechRegion: '',
	pexelsApiKey: '',
	pixabayApiKey: ''
};

/** Merge a decrypted vault key map over the empty defaults. */
export function mergeApiKeys(stored: Record<string, string>): ApiKeys {
	return { ...EMPTY_API_KEYS, ...stored };
}

/**
 * Effective LLM credentials for /generate-script, /models/discover and
 * /stock/extract-keywords.
 *
 * - Base URL: the node's base URL wins; the vault's custom base URL is
 *   the global fallback.
 * - API key: the node's inline key wins; otherwise the vault key for the
 *   gateway matching the effective base URL (openrouter/groq/anthropic by
 *   host, OpenAI for the default endpoint). Unknown custom hosts get no
 *   automatic key — paste one inline in the model node so vault keys are
 *   never silently sent to arbitrary endpoints.
 */
export function resolveLLMCredential(
	model: ModelConfig,
	keys: ApiKeys | null
): { baseUrl?: string; apiKey?: string } {
	const baseUrl = (
		model.baseUrl?.trim() ||
		keys?.llmBaseUrl?.trim() ||
		''
	).trim();
	const inlineKey = model.apiKey?.trim() || '';

	let vaultKey = '';
	if (keys) {
		const url = baseUrl.toLowerCase();
		if (url.includes('openrouter')) vaultKey = keys.openrouterApiKey;
		else if (url.includes('groq')) vaultKey = keys.groqApiKey;
		else if (url.includes('anthropic')) vaultKey = keys.anthropicApiKey;
		else if (!url || url.includes('api.openai.com'))
			vaultKey = keys.openaiApiKey;
	}

	const apiKey = inlineKey || vaultKey;
	return {
		baseUrl: baseUrl || undefined,
		apiKey: apiKey || undefined
	};
}

/** TTS credentials for /voices, /tts and /render (per provider). */
export function ttsCredentialParams(
	provider: TTSProviderId,
	keys: ApiKeys | null
): TTSCredentialParams | undefined {
	if (!keys) return undefined;
	if (provider === 'elevenlabs') {
		return {
			elevenlabs_api_key: keys.elevenlabsApiKey.trim() || undefined
		};
	}
	if (provider === 'azure') {
		return {
			azure_speech_key: keys.azureSpeechKey.trim() || undefined,
			azure_speech_region: keys.azureSpeechRegion.trim() || undefined
		};
	}
	// Free engines (edge, meme_classic, tiktok, google) need no keys.
	return undefined;
}

/** Stock credentials for /stock/search. */
export function stockCredentialParams(
	keys: ApiKeys | null
): StockCredentialParams | undefined {
	if (!keys) return undefined;
	return {
		pexels_api_key: keys.pexelsApiKey.trim() || undefined,
		pixabay_api_key: keys.pixabayApiKey.trim() || undefined
	};
}
