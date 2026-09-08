'use client';

// Desc: Searchable voice combobox for the Voiceover node.
//
// One picker across every TTS provider's catalog: typing filters voices
// by name, language, tag, or gender; picking a voice from another
// provider switches the engine with it. Rows carry a per-voice preview
// button so the free meme engines keep their instant auditions.

import { Check, ChevronsUpDown, Loader2, Play, Search } from 'lucide-react';
import {
	type KeyboardEvent,
	useEffect,
	useMemo,
	useRef,
	useState
} from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { TTSProviderId, VoiceOption } from '@/types/studio';

/** A voice catalog entry tagged with the provider it belongs to. */
export interface VoiceCatalogEntry extends VoiceOption {
	provider: TTSProviderId;
}

/** Compact provider names for group headers and row chips. */
export const PROVIDER_SHORT_LABELS: Record<TTSProviderId, string> = {
	edge: 'Edge',
	meme_classic: 'Meme Classic',
	tiktok: 'TikTok',
	google: 'Google',
	fish_audio: 'Fish Audio',
	azure: 'Azure',
	elevenlabs: 'ElevenLabs'
};

function matchesQuery(voice: VoiceCatalogEntry, query: string): boolean {
	const haystack = [
		voice.label,
		voice.id,
		voice.language,
		voice.gender,
		...(voice.tags ?? []),
		PROVIDER_SHORT_LABELS[voice.provider]
	]
		.join(' ')
		.toLowerCase();
	return haystack.includes(query);
}

interface VoiceComboboxProps {
	/** Selected voice id (may be a custom id absent from the catalog). */
	value: string;
	/** Provider the selected voice belongs to. */
	provider: TTSProviderId;
	/** Unified catalog: every provider's voices, live data overlaid. */
	catalog: VoiceCatalogEntry[];
	/** Provider order for the grouped (unsearched) list. */
	providerOrder: TTSProviderId[];
	onSelect: (provider: TTSProviderId, voiceId: string) => void;
	onPreview: (provider: TTSProviderId, voiceId: string) => void;
	/** `provider:voiceId` key of the preview currently synthesizing. */
	previewingKey: string | null;
	disabled?: boolean;
	id?: string;
}

