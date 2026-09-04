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
	Tags,
	Trash2,
	X
} from 'lucide-react';
import { useState } from 'react';
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

/** Editable keyword chip set: the visual search phrases that ship with a
 * generated script (10+) and drive the auto-selected stock montage. */
function KeywordChips() {
	const keywords = usePipelineStore((s) => s.scriptKeywords);
	const addKeyword = usePipelineStore((s) => s.addScriptKeyword);
	const removeKeyword = usePipelineStore((s) => s.removeScriptKeyword);
	const [draft, setDraft] = useState('');

	const add = () => {
		if (!draft.trim()) return;
		addKeyword(draft);
		setDraft('');
	};

	return (
		<div className="space-y-1.5" data-testid="script-keywords">
			<div className="flex items-center justify-between">
				<Label className="flex items-center gap-1.5 text-[11px] text-zinc-500">
					<Tags className="size-3" />
					Keywords
				</Label>
				<span className="text-[10px] text-zinc-600">{keywords.length}</span>
			</div>
			<div className="flex flex-wrap gap-1">
				{keywords.map((keyword, i) => (
					<span
						key={keyword}
						className="flex items-center gap-1 rounded-full border border-orange-500/25 bg-orange-500/10 py-0.5 pr-1 pl-2.5 text-[11px] text-orange-300"
					>
						{keyword}
						<button
							type="button"
							onClick={() => removeKeyword(i)}
							aria-label={`Remove keyword ${keyword}`}
							className="rounded-full p-0.5 text-orange-300/60 transition-colors hover:bg-orange-500/20 hover:text-red-400"
						>
							<X className="size-3" />
						</button>
					</span>
				))}
			</div>
			<div className="flex gap-1.5">
				<Input
					value={draft}
					onChange={(e) => setDraft(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === 'Enter') {
							e.preventDefault();
							add();
						}
					}}
					placeholder={
						keywords.length ? 'Add keyword' : 'e.g. city street night'
					}
					className="h-7 text-[11px]"
					aria-label="Add script keyword"
				/>
				<Button
					variant="outline"
					size="sm"
					className="h-7 shrink-0 px-2"
					onClick={add}
					disabled={!draft.trim()}
					aria-label="Add keyword"
				>
					<Plus className="size-3" />
				</Button>
			</div>
		</div>
	);
}

export function ScriptNode(_props: NodeProps) {
	const topic = usePipelineStore((s) => s.topic);
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
	const generatingError = usePipelineStore((s) => s.generatingError);

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
			'flex flex-1 items-center justify-center gap-1.5 rounded-full px-2 py-1.5 text-[11px] font-medium transition-all active:scale-[0.98]',
			active
				? 'bg-orange-500 text-zinc-950'
				: 'text-zinc-400 hover:text-zinc-100'
		);

	return (
		<NodeShell
			icon={Sparkles}
			title="Script"
			badge={
				scriptLines.length > 0 ? (
					<NodeBadge variant={scriptConfirmed ? 'success' : 'default'}>
						{scriptConfirmed ? 'confirmed' : `${scriptLines.length} lines`}
					</NodeBadge>
				) : null
			}
		>
			<div className="space-y-3">
				{/* Mode tabs: LLM-generated vs pasted custom script */}
				<div
					className="flex gap-0.5 rounded-full border border-white/10 bg-white/[0.03] p-0.5"
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
					<p className="text-center text-xs text-zinc-500">
						{topic.trim()
							? 'Generate from your topic in the Topic node.'
							: 'Enter a topic first, or paste a custom script.'}
					</p>
				)}

				{scriptMode === 'custom' && (
					<div className="space-y-2">
						<Textarea
							id="custom-script-input"
							data-testid="custom-script-input"
							value={customScriptText}
							onChange={(e) => setCustomScriptText(e.target.value)}
							placeholder="Paste your script here. Blank lines split it into timed lines."
							className="min-h-[110px] resize-y text-xs"
						/>
						<div className="flex items-center justify-between text-[11px] text-zinc-500">
							<span>
								{customLines.length > 0
									? `${customLines.length} lines · ~${Math.round(
											estimateSpokenSeconds(
												customLines.reduce(
													(total, line) => total + line.split(/\s+/).length,
													0
												)
											)
										)}s`
									: 'No LLM call, instant'}
							</span>
						</div>
						<Button
							className="w-full gap-1.5"
							onClick={() => applyCustomScript()}
							disabled={customLines.length === 0}
						>
							<CheckCircle2 className="size-4" />
							Use this script
						</Button>
					</div>
				)}

				{generatingError && (
					<p
						className="rounded-lg bg-red-500/10 px-2 py-1.5 text-[11px] text-red-400"
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
									className={cn(
										'w-5 shrink-0 text-center text-[10px]',
										i === scriptLines.length - 1
											? 'font-semibold text-orange-400'
											: 'text-zinc-600'
									)}
									title={i === scriptLines.length - 1 ? 'Punchline' : undefined}
								>
									{i + 1}
								</span>
								<Input
									value={line}
									onChange={(e) =>
										setScriptLines(updateAt(scriptLines, i, e.target.value))
									}
									className="h-8 min-w-0 flex-1 text-xs"
									aria-label={`Script line ${i + 1}`}
								/>
								<div className="flex shrink-0 items-center">
									<Button
										variant="ghost"
										size="icon"
										className="size-6 text-zinc-500 hover:text-zinc-200"
										onClick={() => setScriptLines(moveAt(scriptLines, i, -1))}
										disabled={i === 0}
										aria-label={`Move line ${i + 1} up`}
									>
										<ChevronUp className="size-3" />
									</Button>
									<Button
										variant="ghost"
										size="icon"
										className="size-6 text-zinc-500 hover:text-zinc-200"
										onClick={() => setScriptLines(moveAt(scriptLines, i, 1))}
										disabled={i === scriptLines.length - 1}
										aria-label={`Move line ${i + 1} down`}
									>
										<ChevronDown className="size-3" />
									</Button>
									<Button
										variant="ghost"
										size="icon"
										className="size-6 text-zinc-500 hover:text-red-400"
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
							className="h-7 w-full gap-1 text-[11px] text-zinc-500 hover:text-zinc-200"
							onClick={() => setScriptLines([...scriptLines, ''])}
						>
							<Plus className="size-3" />
							Add line
						</Button>

						{/* Visual keywords shipped with the script, editable, and the
						 * search set for the auto-selected stock montage (Step 4). */}
						<KeywordChips />

						<div className="flex items-center justify-between gap-2 text-[11px] text-zinc-500">
							<span className="truncate" title={scriptTitle}>
								{scriptTitle || 'untitled'}
							</span>
							<span className="shrink-0">
								{wordCount} words · ~{spokenSeconds}s
							</span>
						</div>

						{!scriptConfirmed && (
							<Button
								className="w-full gap-1.5"
								onClick={() => confirmScript()}
								data-testid="confirm-script-btn"
							>
								<ArrowRight className="size-4" />
								Confirm script
							</Button>
						)}
					</div>
				)}
			</div>
		</NodeShell>
	);
}
