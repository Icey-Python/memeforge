'use client';

// Voiceover Node: TTS provider + voice picker + instant preview.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { AudioLines, Loader2, Play } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { EDGE_VOICES, TTS_PROVIDERS } from '@/lib/catalog';
import { MemeforgeAPI, mediaUrl } from '@/lib/memeforge';
import { usePipelineStore } from '@/store/pipeline';
import type { TTSProviderId } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';

export function VoiceoverNode(_props: NodeProps) {
	const ttsProvider = usePipelineStore((s) => s.ttsProvider);
	const setTtsProvider = usePipelineStore((s) => s.setTtsProvider);
	const ttsVoice = usePipelineStore((s) => s.ttsVoice);
	const setTtsVoice = usePipelineStore((s) => s.setTtsVoice);

	const [previewing, setPreviewing] = useState(false);
	const [previewUrl, setPreviewUrl] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	const { data: voices } = useQuery({
		queryKey: ['voices', ttsProvider],
		queryFn: () => MemeforgeAPI.listVoices(ttsProvider),
		retry: false,
		staleTime: 5 * 60_000
	});

	// Neural shortlist applies to edge + azure; elevenlabs lists remotely
	// (empty until an API key is configured server-side).
	const voiceOptions =
		voices && voices.length > 0
			? voices
			: ttsProvider === 'elevenlabs'
				? []
				: EDGE_VOICES;

	const preview = async () => {
		setPreviewing(true);
		setError(null);
		try {
			const result = await MemeforgeAPI.synthesizeSpeech({
				text: 'This is memeforge, baby. Let us cook.',
				provider: ttsProvider,
				voice: ttsVoice
			});
			setPreviewUrl(mediaUrl(result.audio_url));
		} catch (err: any) {
			setError(err?.response?.data?.detail ?? 'Voice preview failed.');
		} finally {
			setPreviewing(false);
		}
	};

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
				{voiceOptions.length > 0 ? (
					<StudioSelect
						id="tts-voice"
						value={ttsVoice}
						onChange={setTtsVoice}
						options={voiceOptions.map((v) => ({
							value: v.id,
							label: `${v.label} (${v.language}, ${v.gender})`
						}))}
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
				onClick={preview}
				disabled={previewing}
			>
				{previewing ? (
					<Loader2 className="size-3.5 animate-spin" />
				) : (
					<Play className="size-3.5" />
				)}
				Preview voice
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
		</NodeShell>
	);
}
