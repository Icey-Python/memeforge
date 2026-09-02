'use client';

// Script Node: shows the generated script; every line stays editable.

import type { NodeProps } from '@xyflow/react';
import { Plus, ScrollText, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { usePipelineStore } from '@/store/pipeline';
import { NodeBadge, NodeShell } from '../node-shell';

export function ScriptNode(_props: NodeProps) {
	const scriptTitle = usePipelineStore((s) => s.scriptTitle);
	const scriptLines = usePipelineStore((s) => s.scriptLines);
	const setScriptLines = usePipelineStore((s) => s.setScriptLines);

	const wordCount = scriptLines
		.filter((l) => l.trim())
		.reduce((acc, l) => acc + l.trim().split(/\s+/).length, 0);

	const updateLine = (index: number, value: string) => {
		const next = [...scriptLines];
		next[index] = value;
		setScriptLines(next);
	};

	const removeLine = (index: number) => {
		setScriptLines(scriptLines.filter((_, i) => i !== index));
	};

	return (
		<NodeShell
			icon={ScrollText}
			title="Script"
			accent="bg-orange-500/15 text-orange-300"
			badge={
				<NodeBadge variant={scriptLines.length ? 'success' : 'default'}>
					{scriptLines.length ? `${scriptLines.length} lines` : 'empty'}
				</NodeBadge>
			}
			footer={
				scriptLines.length > 0 ? (
					<div className="flex items-center justify-between border-t border-border/60 px-4 py-2 text-xs text-muted-foreground">
						<span className="truncate pr-2">{scriptTitle || 'untitled'}</span>
						<span className="shrink-0">{wordCount} words</span>
					</div>
				) : undefined
			}
		>
			{scriptLines.length === 0 ? (
				<p className="text-xs leading-relaxed text-muted-foreground">
					No script yet. Hit{' '}
					<span className="text-orange-300">Generate script</span> on the Topic
					node — lines land here fully editable.
				</p>
			) : (
				<div className="space-y-2">
					{scriptLines.map((line, i) => {
						const isPunchline = i === scriptLines.length - 1;
						return (
							// biome-ignore lint/suspicious/noArrayIndexKey: script lines are positional
							<div key={i} className="flex items-center gap-1.5">
								<Input
									value={line}
									onChange={(e) => updateLine(i, e.target.value)}
									className={`h-8 text-xs ${
										isPunchline ? 'border-amber-500/40 bg-amber-500/5' : ''
									}`}
									aria-label={`Script line ${i + 1}`}
								/>
								<Button
									variant="ghost"
									size="icon"
									className="size-7 shrink-0 text-muted-foreground hover:text-red-400"
									onClick={() => removeLine(i)}
									aria-label={`Remove line ${i + 1}`}
								>
									<Trash2 className="size-3.5" />
								</Button>
								{isPunchline && (
									<span
										className="shrink-0 rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-amber-400"
										title="Punchline — gets the SFX"
									>
										💥
									</span>
								)}
							</div>
						);
					})}
					<Button
						variant="outline"
						size="sm"
						className="w-full border-dashed text-xs"
						onClick={() => setScriptLines([...scriptLines, ''])}
					>
						<Plus className="size-3.5" /> Add line
					</Button>
				</div>
			)}
		</NodeShell>
	);
}
