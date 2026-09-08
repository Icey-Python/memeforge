'use client';

// Voiceover Node: TTS provider + searchable voice picker + previews.
//
// The voice picker is one searchable combobox across every provider's
// catalog (Fish Audio, ElevenLabs, Edge-TTS, TikTok, Meme Classic,
// Azure, Google): typing filters by voice name, language, tag, or
// gender, and picking a voice from another engine switches the provider
// with it. Every row keeps its instant preview button; Fish Audio adds
// a model picker (pro vs free trial) and a custom voice-id field for
// marketplace voices.

import { useQueries } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { AudioLines, Check, Loader2, Play } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
	EDGE_VOICES,
	FISH_AUDIO_VOICES,
	FISH_MODELS,
	GOOGLE_VOICES,
	MEME_CLASSIC_VOICES,
	TIKTOK_VOICES,
	TTS_PROVIDERS
} from '@/lib/catalog';
import { ttsCredentialParams } from '@/lib/credentials';
import { MemeforgeAPI, mediaUrl } from '@/lib/memeforge';
import { cn } from '@/lib/utils';
import { useCredentialsStore } from '@/store/credentials';
import { usePipelineStore } from '@/store/pipeline';
import type { TTSProviderId, VoiceOption } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';
import { InlineVaultSection } from '../settings-drawer';
import { type VoiceCatalogEntry, VoiceCombobox } from '../voice-combobox';

// Offline fallback catalogs per provider (used before/without the API):
// edge + azure share the neural shortlist, tiktok / meme_classic have the
// meme catalogs, google maps tl codes, fish_audio carries a curated
// marketplace shortlist; elevenlabs lists remotely (empty until an API
// key is configured).
const OFFLINE_VOICE_FALLBACKS: Partial<Record<TTSProviderId, VoiceOption[]>> = {
	edge: EDGE_VOICES,
	azure: EDGE_VOICES,
	tiktok: TIKTOK_VOICES,
	meme_classic: MEME_CLASSIC_VOICES,
	google: GOOGLE_VOICES,
	fish_audio: FISH_AUDIO_VOICES
};

const PROVIDER_IDS = TTS_PROVIDERS.map((p) => p.id);

