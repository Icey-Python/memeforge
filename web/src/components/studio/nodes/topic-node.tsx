'use client';

// Topic / Prompt Node: what the meme is about + script generation trigger.

import type { NodeProps } from '@xyflow/react';
import { Loader2, MessageSquareText, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { TONE_OPTIONS } from '@/lib/catalog';
import { usePipelineStore } from '@/store/pipeline';
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
	const generating = usePipelineStore((s) => s.generating);
	const error = usePipelineStore((s) => s.generatingError);
	const generateScript = usePipelineStore((s) => s.generateScript);
	const hasScript = usePipelineStore((s) => s.scriptLines.length > 0);

	return (
		<NodeShell
			icon={MessageSquareText}
			title="Topic / Prompt"
			accent="bg-fuchsia-500/15 text-fuchsia-300"
			badge={
				<NodeBadge variant={hasScript ? 'success' : 'default'}>
					{hasScript ? 'scripted' : 'awaiting'}
				</NodeBadge>
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
						className="rounded-full border border-border/60 bg-muted/40 px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-fuchsia-500/40 hover:text-foreground"
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

			<Button
				onClick={() => generateScript()}
				disabled={generating || !topic.trim()}
				className="w-full bg-fuchsia-600 text-white hover:bg-fuchsia-500"
			>
				{generating ? (
					<Loader2 className="size-4 animate-spin" />
				) : (
					<Sparkles className="size-4" />
				)}
				{generating ? 'Thinking…' : 'Generate script'}
			</Button>

			{error && (
				<p className="text-xs text-red-400" role="alert">
					{error}
				</p>
			)}
		</NodeShell>
	);
}
