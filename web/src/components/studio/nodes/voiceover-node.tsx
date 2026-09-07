'use client';

// Voiceover Node: TTS provider + voice picker + instant previews.
//
// The free meme-voice engines, Meme Classic (Brian & the classic Polly
// cast) and TikTok Meme Voices, get their own category list with
// per-voice preview buttons; edge/azure/google voices are grouped into
// "meme staples" vs the rest. Fish Audio adds a model picker (pro vs
// free trial) and a custom voice-id field for marketplace voices.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { AudioLines, Check, Loader2, Play } from 'lucide-react';
import { useState } from 'react';
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

// Offline fallback catalogs per provider (used before/without the API):
// edge + azure share the neural shortlist, tiktok / meme_classic have the
// meme catalogs, google maps tl codes, fish_audio carries a curated
// marketplace shortlist; elevenlabs lists remotely (empty until an API
// key is configured server-side).
const OFFLINE_VOICE_FALLBACKS: Partial<Record<TTSProviderId, VoiceOption[]>> = {
	edge: EDGE_VOICES,
	azure: EDGE_VOICES,
	tiktok: TIKTOK_VOICES,
	meme_classic: MEME_CLASSIC_VOICES,
	google: GOOGLE_VOICES,
	fish_audio: FISH_AUDIO_VOICES
};

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
	const keyedFlag =
		ttsProvider === 'elevenlabs'
			? Boolean(vaultKeys?.elevenlabsApiKey)
			: ttsProvider === 'azure'
				? Boolean(vaultKeys?.azureSpeechKey)
				: ttsProvider === 'fish_audio'
					? Boolean(vaultKeys?.fishApiKey)
					: true;
	const ttsCreds = () => ttsCredentialParams(ttsProvider, vaultKeys);

	const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);
	const [previewUrl, setPreviewUrl] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	const { data: voices } = useQuery({
		// Refetch when the vault's key for this provider changes.
		queryKey: ['voices', ttsProvider, keyedFlag, keyRevision],
		queryFn: () => MemeforgeAPI.listVoices(ttsProvider, ttsCreds()),
		retry: false,
		staleTime: 5 * 60_000
	});

	const isTikTok = ttsProvider === 'tiktok';
	const isMemeClassic = ttsProvider === 'meme_classic';
	const isFish = ttsProvider === 'fish_audio';
	// Free meme-voice engines get the featured category list with direct
	// per-voice previews; Brian leads the Meme Classic cast.
	const isFeaturedList = isTikTok || isMemeClassic;

	const voiceOptions: VoiceOption[] =
		voices && voices.length > 0
			? voices
			: (OFFLINE_VOICE_FALLBACKS[ttsProvider] ?? []);

	// The custom-id field shows the active voice only when it is not one
	// of the listed presets (typing there switches to that custom voice).
	const customVoice = voiceOptions.some((v) => v.id === ttsVoice)
		? ''
		: ttsVoice;

	const preview = async (voice: string) => {
		setPreviewingVoice(voice);
		setError(null);
		try {
			const result = await MemeforgeAPI.synthesizeSpeech({
				text: 'This is memeforge, baby. Let us cook.',
				provider: ttsProvider,
				voice,
				...(isFish ? { fish_model: fishModel } : {}),
				...ttsCreds()
			});
			setPreviewUrl(mediaUrl(result.audio_url));
		} catch (err: any) {
			setError(err?.response?.data?.detail ?? 'Voice preview failed.');
		} finally {
			setPreviewingVoice(null);
		}
	};

	const memeVoices = voiceOptions.filter((v) => v.tags?.includes('meme'));
	const otherVoices = voiceOptions.filter((v) => !v.tags?.includes('meme'));

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
				{isFeaturedList ? (
					// Featured free meme voices: category list with direct
					// previews (Brian leads the Meme Classic cast).
					<div
						className="space-y-1"
						data-testid={
							isMemeClassic ? 'meme-classic-voice-list' : 'tiktok-voice-list'
						}
					>
						{voiceOptions.map((v) => {
							const selected = v.id === ttsVoice;
							const previewing = previewingVoice === v.id;
							return (
								<div
									key={v.id}
									className={cn(
										'flex items-center gap-2 rounded-lg border px-2.5 py-1.5 transition-colors',
										selected
											? 'border-orange-500/50 bg-orange-500/10'
											: 'border-white/10 bg-white/[0.02] hover:border-white/20'
									)}
								>
									<button
										type="button"
										className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
										onClick={() => setTtsVoice(v.id)}
									>
										{selected && (
											<Check className="size-3.5 shrink-0 text-orange-400" />
										)}
										<span className="min-w-0">
											<span className="block truncate text-xs font-medium">
												{v.label}
											</span>
											<span className="block text-[10px] text-zinc-500">
												{v.id} · {v.gender}
											</span>
										</span>
									</button>
									<Button
										variant="ghost"
										size="icon"
										className="size-7 shrink-0"
										onClick={() => preview(v.id)}
										disabled={previewingVoice !== null}
										aria-label={`Preview ${v.label}`}
									>
										{previewing ? (
											<Loader2 className="size-3.5 animate-spin" />
										) : (
											<Play className="size-3.5" />
										)}
									</Button>
								</div>
							);
						})}
					</div>
				) : voiceOptions.length > 0 ? (
					<StudioSelect
						id="tts-voice"
						value={ttsVoice}
						onChange={setTtsVoice}
						groups={[
							...(memeVoices.length > 0
								? [
										{
											label: 'Meme voices',
											options: memeVoices.map((v) => ({
												value: v.id,
												label: `${v.label} (${v.language}, ${v.gender})`
											}))
										}
									]
								: []),
							...(otherVoices.length > 0
								? [
										{
											label: 'More voices',
											options: otherVoices.map((v) => ({
												value: v.id,
												label: `${v.label} (${v.language}, ${v.gender})`
											}))
										}
									]
								: [])
						]}
					/>
				) : (
					<p className="text-xs text-zinc-500">
						Voices appear once a key is set above.
					</p>
				)}
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
				onClick={() => preview(ttsVoice)}
				disabled={previewingVoice !== null}
			>
				{previewingVoice === ttsVoice ? (
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
