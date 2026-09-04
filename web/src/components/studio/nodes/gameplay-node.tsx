'use client';

// Video Background Node (Step 4): pick the background for the render.
//
// Two tabs:
//  1. "Presets" - the bundled gameplay loop catalog.
//  2. "Stock" - one clear action: "Fetch assets" queries
//     1-3s vertical clips matching the script's keywords and duration
//     (Pexels / Pixabay via the vault or server keys) and confirms the
//     background on its own, unlocking Preview & Export. A compact
//     "Ready" summary replaces the old sprawling playlist; per-clip
//     details stay one collapsed disclosure away.
//
// Confirming the background unlocks the Preview & Export node (Step 5).

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import {
	Check,
	ChevronDown,
	Clapperboard,
	Dices,
	Film,
	Gamepad2,
	Loader2,
	Wand2,
	X,
	Zap
} from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { GAMEPLAY_FALLBACK } from '@/lib/catalog';
import { stockCredentialParams } from '@/lib/credentials';
import { MemeforgeAPI } from '@/lib/memeforge';
import { estimateSpokenSeconds } from '@/lib/script-split';
import { cn } from '@/lib/utils';
import { useCredentialsStore } from '@/store/credentials';
import { usePipelineStore } from '@/store/pipeline';
import type { GameplayClip } from '@/types/studio';
import { NodeBadge, NodeShell } from '../node-shell';
import { InlineVaultSection } from '../settings-drawer';

type BackgroundTab = 'preset' | 'stock';

