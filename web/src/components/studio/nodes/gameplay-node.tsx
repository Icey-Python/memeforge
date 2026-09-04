'use client';

// Video Background Node (Step 4): pick the background for the render.
//
// Two tabs:
//  1. "Preset Gameplays" — the bundled loop catalog.
//  2. "Stock Video Search" — Pexels / Pixabay vertical clips: auto-suggest
//     visual keywords from the script (AI, heuristic offline fallback),
//     search, hover-to-preview thumbnails, and an ordered multi-clip
//     selection. The backend downloads + stitches the picks (with cuts)
//     to exactly cover the voiceover duration.
//
// Confirming the background unlocks the Preview & Export node (Step 5).

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import {
	Check,
	Clapperboard,
	Dices,
	Film,
	Gamepad2,
	Loader2,
	Play,
	Search,
	Sparkles,
	Wand2,
	X,
	Zap
} from 'lucide-react';
import { useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { GAMEPLAY_FALLBACK } from '@/lib/catalog';
import { resolveLLMCredential, stockCredentialParams } from '@/lib/credentials';
import { MemeforgeAPI } from '@/lib/memeforge';
import { estimateSpokenSeconds } from '@/lib/script-split';
import { cn } from '@/lib/utils';
import { useCredentialsStore } from '@/store/credentials';
import { usePipelineStore } from '@/store/pipeline';
import type { GameplayClip, StockVideoResult } from '@/types/studio';
import { NodeBadge, NodeShell } from '../node-shell';
import { InlineVaultSection } from '../settings-drawer';

type BackgroundTab = 'preset' | 'stock';

function formatDuration(seconds: number): string {
	if (seconds < 60) return `${Math.round(seconds)}s`;
	return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`;
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
			title="Video Background"
			accent="bg-sky-500/15 text-sky-300"
			handles="both"
			className="w-[400px]"
			badge={
				backgroundChosen ? (
					<NodeBadge variant="success">confirmed</NodeBadge>
				) : canConfirm ? (
					<NodeBadge variant="warn">pick ready</NodeBadge>
				) : (
					<NodeBadge>choose one</NodeBadge>
				)
			}
		>
			{/* Tab switcher */}
			<div
				className="flex rounded-lg border border-border/60 bg-muted/40 p-0.5"
				role="tablist"
				aria-label="Background source"
			>
				<button
					type="button"
					role="tab"
					aria-selected={backgroundMode === 'preset'}
					onClick={() => setTab('preset')}
					className={cn(
						'flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors',
						backgroundMode === 'preset'
							? 'bg-card text-foreground shadow-sm'
							: 'text-muted-foreground hover:text-foreground'
					)}
				>
					<Gamepad2 className="size-3.5" /> Preset Gameplays
				</button>
				<button
					type="button"
					role="tab"
					aria-selected={backgroundMode === 'stock'}
					onClick={() => setTab('stock')}
					className={cn(
						'flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors',
						backgroundMode === 'stock'
							? 'bg-card text-foreground shadow-sm'
							: 'text-muted-foreground hover:text-foreground'
					)}
				>
					<Film className="size-3.5" /> Stock Video Search
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
					'w-full font-semibold',
					backgroundChosen
						? 'border-sky-500/40 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20'
						: 'bg-gradient-to-r from-sky-600 to-cyan-600 text-white hover:from-sky-500 hover:to-cyan-500'
				)}
			>
				{backgroundChosen ? (
					<>
						<Check className="size-4" /> Background confirmed
					</>
				) : (
					<>
						<Check className="size-4" /> Confirm Video Background ➔
					</>
				)}
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
					<div className="h-14 animate-pulse rounded-lg bg-muted/60" />
					<div className="h-14 animate-pulse rounded-lg bg-muted/60" />
				</div>
			) : (
				<div className="grid max-h-64 gap-2 overflow-y-auto pr-1">
					{catalog.map((clip) => {
						const active = clip.id === selectedId;
						return (
							<button
								key={clip.id}
								type="button"
								onClick={() => onSelect(clip.id)}
								className={cn(
									'rounded-lg border p-3 text-left transition-colors',
									active
										? 'border-sky-500/60 bg-sky-500/10'
										: 'border-border/60 bg-muted/20 hover:border-sky-500/30'
								)}
								aria-pressed={active}
							>
								<div className="flex items-center justify-between gap-2">
									<span className="text-xs font-semibold">{clip.label}</span>
									{clip.available ? (
										<span className="shrink-0 text-[10px] font-medium uppercase text-emerald-400">
											ready
										</span>
									) : (
										<span className="shrink-0 text-[10px] font-medium uppercase text-amber-400">
											no asset
										</span>
									)}
								</div>
								<p className="mt-1 text-[11px] leading-snug text-muted-foreground">
									{clip.description}
								</p>
							</button>
						);
					})}
				</div>
			)}
			<p className="text-[11px] leading-snug text-muted-foreground">
				Drop <code className="rounded bg-muted px-1">{'<id>.mp4'}</code> loops
				into{' '}
				<code className="rounded bg-muted px-1">server/assets/gameplay/</code>{' '}
				to mark clips ready.
			</p>
		</>
	);
}

// --- Tab 2: stock video search ----------------------------------------------

function StockTab() {
	const scriptLines = usePipelineStore((s) => s.scriptLines);
	const scriptKeywords = usePipelineStore((s) => s.scriptKeywords);
	const model = usePipelineStore((s) => s.model);
	const stockClips = usePipelineStore((s) => s.stockClips);
	const stockMontage = usePipelineStore((s) => s.stockMontage);
	const toggleStockClip = usePipelineStore((s) => s.toggleStockClip);
	const applyStockMontage = usePipelineStore((s) => s.applyStockMontage);
	const setStockMontage = usePipelineStore((s) => s.setStockMontage);
	const swapStockClip = usePipelineStore((s) => s.swapStockClip);

	// Vault keys take priority over the server .env for both the stock
	// search and the LLM keyword suggestion.
	const vaultKeys = useCredentialsStore((s) => s.keys);
	const llmCreds = () => resolveLLMCredential(model, vaultKeys);
	const stockCreds = () => stockCredentialParams(vaultKeys);

	const [query, setQuery] = useState('');
	const [results, setResults] = useState<StockVideoResult[]>([]);
	const [notice, setNotice] = useState<string | null>(null);
	const [searching, setSearching] = useState(false);
	const [suggesting, setSuggesting] = useState(false);
	const [suggestions, setSuggestions] = useState<string[]>([]);
	const [error, setError] = useState<string | null>(null);

	// Auto-selected montage state — the picks themselves live in the
	// pipeline store; this is just the build summary + in-flight flags.
	const [building, setBuilding] = useState(false);
	const [swappingAt, setSwappingAt] = useState<number | null>(null);
	const [montageInfo, setMontageInfo] = useState<{
		segmentsNeeded: number;
		segmentS: number;
	} | null>(null);

	const wordCount = scriptLines
		.join(' ')
		.trim()
		.split(/\s+/)
		.filter(Boolean).length;
	const canAutoBuild = wordCount > 0 || scriptKeywords.length > 0;

	const search = async (q: string) => {
		const term = q.trim();
		if (term.length < 2) {
			setError('Type at least 2 characters to search.');
			return;
		}
		setSearching(true);
		setError(null);
		try {
			const resp = await MemeforgeAPI.searchStock(term, stockCreds());
			setResults(resp.videos);
			setNotice(resp.notice);
			if (resp.videos.length === 0) {
				setError('No clips found — try a simpler search term.');
			}
		} catch (err: any) {
			setError(err?.response?.data?.detail ?? 'Stock search failed.');
		} finally {
			setSearching(false);
		}
	};

	// One-click montage: query Pexels / Pixabay with the script's keyword
	// set and fetch enough 1-3s vertical clips to cover the spoken
	// duration. A fresh seed reshuffles the picks.
	const autoBuild = async (seed?: number) => {
		setBuilding(true);
		setError(null);
		try {
			const resp = await MemeforgeAPI.autoSelectStock({
				// The generated keyword set drives the searches; a custom
				// script falls back to server-side heuristic extraction.
				keywords: scriptKeywords.length ? scriptKeywords : undefined,
				script: scriptLines,
				duration_s:
					wordCount > 0 ? estimateSpokenSeconds(wordCount) : undefined,
				segment_s: 2.25,
				seed,
				...stockCreds()
			});
			applyStockMontage(resp.clips);
			setNotice(resp.notice);
			setMontageInfo({
				segmentsNeeded: resp.segments_needed,
				segmentS: resp.segment_s
			});
		} catch (err: any) {
			setError(err?.response?.data?.detail ?? 'Montage auto-build failed.');
		} finally {
			setBuilding(false);
		}
	};

	// Per-clip swap: fetch a different clip for the same keyword,
	// excluding everything already in the playlist.
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

	// AI keyword suggestion: 3-5 visual queries from the script, generated
	// by the configured LLM (deterministic heuristic when it's offline).
	const suggest = async () => {
		const script = scriptLines.join('\n').trim();
		if (!script) {
			setError('Generate or paste a script first.');
			return;
		}
		setSuggesting(true);
		setError(null);
		try {
			const creds = llmCreds();
			const resp = await MemeforgeAPI.extractKeywords({
				script,
				provider: model.provider,
				model: model.model || undefined,
				base_url: creds.baseUrl,
				api_key: creds.apiKey
			});
			setSuggestions(resp.queries);
		} catch (err: any) {
			setError(err?.response?.data?.detail ?? 'Keyword suggestion failed.');
		} finally {
			setSuggesting(false);
		}
	};

	const togglePick = (video: StockVideoResult) => {
		toggleStockClip({
			provider: video.provider,
			id: video.id,
			url: video.video_url,
			duration_s: video.duration_s,
			label: video.title
		});
	};

	// Coverage: the render stitches picks with cuts/repeats to the exact
	// voiceover length, so >= needed duration means no visible looping.
	const neededSeconds = estimateSpokenSeconds(wordCount);
	const pickedSeconds = stockClips.reduce((sum, c) => sum + c.duration_s, 0);
	const coverage = neededSeconds > 0 ? pickedSeconds / neededSeconds : 0;

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

			{/* One-click fast-switching montage from the script keywords. */}
			<div
				className="space-y-1.5 rounded-lg border border-sky-500/30 bg-sky-500/5 p-2.5"
				data-testid="montage-auto-build"
			>
				<div className="flex items-center justify-between gap-2">
					<div className="min-w-0">
						<p className="text-[11px] font-semibold text-sky-300">
							Auto-build montage
						</p>
						<p className="text-[10px] leading-snug text-muted-foreground">
							{scriptKeywords.length
								? `${scriptKeywords.length} script keywords → ~2s cuts`
								: 'Keywords from your script → ~2s cuts'}
						</p>
					</div>
					<Button
						size="sm"
						className="h-7 shrink-0 gap-1 bg-sky-600 px-2.5 text-white hover:bg-sky-500"
						onClick={() => autoBuild()}
						disabled={building || !canAutoBuild}
						data-testid="auto-build-montage"
					>
						{building ? (
							<Loader2 className="size-3.5 animate-spin" />
						) : (
							<Wand2 className="size-3.5" />
						)}
						Build
					</Button>
				</div>
				{montageInfo && stockClips.length > 0 && (
					<div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
						<span data-testid="montage-summary">
							~{montageInfo.segmentsNeeded} cuts ·{' '}
							{montageInfo.segmentS.toFixed(1)}s each · {stockClips.length}{' '}
							unique clips
						</span>
						<button
							type="button"
							onClick={() => autoBuild(Date.now())}
							disabled={building}
							data-testid="montage-shuffle"
							className="flex shrink-0 items-center gap-1 rounded-full border border-border/60 px-2 py-0.5 transition-colors hover:border-sky-500/40 hover:text-sky-300"
						>
							<Dices className="size-3" />
							Shuffle
						</button>
					</div>
				)}
			</div>

			<div className="space-y-1.5">
				<Label htmlFor="stock-query">Or search vertical stock clips</Label>
				<div className="flex gap-1.5">
					<Input
						id="stock-query"
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === 'Enter') search(query);
						}}
						placeholder="e.g. city street night"
						className="h-8 text-xs"
						data-testid="stock-query-input"
					/>
					<Button
						size="sm"
						variant="outline"
						className="h-8 shrink-0 px-2.5"
						onClick={() => search(query)}
						disabled={searching}
						aria-label="Search stock videos"
					>
						{searching ? (
							<Loader2 className="size-3.5 animate-spin" />
						) : (
							<Search className="size-3.5" />
						)}
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="h-8 shrink-0 gap-1 px-2.5"
						onClick={suggest}
						disabled={suggesting}
						title="Suggest visual search keywords from your script (AI)"
						data-testid="suggest-keywords"
					>
						{suggesting ? (
							<Loader2 className="size-3.5 animate-spin" />
						) : (
							<Sparkles className="size-3.5" />
						)}
						<span className="hidden xl:inline">Auto</span>
					</Button>
				</div>
			</div>

			{suggestions.length > 0 && (
				<div
					className="flex flex-wrap gap-1.5"
					data-testid="keyword-suggestions"
				>
					{suggestions.map((q) => (
						<button
							key={q}
							type="button"
							onClick={() => {
								setQuery(q);
								search(q);
							}}
							className="flex items-center gap-1 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-300 transition-colors hover:bg-sky-500/20"
						>
							<Wand2 className="size-3" />
							{q}
						</button>
					))}
				</div>
			)}

			{notice && (
				<p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] leading-snug text-amber-300">
					{notice}
				</p>
			)}

			{error && (
				<p className="text-xs text-red-400" role="alert">
					{error}
				</p>
			)}

			{results.length > 0 && (
				<div
					className="grid max-h-72 grid-cols-2 gap-2 overflow-y-auto pr-1"
					data-testid="stock-results"
				>
					{results.map((video) => (
						<StockThumb
							key={`${video.provider}-${video.id}`}
							video={video}
							picked={stockClips.some((c) => c.url === video.video_url)}
							onToggle={() => togglePick(video)}
						/>
					))}
				</div>
			)}

			{/* Ordered multi-clip selection + montage mode vs coverage */}
			{stockClips.length > 0 && (
				<div
					className="space-y-1.5 rounded-lg border border-border/60 bg-muted/20 p-2.5"
					data-testid="stock-picks"
				>
					<div className="flex items-center justify-between gap-2 text-[11px] font-medium">
						<span>
							Background playlist ({stockClips.length} clip
							{stockClips.length === 1 ? '' : 's'})
						</span>
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
								'flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 transition-colors',
								stockMontage
									? 'border-sky-500/50 bg-sky-500/15 text-sky-300'
									: 'border-border/60 text-muted-foreground hover:text-foreground'
							)}
						>
							<Zap className="size-3" />
							{stockMontage ? 'Fast cuts' : 'Full clips'}
						</button>
					</div>
					<ol className="space-y-1">
						{stockClips.map((clip, i) => (
							<li
								key={clip.url}
								className="flex items-center gap-1.5 rounded-md bg-background/60 px-2 py-1 text-[11px]"
							>
								<span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-[9px] font-bold text-sky-300">
									{i + 1}
								</span>
								<span
									className="min-w-0 flex-1 truncate"
									title={
										clip.keyword
											? `${clip.label} — keyword: ${clip.keyword}`
											: clip.label
									}
								>
									{clip.label}
								</span>
								{clip.keyword && (
									<span
										className="max-w-24 shrink-0 truncate rounded-full bg-sky-500/10 px-1.5 text-[9px] text-sky-300"
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
										className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-sky-300"
									>
										{swappingAt === i ? (
											<Loader2 className="size-3 animate-spin" />
										) : (
											<Dices className="size-3" />
										)}
									</button>
								)}
								<span className="shrink-0 text-muted-foreground">
									{formatDuration(clip.duration_s)}
								</span>
								<button
									type="button"
									onClick={() => toggleStockClip(clip)}
									aria-label={`Remove ${clip.label}`}
									className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-red-400"
								>
									<X className="size-3" />
								</button>
							</li>
						))}
					</ol>
					{stockMontage ? (
						<p className="text-[10px] leading-snug text-muted-foreground">
							Fast-switching montage — each clip plays ~1.5–3s before the cut,
							cycled to cover your whole voiceover.
						</p>
					) : (
						<>
							<div className="h-1.5 overflow-hidden rounded-full bg-muted">
								<div
									className={cn(
										'h-full rounded-full transition-all',
										coverage >= 1
											? 'bg-emerald-500'
											: 'bg-gradient-to-r from-amber-500 to-orange-500'
									)}
									style={{ width: `${Math.min(100, coverage * 100)}%` }}
								/>
							</div>
							<p className="text-[10px] leading-snug text-muted-foreground">
								{coverage >= 1
									? 'Full coverage — the picks cover your whole voiceover.'
									: 'Short on coverage — clips will repeat to fill the voiceover. Pick more for variety.'}
							</p>
						</>
					)}
				</div>
			)}
		</>
	);
}

// --- Stock thumbnail card with hover video preview ---------------------------

function StockThumb({
	video,
	picked,
	onToggle
}: {
	video: StockVideoResult;
	picked: boolean;
	onToggle: () => void;
}) {
	const videoRef = useRef<HTMLVideoElement | null>(null);

	// Hover plays a muted looping preview straight from the CDN; leaving
	// pauses + rewinds. Thumbnails without a poster image load a video
	// frame via the #t=0.1 media fragment.
	const startPreview = () => {
		videoRef.current?.play().catch(() => {
			/* autoplay denied — the still thumbnail stays */
		});
	};
	const stopPreview = () => {
		const el = videoRef.current;
		if (el) {
			el.pause();
			el.currentTime = 0;
		}
	};

	return (
		<button
			type="button"
			onClick={onToggle}
			onMouseEnter={startPreview}
			onMouseLeave={stopPreview}
			aria-pressed={picked}
			data-testid="stock-thumb"
			className={cn(
				'group relative overflow-hidden rounded-lg border text-left transition-all',
				picked
					? 'border-sky-500/70 ring-2 ring-sky-500/40'
					: 'border-border/60 hover:border-sky-500/40'
			)}
		>
			<div className="relative aspect-[9/16] w-full bg-black/80">
				{video.thumbnail_url ? (
					// biome-ignore lint/performance/noImgElement: remote stock CDN thumbnails (Pexels/Pixabay), dynamic per search
					<img
						src={video.thumbnail_url}
						alt={video.title}
						loading="lazy"
						className="absolute inset-0 size-full object-cover"
					/>
				) : null}
				<video
					ref={videoRef}
					src={`${video.video_url}#t=0.1`}
					muted
					loop
					playsInline
					preload="metadata"
					className={cn(
						'absolute inset-0 size-full object-cover transition-opacity',
						video.thumbnail_url
							? 'opacity-0 group-hover:opacity-100'
							: 'opacity-100'
					)}
				/>
				{/* Provider + duration badges */}
				<span className="absolute top-1 left-1 rounded bg-black/70 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-white/90">
					{video.provider}
					{video.is_demo ? ' · demo' : ''}
				</span>
				<span className="absolute right-1 bottom-1 rounded bg-black/70 px-1.5 py-0.5 text-[9px] font-medium text-white/90">
					{formatDuration(video.duration_s)}
				</span>
				{/* Play affordance on hover */}
				<span className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
					<span className="flex size-8 items-center justify-center rounded-full bg-black/60 backdrop-blur">
						<Play className="size-4 translate-x-px text-white" />
					</span>
				</span>
				{/* Picked check */}
				{picked && (
					<span className="absolute top-1 right-1 flex size-5 items-center justify-center rounded-full bg-sky-500 text-white shadow">
						<Check className="size-3" />
					</span>
				)}
			</div>
			<p className="truncate px-1.5 py-1 text-[10px] leading-tight text-muted-foreground">
				{video.title}
			</p>
		</button>
	);
}
