'use client';

// Preview & Export Node: render trigger, job progress, vertical player.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import {
	Check,
	CircleDashed,
	Film,
	Loader2,
	RotateCcw,
	XCircle,
	Zap
} from 'lucide-react';
import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { CARD_STYLE_OPTIONS } from '@/lib/catalog';
import { MemeforgeAPI, mediaUrl } from '@/lib/memeforge';
import { cn } from '@/lib/utils';
import { usePipelineStore } from '@/store/pipeline';
import type { CardStyleId } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';

function CheckItem({ ok, label }: { ok: boolean; label: string }) {
	return (
		<li
			className={cn(
				'flex items-center gap-2 text-xs',
				ok ? 'text-zinc-500' : 'text-zinc-200'
			)}
		>
			{ok ? (
				<Check className="size-3.5 text-orange-400" />
			) : (
				<CircleDashed className="size-3.5 text-zinc-600" />
			)}
			{label}
			{!ok && <span className="text-red-400">needed</span>}
		</li>
	);
}

export function PreviewNode(_props: NodeProps) {
	const topic = usePipelineStore((s) => s.topic);
	const scriptLines = usePipelineStore((s) => s.scriptLines);
	const gameplayId = usePipelineStore((s) => s.gameplayId);
	const backgroundMode = usePipelineStore((s) => s.backgroundMode);
	const stockClips = usePipelineStore((s) => s.stockClips);
	const sfxEnabled = usePipelineStore((s) => s.sfxEnabled);
	const toggleSfx = usePipelineStore((s) => s.toggleSfx);
	const cardStyle = usePipelineStore((s) => s.cardStyle);
	const setCardStyle = usePipelineStore((s) => s.setCardStyle);
	const renderJob = usePipelineStore((s) => s.renderJob);
	const rendering = usePipelineStore((s) => s.rendering);
	const startRender = usePipelineStore((s) => s.startRender);
	const pollRenderJob = usePipelineStore((s) => s.pollRenderJob);
	const resetRender = usePipelineStore((s) => s.resetRender);

	const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

	const { data: clips } = useQuery({
		queryKey: ['gameplays'],
		queryFn: MemeforgeAPI.listGameplays,
		retry: false,
		staleTime: 60_000
	});
	const clip = (clips?.length ? clips : []).find((c) => c.id === gameplayId);
	// Background readiness depends on the active mode: preset loops need a
	// bundled asset on the server; stock mode needs at least one picked clip.
	const backgroundReady =
		backgroundMode === 'stock'
			? stockClips.length > 0
			: Boolean(clip?.available);

	const hasScript = scriptLines.some((l) => l.trim());
	// A pasted custom script is a complete pipeline input on its own,
	// rendering must not require a topic as well.
	const ready = hasScript && backgroundReady;

	// Poll the backend while a job is in flight.
	useEffect(() => {
		if (rendering && renderJob?.id) {
			const jobId = renderJob.id;
			pollRef.current = setInterval(() => pollRenderJob(jobId), 2000);
		}
		return () => {
			if (pollRef.current) clearInterval(pollRef.current);
		};
	}, [rendering, renderJob?.id, pollRenderJob]);

	const onRender = async () => {
		try {
			await startRender();
			toast.success('Render queued, forging your short.');
		} catch (err: any) {
			toast.error(err.message ?? 'Render failed to start.');
		}
	};

	const statusBadge = () => {
		if (!renderJob) return null;
		if (renderJob.status === 'completed')
			return <NodeBadge variant="success">ready</NodeBadge>;
		if (renderJob.status === 'failed')
			return <NodeBadge variant="danger">failed</NodeBadge>;
		return <NodeBadge variant="warn">{renderJob.status}</NodeBadge>;
	};

	return (
		<NodeShell
			icon={Film}
			title="Preview & Export"
			handles="target"
			extraTargetId="gameplay"
			badge={statusBadge()}
		>
			<ul className="space-y-1.5">
				<CheckItem ok={topic.trim().length > 0} label="Topic set" />
				<CheckItem ok={hasScript} label="Script lines" />
				<CheckItem
					ok={backgroundReady}
					label={
						backgroundMode === 'stock'
							? 'Stock clips picked'
							: 'Background clip available'
					}
				/>
			</ul>

			<div className="space-y-1.5">
				<Label htmlFor="card-style-select">Top card</Label>
				<StudioSelect
					id="card-style-select"
					value={cardStyle}
					onChange={(v) => setCardStyle(v as CardStyleId)}
					options={CARD_STYLE_OPTIONS.map((o) => ({
						value: o.value,
						label: o.label
					}))}
				/>
			</div>

			<label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-400">
				<input
					type="checkbox"
					checked={sfxEnabled}
					onChange={toggleSfx}
					className="size-3.5 accent-orange-500"
				/>
				Punchline SFX
			</label>

			{rendering ||
			renderJob?.status === 'running' ||
			renderJob?.status === 'queued' ? (
				<div className="space-y-2">
					<div className="h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
						<div
							className="h-full rounded-full bg-orange-500 transition-all"
							style={{
								width: `${Math.round((renderJob?.progress ?? 0) * 100)}%`
							}}
						/>
					</div>
					<p className="flex items-center gap-2 text-xs text-zinc-500">
						<Loader2 className="size-3 animate-spin" />
						{renderJob?.message ?? 'Working'} (
						{Math.round((renderJob?.progress ?? 0) * 100)}%)
					</p>
				</div>
			) : (
				<Button
					onClick={onRender}
					disabled={!ready || rendering}
					className="w-full gap-1.5"
				>
					<Zap className="size-4" />
					Render 1080×1920 short
				</Button>
			)}

			{renderJob?.status === 'failed' && (
				<div className="rounded-xl border border-red-500/25 bg-red-500/10 p-3 text-xs text-red-300">
					<p className="flex items-center gap-1.5 font-medium">
						<XCircle className="size-3.5" /> Render failed
					</p>
					<p className="mt-1 break-words text-red-300/80">{renderJob.error}</p>
					<Button
						variant="ghost"
						size="sm"
						className="mt-2 h-7 px-2 text-xs text-red-300 hover:text-red-200"
						onClick={resetRender}
					>
						<RotateCcw className="size-3" /> Try again
					</Button>
				</div>
			)}

			{renderJob?.status === 'completed' && renderJob.videoUrl && (
				<div className="space-y-2">
					<div className="mx-auto w-fit overflow-hidden rounded-xl border border-white/10">
						<video
							controls
							src={mediaUrl(renderJob.videoUrl)}
							className="aspect-[9/16] max-h-[380px] w-auto bg-black"
							data-testid="rendered-video"
						/>
					</div>
					<Button
						variant="outline"
						size="sm"
						className="w-full text-xs"
						onClick={resetRender}
					>
						<RotateCcw className="size-3" /> Render another
					</Button>
				</div>
			)}

			{!ready && !rendering && !renderJob && (
				<p className="text-[11px] text-zinc-600">
					A script plus a background is enough to render. Pasting a custom
					script works without a topic.
				</p>
			)}
		</NodeShell>
	);
}