export function VoiceoverNode(_props: NodeProps) {
	const ttsProvider = usePipelineStore((s) => s.ttsProvider);
	const setTtsProvider = usePipelineStore((s) => s.setTtsProvider);
	const ttsVoice = usePipelineStore((s) => s.ttsVoice);
	const setTtsVoice = usePipelineStore((s) => s.setTtsVoice);
	const fishModel = usePipelineStore((s) => s.fishModel);
	const setFishModel = usePipelineStore((s) => s.setFishModel);
	const voiceConfirmed = usePipelineStore((s) => s.voiceConfirmed);
	const confirmVoice = usePipelineStore((s) => s.confirmVoice);

	// Vault-supplied keys (ElevenLabs / Azure / Fish Audio) take priority
	// over the server .env for voice listing, previews, and the final
	// render.
	const vaultKeys = useCredentialsStore((s) => s.keys);
	const keyRevision = useCredentialsStore((s) => s.revision);
	const isKeyed = (provider: TTSProviderId) =>
		provider === 'elevenlabs'
			? Boolean(vaultKeys?.elevenlabsApiKey)
			: provider === 'azure'
				? Boolean(vaultKeys?.azureSpeechKey)
				: provider === 'fish_audio'
					? Boolean(vaultKeys?.fishApiKey)
					: true;

	// Live voice catalogs for every provider in parallel: keyed engines
	// (ElevenLabs library, Fish marketplace) surface their remote lists,
	// the free engines just re-serve their static catalogs. Each query
	// refetches when the vault's key for that provider changes.
	const voiceQueries = useQueries({
		queries: TTS_PROVIDERS.map((p) => ({
			queryKey: ['voices', p.id, isKeyed(p.id), keyRevision],
			queryFn: () =>
				MemeforgeAPI.listVoices(p.id, ttsCredentialParams(p.id, vaultKeys)),
			retry: false,
			staleTime: 5 * 60_000
		}))
	});

	// Live results per provider (undefined when the call failed or is in
	// flight); offline fallbacks fill the gaps.
	const liveVoices = useMemo(() => {
		const map: Partial<Record<TTSProviderId, VoiceOption[]>> = {};
		for (const [i, p] of TTS_PROVIDERS.entries()) {
			const data = voiceQueries[i]?.data;
			if (data && data.length > 0) map[p.id] = data;
		}
		return map;
	}, [voiceQueries]);

	// The unified searchable catalog: every provider's voices tagged with
	// their engine, live data winning over the offline fallbacks.
	const catalog = useMemo<VoiceCatalogEntry[]>(() => {
		const entries: VoiceCatalogEntry[] = [];
		for (const provider of PROVIDER_IDS) {
			const list =
				liveVoices[provider] ?? OFFLINE_VOICE_FALLBACKS[provider] ?? [];
			for (const voice of list) entries.push({ ...voice, provider });
		}
		return entries;
	}, [liveVoices]);

	const isFish = ttsProvider === 'fish_audio';
	const voiceOptions =
		liveVoices[ttsProvider] ?? OFFLINE_VOICE_FALLBACKS[ttsProvider] ?? [];

	// The custom-id field shows the active voice only when it is not one
	// of the listed presets (typing there switches to that custom voice).
	const customVoice = voiceOptions.some((v) => v.id === ttsVoice)
		? ''
		: ttsVoice;

	const [previewing, setPreviewing] = useState<string | null>(null);
	const [previewUrl, setPreviewUrl] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	const selectVoice = (provider: TTSProviderId, voiceId: string) => {
		if (provider !== ttsProvider) setTtsProvider(provider);
		setTtsVoice(voiceId);
	};

	const preview = async (provider: TTSProviderId, voice: string) => {
		const key = `${provider}:${voice}`;
		setPreviewing(key);
		setError(null);
		try {
			const result = await MemeforgeAPI.synthesizeSpeech({
				text: 'This is memeforge, baby. Let us cook.',
				provider,
				voice,
				...(provider === 'fish_audio' ? { fish_model: fishModel } : {}),
				...ttsCredentialParams(provider, vaultKeys)
			});
			setPreviewUrl(mediaUrl(result.audio_url));
		} catch (err: any) {
			setError(err?.response?.data?.detail ?? 'Voice preview failed.');
		} finally {
			setPreviewing(null);
		}
	};

	return (
		<NodeShell
			icon={AudioLines}
			title="Voiceover"
			badge={
				<NodeBadge>
					{TTS_PROVIDERS.find((p) => p.id === ttsProvider)?.free
						? 'free'
						: 'premium'}
				</NodeBadge>
			}
		>
			<div className="space-y-1.5">
				<Label htmlFor="tts-provider">Provider</Label>
				<StudioSelect
					id="tts-provider"
					value={ttsProvider}
					onChange={(v) => setTtsProvider(v as TTSProviderId)}
					options={TTS_PROVIDERS.map((p) => ({
						value: p.id,
						label: p.free ? `${p.label} (free)` : p.label
					}))}
				/>
			</div>

			{/* Keyed engines: inline vault inputs for the provider's key. */}
			{(ttsProvider === 'elevenlabs' || ttsProvider === 'azure' || isFish) && (
				<InlineVaultSection
					title={
						ttsProvider === 'elevenlabs'
							? 'ElevenLabs key'
							: ttsProvider === 'azure'
								? 'Azure speech key'
								: 'Fish Audio key'
					}
					compact
					fields={
						ttsProvider === 'elevenlabs'
							? [
									{
										field: 'elevenlabsApiKey',
										label: 'ElevenLabs API Key',
										placeholder: 'xi-api key',
										serverFlag: 'tts_elevenlabs'
									}
								]
							: ttsProvider === 'azure'
								? [
										{
											field: 'azureSpeechKey',
											label: 'Azure Speech Key',
											placeholder: 'subscription key',
											serverFlag: 'tts_azure'
										},
										{
											field: 'azureSpeechRegion',
											label: 'Azure Region',
											placeholder: 'eastus',
											serverFlag: 'tts_azure_region',
											plaintext: true
										}
									]
								: [
										{
											field: 'fishApiKey',
											label: 'Fish Audio API Key',
											placeholder: 'fish_...',
											serverFlag: 'tts_fish'
										}
									]
					}
				/>
			)}

			{/* Fish Audio: model picker (pro model vs zero-cost trial). */}
			{isFish && (
				<div className="space-y-1.5">
					<Label htmlFor="fish-model">Model</Label>
					<StudioSelect
						id="fish-model"
						value={fishModel}
						onChange={setFishModel}
						options={FISH_MODELS.map((m) => ({
							value: m.id,
							label: m.label
						}))}
					/>
				</div>
			)}

			<div className="space-y-1.5">
				<Label htmlFor="tts-voice">Voice</Label>
				<VoiceCombobox
					id="tts-voice"
					value={ttsVoice}
					provider={ttsProvider}
					catalog={catalog}
					providerOrder={PROVIDER_IDS}
					onSelect={selectVoice}
					onPreview={preview}
					previewingKey={previewing}
				/>
				{isFish && (
					// Any fish.audio marketplace voice by id (the picker above
					// covers the curated/live presets).
					<div className="space-y-1 pt-1">
						<Label htmlFor="fish-custom-voice">Custom voice ID</Label>
						<Input
							id="fish-custom-voice"
							value={customVoice}
							onChange={(e) => setTtsVoice(e.target.value.trim())}
							placeholder="fish.audio voice model id"
							autoComplete="off"
							spellCheck={false}
							className="h-8 text-xs"
							data-testid="fish-custom-voice"
						/>
						<p className="text-[10px] text-zinc-500">
							Paste any voice id from the fish.audio marketplace.
						</p>
					</div>
				)}
			</div>

			<Button
				variant="outline"
				size="sm"
				className="w-full"
				onClick={() => preview(ttsProvider, ttsVoice)}
				disabled={previewing !== null}
			>
				{previewing === `${ttsProvider}:${ttsVoice}` ? (
					<Loader2 className="size-3.5 animate-spin" />
				) : (
					<Play className="size-3.5" />
				)}
				Preview selected voice
			</Button>

			{previewUrl && (
				// eslint-disable-next-line jsx-a11y/media-has-caption
				<audio
					controls
					src={previewUrl}
					className="h-8 w-full"
					data-testid="voice-preview"
				/>
			)}

			{error && (
				<p className="text-xs text-red-400" role="alert">
					{error}
				</p>
			)}

			{/* Step 3 gate: confirming the voice unlocks the video background. */}
			<Button
				size="sm"
				onClick={confirmVoice}
				aria-pressed={voiceConfirmed}
				data-testid="confirm-voice"
				className={cn(
					'w-full',
					voiceConfirmed
						? 'border border-orange-500/30 bg-orange-500/10 text-orange-300 hover:bg-orange-500/15'
						: ''
				)}
				variant={voiceConfirmed ? 'outline' : 'default'}
			>
				<Check className="size-4" />
				{voiceConfirmed ? 'Voice confirmed' : 'Confirm voice'}
			</Button>
		</NodeShell>
	);
}
