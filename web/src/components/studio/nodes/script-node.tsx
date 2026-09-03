'use client';

// Script Node: generated or pasted custom script. Every line stays
// editable, reorderable, and removable; the last line is the punchline.
// Confirming the script (or applying a pasted custom script) unlocks the
// Voiceover + Gameplay nodes in stepwise mode.

import type { NodeProps } from '@xyflow/react';
import {
	ArrowRight,
	CheckCircle2,
	ChevronDown,
	ChevronUp,
	ClipboardPaste,
	Plus,
	Sparkles,
	Trash2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { estimateSpokenSeconds, splitScriptText } from '@/lib/script-split';
import { cn } from '@/lib/utils';
import { usePipelineStore } from '@/store/pipeline';
import { NodeBadge, NodeShell } from '../node-shell';

function updateAt(list: string[], index: number, value: string): string[] {
	const next = [...list];
	next[index] = value;
	return next;
}

function moveAt(list: string[], index: number, delta: number): string[] {
	const target = index + delta;
	if (target < 0 || target >= list.length) return list;
	const next = [...list];
	[next[index], next[target]] = [next[target], next[index]];
	return next;
}

export function ScriptNode(_props: NodeProps) {
	const topic = usePipelineStore((s) => s.topic);
	const generating = usePipelineStore((s) => s.generating);
	const generatingError = usePipelineStore((s) => s.generatingError);
	const scriptMode = usePipelineStore((s) => s.scriptMode);
	const setScriptMode = usePipelineStore((s) => s.setScriptMode);
	const scriptTitle = usePipelineStore((s) => s.scriptTitle);
	const scriptLines = usePipelineStore((s) => s.scriptLines);
	const setScriptLines = usePipelineStore((s) => s.setScriptLines);
	const customScriptText = usePipelineStore((s) => s.customScriptText);
	const setCustomScriptText = usePipelineStore((s) => s.setCustomScriptText);
	const applyCustomScript = usePipelineStore((s) => s.applyCustomScript);
	const scriptConfirmed = usePipelineStore((s) => s.scriptConfirmed);
	const confirmScript = usePipelineStore((s) => s.confirmScript);
	const generateScript = usePipelineStore((s) => s.generateScript);

	const wordCount = scriptLines.reduce(
		(total, line) =>
			total + (line.trim() ? line.trim().split(/\s+/).length : 0),
		0
	);
	const spokenSeconds = Math.round(estimateSpokenSeconds(wordCount));
	const customLines = customScriptText.trim()
		? splitScriptText(customScriptText)
		: [];

	const tabClass = (active: boolean) =>
		cn(
			'flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors',
			active
				? 'bg-orange-600 text-white shadow-sm'
				: 'text-muted-foreground hover:text-foreground'
		);

	return (
		<NodeShell
			icon={Sparkles}
			title="Script"
			accent="bg-orange-500/15 text-orange-300"
			badge={
				<NodeBadge variant={scriptConfirmed ? 'success' : 'default'}>
					{scriptConfirmed
						? 'confirmed'
						: scriptLines.length
							? `${scriptLines.length} lines`
							: 'empty'}
				</NodeBadge>
			}
		>
			<div className="space-y-3">
				{/* Mode tabs: LLM-generated vs pasted custom script */}
				<div
					className="flex gap-1 rounded-lg border border-border/60 bg-muted/40 p-0.5"
					data-testid="script-mode-tabs"
				>
					<button
						type="button"
						onClick={() => setScriptMode('generated')}
						aria-pressed={scriptMode === 'generated'}
						className={tabClass(scriptMode === 'generated')}
					>
						<Sparkles className="size-3.5" />
						Generated
					</button>
					<button
						type="button"
						onClick={() => setScriptMode('custom')}
						aria-pressed={scriptMode === 'custom'}
						className={tabClass(scriptMode === 'custom')}
					>
						<ClipboardPaste className="size-3.5" />
						Custom
					</button>
				</div>

				{scriptMode === 'generated' && scriptLines.length === 0 && (
					<p className="text-center text-xs text-muted-foreground">
						{topic.trim()
							? 'Generate a script from your topic, or switch to Custom to paste your own.'
							: 'Enter a topic in the Topic node first, or switch to Custom to paste your own script.'}
					</p>
				)}

				{scriptMode === 'generated' && (
					<Button
						className="w-full gap-1.5 bg-orange-600 text-white hover:bg-orange-500"
						onClick={() => generateScript()}
						disabled={generating || !topic.trim()}
					>
						<Sparkles className="size-4" />
						{generating ? 'Generating…' : 'Generate script'}
					</Button>
				)}

				{scriptMode === 'custom' && (
					<div className="space-y-2">
						<Label
							htmlFor="custom-script-input"
							className="text-[11px] text-muted-foreground"
						>
							Paste / write your script
						</Label>
						<Textarea
							id="custom-script-input"
							data-testid="custom-script-input"
							value={customScriptText}
							onChange={(e) => setCustomScriptText(e.target.value)}
							placeholder={
								'Paste your whole script here…\n\nBlank lines and sentence punctuation split it into timed lines automatically.'
							}
							className="min-h-[110px] resize-y text-xs"
						/>
						<div className="flex items-center justify-between text-[11px] text-muted-foreground">
							<span>
								{customLines.length > 0
									? `${customLines.length} lines · ~${Math.round(
											estimateSpokenSeconds(
												customLines.reduce(
													(total, line) => total + line.split(/\s+/).length,
													0
												)
											)
										)}s of speech`
									: 'No LLM call — splits by paragraphs & punctuation'}
							</span>
						</div>
						<Button
							className="w-full gap-1.5 bg-orange-600 text-white hover:bg-orange-500"
							onClick={() => applyCustomScript()}
							disabled={customLines.length === 0}
						>
							<CheckCircle2 className="size-4" />
							Use this script
						</Button>
						<p className="text-center text-[11px] text-muted-foreground">
							Instantly unlocks voiceover &amp; gameplay — lines stay editable
							below.
						</p>
					</div>
				)}

				{generatingError && (
					<p
						className="rounded-md bg-red-500/10 px-2 py-1.5 text-[11px] text-red-400"
						data-testid="script-error"
					>
						{generatingError}
					</p>
				)}

				{scriptLines.length > 0 && (
					<div className="space-y-2" data-testid="script-lines">
						{scriptLines.map((line, i) => (
							// biome-ignore lint/suspicious/noArrayIndexKey: script lines are positional
							<div key={i} className="flex items-center gap-1">
								<span
									className="w-5 shrink-0 text-center text-[10px] text-muted-foreground"
									title={i === scriptLines.length - 1 ? 'Punchline' : undefined}
								>
									{i === scriptLines.length - 1 ? '💥' : i + 1}
								</span>
								<Input
									value={line}
									onChange={(e) =>
										setScriptLines(updateAt(scriptLines, i, e.target.value))
									}
									className="h-8 min-w-0 flex-1 border-border/60 bg-background/60 text-xs"
									aria-label={`Script line ${i + 1}`}
								/>
								<div className="flex shrink-0 items-center">
									<Button
										variant="ghost"
										size="icon"
										className="size-6 text-muted-foreground hover:text-foreground"
										onClick={() => setScriptLines(moveAt(scriptLines, i, -1))}
										disabled={i === 0}
										aria-label={`Move line ${i + 1} up`}
									>
										<ChevronUp className="size-3" />
									</Button>
									<Button
										variant="ghost"
										size="icon"
										className="size-6 text-muted-foreground hover:text-foreground"
										onClick={() => setScriptLines(moveAt(scriptLines, i, 1))}
										disabled={i === scriptLines.length - 1}
										aria-label={`Move line ${i + 1} down`}
									>
										<ChevronDown className="size-3" />
									</Button>
									<Button
										variant="ghost"
										size="icon"
										className="size-6 text-muted-foreground hover:text-red-400"
										onClick={() =>
											setScriptLines(
												scriptLines.filter((_, index) => index !== i)
											)
										}
										disabled={scriptLines.length <= 1}
										aria-label={`Delete line ${i + 1}`}
									>
										<Trash2 className="size-3" />
									</Button>
								</div>
							</div>
						))}

						<Button
							variant="ghost"
							size="sm"
							className="h-7 w-full gap-1 text-[11px] text-muted-foreground hover:text-foreground"
							onClick={() => setScriptLines([...scriptLines, ''])}
						>
							<Plus className="size-3" />
							Add line
						</Button>

						<div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
							<span className="truncate" title={scriptTitle}>
								“{scriptTitle || 'untitled'}”
							</span>
							<span className="shrink-0">
								{wordCount} words · ~{spokenSeconds}s
							</span>
						</div>

						{!scriptConfirmed && (
							<Button
								className="w-full gap-1.5 bg-orange-600 text-white hover:bg-orange-500"
								onClick={() => confirmScript()}
								data-testid="confirm-script-btn"
							>
								<ArrowRight className="size-4" />
								Confirm script &amp; continue
							</Button>
						)}
					</div>
				)}
			</div>
		</NodeShell>
	);
}
