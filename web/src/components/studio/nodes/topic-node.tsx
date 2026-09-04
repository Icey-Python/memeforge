'use client';

// Topic Node: what the video is about + script generation trigger
// (with target duration pacing).

import type { NodeProps } from '@xyflow/react';
import { Loader2, MessageSquareText, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { DURATION_OPTIONS, TONE_OPTIONS } from '@/lib/catalog';
import { usePipelineStore } from '@/store/pipeline';
import type { DurationTarget } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';

const TOPIC_IDEAS = [
	'elden ring boss fights',
	'skyrim sneak builds',
	'gta rp traffic stops',
	'minecraft redstone griefers'
];

export function TopicNode(_props: NodeProps) {
	const topic = usePipelineStore((s) => s.topic);
	const setTopic = usePipelineStore((s) => s.setTopic);
	const tone = usePipelineStore((s) => s.tone);
	const setTone = usePipelineStore((s) => s.setTone);
	const durationTarget = usePipelineStore((s) => s.durationTarget);
	const setDurationTarget = usePipelineStore((s) => s.setDurationTarget);
	const generating = usePipelineStore((s) => s.generating);
	const error = usePipelineStore((s) => s.generatingError);
	const generateScript = usePipelineStore((s) => s.generateScript);
	const hasScript = usePipelineStore((s) => s.scriptLines.length > 0);

	return (
		<NodeShell
			icon={MessageSquareText}
			title="Topic"
			badge={
				hasScript ? <NodeBadge variant="success">scripted</NodeBadge> : null
			}
		>
			<div className="space-y-1.5">
				<Label htmlFor="topic-input">Topic</Label>
				<Textarea
					id="topic-input"
					value={topic}
					placeholder="e.g. elden ring boss fights"
					className="min-h-[64px] resize-none"
					onChange={(e) => setTopic(e.target.value)}
				/>
			</div>

			<div className="flex flex-wrap gap-1.5">
				{TOPIC_IDEAS.map((idea) => (
					<button
						key={idea}
						type="button"
						onClick={() => setTopic(idea)}
						className="rounded-full border border-white/10 px-3 py-1 text-xs text-zinc-400 transition-all hover:border-orange-500/40 hover:text-zinc-100 active:scale-[0.98]"
					>
						{idea}
					</button>
				))}
			</div>

			<div className="space-y-1.5">
				<Label htmlFor="tone-select">Tone</Label>
				<StudioSelect
					id="tone-select"
					value={tone}
					onChange={setTone}
					options={TONE_OPTIONS.map((t) => ({
						value: t.id,
						label: t.label
					}))}
				/>
			</div>

			<div className="space-y-1.5">
				<Label htmlFor="duration-select">Duration</Label>
				<StudioSelect
					id="duration-select"
					value={String(durationTarget)}
					onChange={(v) => setDurationTarget(Number(v) as DurationTarget)}
					options={DURATION_OPTIONS.map((d) => ({
						value: String(d.value),
						label: d.label
					}))}
				/>
			</div>

			<Button
				onClick={() => generateScript()}
				disabled={generating || !topic.trim()}
				className="w-full"
			>
				{generating ? (
					<Loader2 className="size-4 animate-spin" />
				) : (
					<Sparkles className="size-4" />
				)}
				{generating ? 'Generating' : 'Generate script'}
			</Button>

			{error && (
				<p className="text-xs text-red-400" role="alert">
					{error}
				</p>
			)}
		</NodeShell>
	);
}
