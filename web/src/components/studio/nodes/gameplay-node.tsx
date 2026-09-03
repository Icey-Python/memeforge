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
	Film,
	Gamepad2,
	KeyRound,
	Loader2,
	Play,
	Search,
	Sparkles,
	Wand2,
	X
} from 'lucide-react';
import { useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
	backendLLMProvider,
	GAMEPLAY_FALLBACK,
	llmBaseUrl
} from '@/lib/catalog';
import { MemeforgeAPI } from '@/lib/memeforge';
import { estimateSpokenSeconds } from '@/lib/script-split';
import { cn } from '@/lib/utils';
import { usePipelineStore } from '@/store/pipeline';
import type { GameplayClip, StockVideoResult } from '@/types/studio';
import { NodeBadge, NodeShell } from '../node-shell';
import { VaultKeyInput } from '../vault-key-input';

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
	const model = usePipelineStore((s) => s.model);
	const stockClips = usePipelineStore((s) => s.stockClips);
	const toggleStockClip = usePipelineStore((s) => s.toggleStockClip);
	const setStockKeys = usePipelineStore((s) => s.setStockKeys);
	const pexelsKey = usePipelineStore((s) => s.stockPexelsKey);
	const pixabayKey = usePipelineStore((s) => s.stockPixabayKey);

	const [query, setQuery] = useState('');
	const [results, setResults] = useState<StockVideoResult[]>([]);
	const [notice, setNotice] = useState<string | null>(null);
	const [searching, setSearching] = useState(false);
	const [suggesting, setSuggesting] = useState(false);
	const [suggestions, setSuggestions] = useState<string[]>([]);
	const [error, setError] = useState<string | null>(null);

	const search = async (q: string) => {
		const term = q.trim();
		if (term.length < 2) {
			setError('Type at least 2 characters to search.');
			return;
		}
		setSearching(true);
		setError(null);
		try {
			// Vault keys ride along as overrides; without any key the
			// backend serves curated demo clips.
			const resp = await MemeforgeAPI.searchStock(term, {
				pexels: pexelsKey || undefined,
				pixabay: pixabayKey || undefined
			});
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
			const resp = await MemeforgeAPI.extractKeywords({
				script,
				provider: backendLLMProvider(model.provider),
				model: model.model || undefined,
				base_url: llmBaseUrl(model) || undefined,
				api_key: model.apiKey || undefined
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
	const neededSeconds = estimateSpokenSeconds(
		scriptLines.join(' ').trim().split(/\s+/).filter(Boolean).length
	);
	const pickedSeconds = stockClips.reduce((sum, c) => sum + c.duration_s, 0);
	const coverage = neededSeconds > 0 ? pickedSeconds / neededSeconds : 0;

	return (
		<>
			{notice && (
				<p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] leading-snug text-amber-300">
					{notice}
				</p>
			)}

			<div className="space-y-2.5 rounded-lg border border-border/60 bg-muted/20 p-2.5">
				<p className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
					<KeyRound className="size-3" />
					Live results keys — saved encrypted in your browser, or leave blank
					for curated demo clips.
				</p>
				<div className="grid gap-2.5">
					<VaultKeyInput
						id="pexels-key"
						vaultKey="stock.pexels.apiKey"
						label="Pexels API key"
						placeholder="free key from pexels.com/api"
						onSaved={(secret) => setStockKeys({ pexels: secret })}
						onDeleted={() => setStockKeys({ pexels: '' })}
					/>
					<VaultKeyInput
						id="pixabay-key"
						vaultKey="stock.pixabay.apiKey"
						label="Pixabay API key"
						placeholder="free key from pixabay.com/api"
						onSaved={(secret) => setStockKeys({ pixabay: secret })}
						onDeleted={() => setStockKeys({ pixabay: '' })}
					/>
				</div>
			</div>

			<div className="space-y-1.5">
				<Label htmlFor="stock-query">Search vertical stock clips</Label>
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

			{/* Ordered multi-clip selection + coverage vs script duration */}
			{stockClips.length > 0 && (
				<div
					className="space-y-1.5 rounded-lg border border-border/60 bg-muted/20 p-2.5"
					data-testid="stock-picks"
				>
					<div className="flex items-center justify-between text-[11px] font-medium">
						<span>
							Background playlist ({stockClips.length} clip
							{stockClips.length === 1 ? '' : 's'})
						</span>
						<span className="text-muted-foreground">
							{formatDuration(pickedSeconds)} / {formatDuration(neededSeconds)}{' '}
							script
						</span>
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
								<span className="min-w-0 flex-1 truncate">{clip.label}</span>
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