function formatDuration(seconds: number): string {
	if (seconds < 60) return `${Math.round(seconds)}s`;
	return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`;
}

/** Human label for the target video length ("60s", "~2m"). */
function formatVideoLength(seconds: number): string {
	if (seconds < 90) return `${Math.round(seconds)}s`;
	return `~${Math.max(1, Math.round(seconds / 60))}m`;
}

export function GameplayNode(_props: NodeProps) {
	const gameplayId = usePipelineStore((s) => s.gameplayId);
	const setGameplay = usePipelineStore((s) => s.setGameplay);
	const backgroundMode = usePipelineStore((s) => s.backgroundMode);
	const setBackgroundMode = usePipelineStore((s) => s.setBackgroundMode);
	const stockClips = usePipelineStore((s) => s.stockClips);
	const backgroundChosen = usePipelineStore((s) => s.backgroundChosen);
	const confirmBackground = usePipelineStore((s) => s.confirmBackground);

	// The active tab mirrors the store's background mode so switching
	// tabs (or picking a clip) always makes the intent explicit.
	const setTab = (tab: BackgroundTab) => setBackgroundMode(tab);

	const { data: clips, isLoading } = useQuery({
		queryKey: ['gameplays'],
		queryFn: MemeforgeAPI.listGameplays,
		retry: false,
		staleTime: 60_000
	});

	const catalog = clips?.length ? clips : GAMEPLAY_FALLBACK;
	const selected = catalog.find((c) => c.id === gameplayId);

	const presetReady =
		backgroundMode === 'preset' && Boolean(selected?.available);
	const stockReady = backgroundMode === 'stock' && stockClips.length > 0;
	const canConfirm = presetReady || stockReady;

	return (
		<NodeShell
			icon={Clapperboard}
			title="Background"
			handles="both"
			className="w-[400px]"
			badge={
				backgroundChosen ? (
					<NodeBadge variant="success">confirmed</NodeBadge>
				) : canConfirm ? (
					<NodeBadge variant="warn">pick ready</NodeBadge>
				) : null
			}
		>
			{/* Tab switcher */}
			<div
				className="flex gap-0.5 rounded-full border border-white/10 bg-white/[0.03] p-0.5"
				role="tablist"
				aria-label="Background source"
			>
				<button
					type="button"
					role="tab"
					aria-selected={backgroundMode === 'preset'}
					onClick={() => setTab('preset')}
					className={cn(
						'flex flex-1 items-center justify-center gap-1.5 rounded-full px-2 py-1.5 text-xs font-medium transition-all active:scale-[0.98]',
						backgroundMode === 'preset'
							? 'bg-orange-500 text-zinc-950'
							: 'text-zinc-400 hover:text-zinc-100'
					)}
				>
					<Gamepad2 className="size-3.5" /> Presets
				</button>
				<button
					type="button"
					role="tab"
					aria-selected={backgroundMode === 'stock'}
					onClick={() => setTab('stock')}
					className={cn(
						'flex flex-1 items-center justify-center gap-1.5 rounded-full px-2 py-1.5 text-xs font-medium transition-all active:scale-[0.98]',
						backgroundMode === 'stock'
							? 'bg-orange-500 text-zinc-950'
							: 'text-zinc-400 hover:text-zinc-100'
					)}
				>
					<Film className="size-3.5" /> Stock
				</button>
			</div>

			{backgroundMode === 'preset' ? (
				<PresetTab
					catalog={catalog}
					selectedId={gameplayId}
					isLoading={Boolean(isLoading)}
					onSelect={setGameplay}
				/>
			) : (
				<StockTab />
			)}

			{/* Step 4 gate: confirming the background unlocks Preview & Export. */}
			<Button
				size="sm"
				onClick={confirmBackground}
				disabled={!canConfirm}
				aria-pressed={backgroundChosen}
				data-testid="confirm-background"
				className={cn(
					'w-full',
					backgroundChosen &&
						'border-orange-500/30 bg-orange-500/10 text-orange-300 hover:bg-orange-500/15'
				)}
				variant={backgroundChosen ? 'outline' : 'default'}
			>
				<Check className="size-4" />
				{backgroundChosen ? 'Background confirmed' : 'Confirm background'}
			</Button>
		</NodeShell>
	);
}

// --- Tab 1: preset gameplay loops -------------------------------------------

function PresetTab({
	catalog,
	selectedId,
	isLoading,
	onSelect
}: {
	catalog: GameplayClip[];
	selectedId: string;
	isLoading: boolean;
	onSelect: (id: string) => void;
}) {
	return (
		<>
			{isLoading ? (
				<div className="space-y-2">
					<div className="h-14 animate-pulse rounded-lg bg-white/[0.04]" />
					<div className="h-14 animate-pulse rounded-lg bg-white/[0.04]" />
				</div>
			) : (
				<div
					className="max-h-64 overflow-y-auto"
					data-testid="preset-gameplay-list"
				>
					{catalog.map((clip) => {
						const active = clip.id === selectedId;
						return (
							<button
								key={clip.id}
								type="button"
								onClick={() => onSelect(clip.id)}
								className={cn(
									'flex w-full items-center justify-between gap-2 border-b border-white/[0.06] px-2 py-2.5 text-left transition-colors last:border-b-0',
									active ? 'bg-orange-500/10' : 'hover:bg-white/[0.03]'
								)}
								aria-pressed={active}
							>
								<div className="min-w-0">
									<div className="flex items-center gap-2">
										<span className="text-xs font-medium text-zinc-200">
											{clip.label}
										</span>
										{clip.available ? (
											<span className="shrink-0 text-[10px] font-medium text-emerald-400">
												ready
											</span>
										) : (
											<span className="shrink-0 text-[10px] font-medium text-zinc-600">
												no asset
											</span>
										)}
									</div>
									<p className="mt-0.5 truncate text-[11px] text-zinc-500">
										{clip.description}
									</p>
								</div>
								{active && (
									<Check className="size-4 shrink-0 text-orange-400" />
								)}
							</button>
						);
					})}
				</div>
			)}
			<p className="text-[11px] text-zinc-600">
				Drop <code className="rounded bg-white/5 px-1">{'<id>.mp4'}</code> loops
				into{' '}
				<code className="rounded bg-white/5 px-1">server/assets/gameplay/</code>{' '}
				to mark clips ready.
			</p>
		</>
	);
}

// --- Tab 2: one-click stock montage ------------------------------------------

function StockTab() {
	const scriptLines = usePipelineStore((s) => s.scriptLines);
	const scriptKeywords = usePipelineStore((s) => s.scriptKeywords);
	const stockClips = usePipelineStore((s) => s.stockClips);
	const stockMontage = usePipelineStore((s) => s.stockMontage);
	const toggleStockClip = usePipelineStore((s) => s.toggleStockClip);
	const applyStockMontage = usePipelineStore((s) => s.applyStockMontage);
	const setStockMontage = usePipelineStore((s) => s.setStockMontage);
	const swapStockClip = usePipelineStore((s) => s.swapStockClip);
	const confirmBackground = usePipelineStore((s) => s.confirmBackground);

	// Vault keys take priority over the server .env for the stock search.
	const vaultKeys = useCredentialsStore((s) => s.keys);
	const stockCreds = () => stockCredentialParams(vaultKeys);

	const [notice, setNotice] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [building, setBuilding] = useState(false);
	const [swappingAt, setSwappingAt] = useState<number | null>(null);
	const [showClips, setShowClips] = useState(false);

	const wordCount = scriptLines
		.join(' ')
		.trim()
		.split(/\s+/)
		.filter(Boolean).length;
	const canAutoBuild = wordCount > 0 || scriptKeywords.length > 0;
	const neededSeconds = estimateSpokenSeconds(wordCount);

	// The single action: query Pexels / Pixabay with the script's keyword
	// set, fetch enough 1-3s vertical clips to cover the spoken duration,
	// and confirm the background so the next step unlocks immediately.
	const autoBuild = async (seed?: number) => {
		setBuilding(true);
		setError(null);
		try {
			const resp = await MemeforgeAPI.autoSelectStock({
				// The generated keyword set drives the searches; a custom
				// script falls back to server-side heuristic extraction.
				keywords: scriptKeywords.length ? scriptKeywords : undefined,
				script: scriptLines,
				duration_s: wordCount > 0 ? neededSeconds : undefined,
				segment_s: 2.25,
				seed,
				...stockCreds()
			});
			applyStockMontage(resp.clips);
			setNotice(resp.notice);
			// Proceed on success: the picks unlock Preview & Export.
			if (resp.clips.length > 0) confirmBackground();
		} catch (err: any) {
			setError(err?.response?.data?.detail ?? 'Montage auto-build failed.');
		} finally {
			setBuilding(false);
		}
	};

	// Per-clip swap (inside the collapsed details): fetch a different
	// clip for the same keyword, excluding current picks.
	const swapClip = async (index: number) => {
		const clip = stockClips[index];
		if (!clip?.keyword) return;
		setSwappingAt(index);
		setError(null);
		try {
			const resp = await MemeforgeAPI.autoSelectStock({
				keywords: [clip.keyword],
				duration_s: 2.25,
				segment_s: 2.25,
				seed: Date.now(),
				exclude: stockClips,
				...stockCreds()
			});
			const replacement = resp.clips[0];
			if (!replacement) {
				throw new Error('No alternative clip for this keyword.');
			}
			swapStockClip(index, replacement);
		} catch (err: any) {
			setError(
				err?.response?.data?.detail ?? err?.message ?? 'Clip swap failed.'
			);
		} finally {
			setSwappingAt(null);
		}
	};

	return (
		<>
			{/* Pexels / Pixabay keys: vault > server .env > curated demo clips. */}
			<InlineVaultSection
				title="Stock API keys"
				compact
				fields={[
					{
						field: 'pexelsApiKey',
						label: 'Pexels API Key',
						placeholder: 'free key from pexels.com/api',
						serverFlag: 'stock_pexels'
					},
					{
						field: 'pixabayApiKey',
						label: 'Pixabay API Key',
						placeholder: 'free key from pixabay.com/api',
						serverFlag: 'stock_pixabay'
					}
				]}
			/>

			{/* The one action: build the montage in the background. */}
			<div
				className="space-y-2.5 rounded-xl border border-white/10 p-3"
				data-testid="montage-auto-build"
			>
				<div className="min-w-0">
					<p className="text-xs font-medium text-zinc-200">
						Stock video montage
					</p>
					<p className="mt-0.5 text-[11px] leading-snug text-zinc-500">
						{scriptKeywords.length
							? `${scriptKeywords.length} keywords from your script, ~2s cuts`
							: 'Keywords derived from your script, ~2s cuts'}
					</p>
				</div>
				<Button
					size="sm"
					className="w-full"
					onClick={() => autoBuild()}
					disabled={building || !canAutoBuild}
					data-testid="auto-build-montage"
				>
					{building ? (
						<Loader2 className="size-4 animate-spin" />
					) : (
						<Wand2 className="size-4" />
					)}
					{building
						? 'Downloading assets...'
						: stockClips.length > 0
							? 'Refetch assets'
							: 'Fetch assets'}
				</Button>
			</div>

			{/* Compact readiness summary: replaces the sprawling playlist. */}
			{stockClips.length > 0 && (
				<div
					className="space-y-2 rounded-xl border border-orange-500/25 bg-orange-500/[0.06] p-3"
					data-testid="stock-summary"
				>
					<div className="flex items-center gap-2 text-xs">
						<span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-orange-500/15">
							<Check className="size-3 text-orange-400" />
						</span>
						<span
							className="min-w-0 flex-1 truncate font-medium text-zinc-200"
							data-testid="montage-summary"
						>
							Ready · {stockClips.length} stock clips auto-selected for{' '}
							{formatVideoLength(neededSeconds)} video
						</span>
					</div>
					<div className="flex flex-wrap items-center gap-1.5">
						<button
							type="button"
							onClick={() => autoBuild(Date.now())}
							disabled={building}
							data-testid="montage-shuffle"
							className="flex items-center gap-1 rounded-full border border-white/10 px-2.5 py-0.5 text-[11px] text-zinc-400 transition-all hover:border-orange-500/40 hover:text-orange-300 active:scale-[0.98]"
						>
							<Dices className="size-3" />
							Shuffle
						</button>
						<button
							type="button"
							onClick={() => setStockMontage(!stockMontage)}
							aria-pressed={stockMontage}
							data-testid="montage-toggle"
							title={
								stockMontage
									? 'Fast-switching montage: each clip plays ~1.5-3s before the cut'
									: 'Playlist: each clip plays in full, in order'
							}
							className={cn(
								'flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] transition-all active:scale-[0.98]',
								stockMontage
									? 'border-orange-500/50 bg-orange-500/15 text-orange-300'
									: 'border-white/10 text-zinc-400 hover:text-zinc-100'
							)}
						>
							<Zap className="size-3" />
							{stockMontage ? 'Fast cuts' : 'Full clips'}
						</button>
						<button
							type="button"
							onClick={() => setShowClips((s) => !s)}
							aria-expanded={showClips}
							data-testid="montage-details-toggle"
							className="flex items-center gap-1 rounded-full border border-white/10 px-2.5 py-0.5 text-[11px] text-zinc-400 transition-all hover:border-orange-500/40 hover:text-orange-300 active:scale-[0.98]"
						>
							<ChevronDown
								className={cn(
									'size-3 transition-transform',
									showClips && 'rotate-180'
								)}
							/>
							Clips
						</button>
					</div>

					{/* Collapsed by default: the ordered picks, one line each. */}
					{showClips && (
						<ol
							className="max-h-40 space-y-1 overflow-y-auto pr-1"
							data-testid="stock-picks"
						>
							{stockClips.map((clip, i) => (
								<li
									key={clip.url}
									className="flex items-center gap-1.5 rounded-lg bg-white/[0.03] px-2 py-1 text-[11px]"
								>
									<span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-orange-500/15 text-[9px] font-semibold text-orange-300">
										{i + 1}
									</span>
									<span
										className="min-w-0 flex-1 truncate text-zinc-300"
										title={
											clip.keyword
												? `${clip.label} (keyword: ${clip.keyword})`
												: clip.label
										}
									>
										{clip.label}
									</span>
									{clip.keyword && (
										<span
											className="max-w-24 shrink-0 truncate rounded-full bg-orange-500/10 px-1.5 text-[9px] text-orange-300"
											title={`Keyword: ${clip.keyword}`}
										>
											{clip.keyword}
										</span>
									)}
									{clip.keyword && (
										<button
											type="button"
											onClick={() => swapClip(i)}
											disabled={swappingAt === i}
											title={`Swap this clip (searches "${clip.keyword}" for another)`}
											aria-label={`Swap ${clip.label}`}
											className="shrink-0 rounded p-0.5 text-zinc-500 transition-colors hover:text-orange-300"
										>
											{swappingAt === i ? (
												<Loader2 className="size-3 animate-spin" />
											) : (
												<Dices className="size-3" />
											)}
										</button>
									)}
									<span className="shrink-0 text-zinc-600">
										{formatDuration(clip.duration_s)}
									</span>
									<button
										type="button"
										onClick={() => toggleStockClip(clip)}
										aria-label={`Remove ${clip.label}`}
										className="shrink-0 rounded p-0.5 text-zinc-500 transition-colors hover:text-red-400"
									>
										<X className="size-3" />
									</button>
								</li>
							))}
						</ol>
					)}
				</div>
			)}

			{notice && (
				<p className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-2.5 py-1.5 text-[11px] leading-snug text-amber-300">
					{notice}
				</p>
			)}

			{error && (
				<p className="text-xs text-red-400" role="alert">
					{error}
				</p>
			)}
		</>
	);
}
