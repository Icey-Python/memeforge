'use client';

// Voiceover Node: TTS provider + voice picker + instant previews.
//
// The free meme-voice engines — Meme Classic (Brian & the classic Polly
// cast) and TikTok Meme Voices — get their own category list with
// per-voice preview buttons; edge/azure/google voices are grouped into
// "meme staples" vs the rest.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { AudioLines, Check, Loader2, Play } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
	EDGE_VOICES,
	GOOGLE_VOICES,
	MEME_CLASSIC_VOICES,
	TIKTOK_VOICES,
	TTS_PROVIDERS
} from '@/lib/catalog';
import { MemeforgeAPI, mediaUrl } from '@/lib/memeforge';
import { cn } from '@/lib/utils';
import { usePipelineStore } from '@/store/pipeline';
import type { TTSProviderId, VoiceOption } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';

// Offline fallback catalogs per provider (used before/without the API):
// edge + azure share the neural shortlist, tiktok / meme_classic have the
// meme catalogs, google maps tl codes; elevenlabs lists remotely (empty
// until an API key is configured server-side).
const OFFLINE_VOICE_FALLBACKS: Partial<Record<TTSProviderId, VoiceOption[]>> = {
	edge: EDGE_VOICES,
	azure: EDGE_VOICES,
	tiktok: TIKTOK_VOICES,
	meme_classic: MEME_CLASSIC_VOICES,
	google: GOOGLE_VOICES
};

export function VoiceoverNode(_props: NodeProps) {
	const ttsProvider = usePipelineStore((s) => s.ttsProvider);
	const setTtsProvider = usePipelineStore((s) => s.setTtsProvider);
	const ttsVoice = usePipelineStore((s) => s.ttsVoice);
	const setTtsVoice = usePipelineStore((s) => s.setTtsVoice);
	const voiceConfirmed = usePipelineStore((s) => s.voiceConfirmed);
	const confirmVoice = usePipelineStore((s) => s.confirmVoice);

	const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);
	const [previewUrl, setPreviewUrl] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	const { data: voices } = useQuery({
		queryKey: ['voices', ttsProvider],
		queryFn: () => MemeforgeAPI.listVoices(ttsProvider),
		retry: false,
		staleTime: 5 * 60_000
	});

	const isTikTok = ttsProvider === 'tiktok';
	const isMemeClassic = ttsProvider === 'meme_classic';
	// Free meme-voice engines get the featured category list with direct
	// per-voice previews; Brian leads the Meme Classic cast.
	const isFeaturedList = isTikTok || isMemeClassic;

	const voiceOptions: VoiceOption[] =
		voices && voices.length > 0
			? voices
			: (OFFLINE_VOICE_FALLBACKS[ttsProvider] ?? []);

	const preview = async (voice: string) => {
		setPreviewingVoice(voice);
		setError(null);
		try {
			const result = await MemeforgeAPI.synthesizeSpeech({
				text: 'This is memeforge, baby. Let us cook.',
				provider: ttsProvider,
				voice
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
			title="Voiceover / TTS"
			accent="bg-emerald-500/15 text-emerald-300"
			badge={
				<NodeBadge variant="success">
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
						label: `${p.label} — ${p.hint}${p.free ? ' (free)' : ''}`
					}))}
				/>
			</div>

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
						{isMemeClassic && (
							<p className="text-[10px] text-muted-foreground">
								The iconic Twitch meme TTS voices — free, keyless, no limits.
							</p>
						)}
						{voiceOptions.map((v) => {
							const selected = v.id === ttsVoice;
							const previewing = previewingVoice === v.id;
							return (
								<div
									key={v.id}
									className={cn(
										'flex items-center gap-2 rounded-lg border px-2.5 py-1.5 transition-colors',
										selected
											? 'border-emerald-500/50 bg-emerald-500/10'
											: 'border-border/60 bg-background/60'
									)}
								>
									<button
										type="button"
										className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
										onClick={() => setTtsVoice(v.id)}
									>
										{selected && (
											<Check className="size-3.5 shrink-0 text-emerald-400" />
										)}
										<span className="min-w-0">
											<span className="block truncate text-xs font-medium">
												{v.label}
											</span>
											<span className="block text-[10px] text-muted-foreground">
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
											label: '⭐ Popular meme voices',
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
					<p className="text-xs text-muted-foreground">
						ElevenLabs voices appear once{' '}
						<code className="rounded bg-muted px-1">ELEVENLABS_API_KEY</code> is
						set on the server.
					</p>
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
					'w-full font-semibold',
					voiceConfirmed
						? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20'
						: 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white hover:from-emerald-500 hover:to-teal-500'
				)}
			>
				{voiceConfirmed ? (
					<>
						<Check className="size-4" /> Voice confirmed
					</>
				) : (
					<>
						<Check className="size-4" /> Confirm Voice &amp; Next ➔
					</>
				)}
			</Button>
		</NodeShell>
	);
}
