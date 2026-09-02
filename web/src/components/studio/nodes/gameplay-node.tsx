'use client';

// Gameplay Node: pick the background loop for the bottom frame.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { Gamepad2 } from 'lucide-react';
import { GAMEPLAY_FALLBACK } from '@/lib/catalog';
import { MemeforgeAPI } from '@/lib/memeforge';
import { cn } from '@/lib/utils';
import { usePipelineStore } from '@/store/pipeline';
import { NodeBadge, NodeShell } from '../node-shell';

export function GameplayNode(_props: NodeProps) {
	const gameplayId = usePipelineStore((s) => s.gameplayId);
	const setGameplay = usePipelineStore((s) => s.setGameplay);

	const { data: clips, isLoading } = useQuery({
		queryKey: ['gameplays'],
		queryFn: MemeforgeAPI.listGameplays,
		retry: false,
		staleTime: 60_000
	});

	const catalog = clips?.length ? clips : GAMEPLAY_FALLBACK;
	const selected = catalog.find((c) => c.id === gameplayId);

	return (
		<NodeShell
			icon={Gamepad2}
			title="Gameplay / Background"
			accent="bg-sky-500/15 text-sky-300"
			handles="source"
			badge={
				<NodeBadge variant={selected?.available ? 'success' : 'warn'}>
					{selected
						? selected.available
							? 'clip ready'
							: 'no asset'
						: 'pick one'}
				</NodeBadge>
			}
		>
			{isLoading ? (
				<div className="space-y-2">
					<div className="h-14 animate-pulse rounded-lg bg-muted/60" />
					<div className="h-14 animate-pulse rounded-lg bg-muted/60" />
				</div>
			) : (
				<div className="grid max-h-64 gap-2 overflow-y-auto pr-1">
					{catalog.map((clip) => {
						const active = clip.id === gameplayId;
						return (
							<button
								key={clip.id}
								type="button"
								onClick={() => setGameplay(clip.id)}
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
		</NodeShell>
	);
}