export function VoiceCombobox({
	value,
	provider,
	catalog,
	providerOrder,
	onSelect,
	onPreview,
	previewingKey,
	disabled,
	id
}: VoiceComboboxProps) {
	const [open, setOpen] = useState(false);
	const [query, setQuery] = useState('');
	const [highlight, setHighlight] = useState(0);
	const rootRef = useRef<HTMLDivElement>(null);
	const listRef = useRef<HTMLDivElement>(null);
	const inputRef = useRef<HTMLInputElement>(null);

	const selected = catalog.find(
		(v) => v.provider === provider && v.id === value
	);

	const filtered = useMemo(() => {
		const q = query.trim().toLowerCase();
		return q ? catalog.filter((v) => matchesQuery(v, q)) : catalog;
	}, [catalog, query]);

	// Grouped layout when browsing (no query); flat while searching. The
	// active provider's group leads so its voices stay nearest.
	const groups = useMemo(() => {
		if (query.trim()) return null;
		const byProvider = new Map<TTSProviderId, VoiceCatalogEntry[]>();
		for (const entry of catalog) {
			const list = byProvider.get(entry.provider) ?? [];
			list.push(entry);
			byProvider.set(entry.provider, list);
		}
		return [...providerOrder]
			.sort((a, b) => {
				if (a === provider) return -1;
				if (b === provider) return 1;
				return 0;
			})
			.map((p) => ({ provider: p, entries: byProvider.get(p) ?? [] }));
	}, [catalog, providerOrder, provider, query]);

	// Rows in the exact order they render (groups flatten to the same
	// sequence), so keyboard navigation stays in sync with the DOM.
	const rows = useMemo(
		() => (groups ? groups.flatMap((g) => g.entries) : filtered),
		[groups, filtered]
	);

	// Close on outside pointer presses; the panel lives inside the node
	// card, so this keeps it from lingering over the canvas.
	useEffect(() => {
		if (!open) return;
		const onPointerDown = (event: PointerEvent) => {
			if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
		};
		document.addEventListener('pointerdown', onPointerDown);
		return () => document.removeEventListener('pointerdown', onPointerDown);
	}, [open]);

	// Keep the highlighted row in view during keyboard navigation.
	useEffect(() => {
		if (!open) return;
		listRef.current
			?.querySelector(`[data-idx="${highlight}"]`)
			?.scrollIntoView({ block: 'nearest' });
	}, [highlight, open]);

	const openPanel = () => {
		setOpen(true);
		setQuery('');
		setHighlight(0);
		requestAnimationFrame(() => inputRef.current?.focus());
	};

	const pick = (entry: VoiceCatalogEntry) => {
		onSelect(entry.provider, entry.id);
		setOpen(false);
	};

	const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
		if (event.key === 'Escape') {
			setOpen(false);
			return;
		}
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			setHighlight((h) => Math.min(h + 1, rows.length - 1));
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			setHighlight((h) => Math.max(h - 1, 0));
		} else if (event.key === 'Enter') {
			event.preventDefault();
			const entry = rows[highlight];
			if (entry) pick(entry);
		}
	};

	let rowIdx = -1; // flat index across groups, matching `rows` order

	return (
		<div ref={rootRef} className="relative" data-testid="voice-combobox">
			<button
				type="button"
				id={id}
				disabled={disabled}
				aria-haspopup="listbox"
				aria-expanded={open}
				onClick={() => (open ? setOpen(false) : openPanel())}
				className="flex h-9 w-full items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 text-left text-sm transition-colors hover:border-white/20 focus-visible:border-orange-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/25 disabled:cursor-not-allowed disabled:opacity-50"
			>
				<span className="min-w-0 flex-1">
					<span className="block truncate text-xs font-medium">
						{selected ? selected.label : 'Custom voice id'}
					</span>
					<span className="block truncate text-[10px] text-zinc-500">
						{selected
							? `${PROVIDER_SHORT_LABELS[selected.provider]} · ${selected.language} · ${selected.gender}`
							: value || 'no voice set'}
					</span>
				</span>
				{previewingKey === `${provider}:${value}` ? (
					<Loader2 className="size-3.5 shrink-0 animate-spin text-zinc-400" />
				) : (
					<ChevronsUpDown className="size-3.5 shrink-0 text-zinc-500" />
				)}
			</button>

			{open && (
				<div className="absolute inset-x-0 top-[calc(100%+6px)] z-50 overflow-hidden rounded-lg border border-white/10 bg-zinc-900 shadow-xl shadow-black/50">
					<div className="flex items-center gap-2 border-b border-white/10 px-2.5 py-2">
						<Search className="size-3.5 shrink-0 text-zinc-500" />
						<input
							ref={inputRef}
							value={query}
							onChange={(e) => {
								setQuery(e.target.value);
								setHighlight(0);
							}}
							onKeyDown={onKeyDown}
							placeholder="Search voices, languages, tags..."
							aria-label="Search voices"
							className="h-6 w-full bg-transparent text-xs text-zinc-200 outline-none placeholder:text-zinc-600"
							data-testid="voice-combobox-input"
						/>
					</div>
					<div
						ref={listRef}
						role="listbox"
						aria-label="Voices"
						className="max-h-64 overflow-y-auto p-1"
					>
						{rows.length === 0 && (
							<p className="px-2 py-3 text-center text-xs text-zinc-500">
								{query.trim()
									? `No voices match "${query.trim()}"`
									: 'No voices available yet.'}
							</p>
						)}
						{groups
							? groups.map(
									(group) =>
										group.entries.length > 0 && (
											<div key={group.provider}>
												<div className="flex items-center justify-between px-2 pb-0.5 pt-1.5">
													<span className="text-[10px] font-semibold tracking-wide text-zinc-500 uppercase">
														{PROVIDER_SHORT_LABELS[group.provider]}
													</span>
													<span className="text-[10px] text-zinc-600">
														{group.entries.length}
													</span>
												</div>
												{group.entries.map((entry) => {
													rowIdx += 1;
													return (
														<ComboboxRow
															key={`${entry.provider}:${entry.id}`}
															entry={entry}
															idx={rowIdx}
															selected={
																entry.provider === provider &&
																entry.id === value
															}
															highlighted={rowIdx === highlight}
															previewing={
																previewingKey ===
																`${entry.provider}:${entry.id}`
															}
															onHover={setHighlight}
															onPick={pick}
															onPreview={onPreview}
															previewDisabled={previewingKey !== null}
														/>
													);
												})}
											</div>
										)
								)
							: rows.map((entry, idx) => (
									<ComboboxRow
										key={`${entry.provider}:${entry.id}`}
										entry={entry}
										idx={idx}
										selected={entry.provider === provider && entry.id === value}
										highlighted={idx === highlight}
										previewing={
											previewingKey === `${entry.provider}:${entry.id}`
										}
										onHover={setHighlight}
										onPick={pick}
										onPreview={onPreview}
										previewDisabled={previewingKey !== null}
									/>
								))}
					</div>
				</div>
			)}
		</div>
	);
}

function ComboboxRow({
	entry,
	idx,
	selected,
	highlighted,
	previewing,
	previewDisabled,
	onHover,
	onPick,
	onPreview
}: {
	entry: VoiceCatalogEntry;
	idx: number;
	selected: boolean;
	highlighted: boolean;
	previewing: boolean;
	/** Any preview in flight: rows disable while audio synthesizes. */
	previewDisabled: boolean;
	onHover: (idx: number) => void;
	onPick: (entry: VoiceCatalogEntry) => void;
	onPreview: (provider: TTSProviderId, voiceId: string) => void;
}) {
	return (
		<div
			data-idx={idx}
			role="option"
			aria-selected={selected}
			tabIndex={-1}
			onMouseEnter={() => onHover(idx)}
			className={cn(
				'flex items-center gap-1 rounded-lg px-1.5 py-1 transition-colors',
				highlighted ? 'bg-white/[0.06]' : '',
				selected ? 'bg-orange-500/10' : ''
			)}
		>
			<button
				type="button"
				onClick={() => onPick(entry)}
				className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
				data-testid={`voice-option-${entry.id}`}
			>
				{selected && <Check className="size-3.5 shrink-0 text-orange-400" />}
				<span className="min-w-0">
					<span className="block truncate text-xs font-medium">
						{entry.label}
					</span>
					<span className="block truncate text-[10px] text-zinc-500">
						{PROVIDER_SHORT_LABELS[entry.provider]} · {entry.language} ·{' '}
						{entry.gender}
						{entry.tags && entry.tags.length > 0
							? ` · ${entry.tags.join(', ')}`
							: ''}
					</span>
				</span>
			</button>
			<Button
				variant="ghost"
				size="icon"
				className="size-6 shrink-0 text-zinc-500 hover:text-zinc-200"
				onClick={(e) => {
					e.stopPropagation();
					onPreview(entry.provider, entry.id);
				}}
				disabled={previewDisabled}
				aria-label={`Preview ${entry.label}`}
			>
				{previewing ? (
					<Loader2 className="size-3 animate-spin" />
				) : (
					<Play className="size-3" />
				)}
			</Button>
		</div>
	);
}
