'use client';

// Studio top bar: brand, stepwise mode toggle, step indicator, backend
// health, vault access.

import { useQuery } from '@tanstack/react-query';
import {
	Flame,
	Footprints,
	KeyRound,
	LayoutGrid,
	Loader2,
	LockOpen
} from 'lucide-react';
import Link from 'next/link';
import { ApiKeysSheet } from '@/components/studio/settings-drawer';
import { Button } from '@/components/ui/button';
import { MemeforgeAPI } from '@/lib/memeforge';
import { cn } from '@/lib/utils';
import { useCredentialsStore } from '@/store/credentials';
import { STUDIO_STEPS, studioStage, usePipelineStore } from '@/store/pipeline';

export function StudioHeader() {
	const { data: health, isLoading } = useQuery({
		queryKey: ['health'],
		queryFn: MemeforgeAPI.health,
		retry: false,
		refetchInterval: 30_000
	});

	const online = health?.status === 'ok';

	const stepwise = usePipelineStore((s) => s.stepwise);
	const setStepwise = usePipelineStore((s) => s.setStepwise);
	const stage = usePipelineStore((s) => studioStage(s));

	const vaultStatus = useCredentialsStore((s) => s.status);
	const openSettings = useCredentialsStore((s) => s.openSettings);

	const modeButton = (active: boolean) =>
		cn(
			'flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all active:scale-[0.98]',
			active
				? 'bg-orange-500 text-zinc-950'
				: 'text-zinc-400 hover:text-zinc-100'
		);

	return (
		<header className="z-10 flex h-14 shrink-0 items-center justify-between border-b border-white/[0.06] bg-zinc-950/80 px-4 backdrop-blur">
			<div className="flex items-center gap-3">
				<Link
					href="/"
					className="flex items-center gap-2.5 transition-opacity hover:opacity-80"
					aria-label="MemeForge home"
				>
					<span className="flex size-7 items-center justify-center rounded-lg bg-orange-500">
						<Flame className="size-4 text-zinc-950" />
					</span>
					<span className="text-[15px] font-semibold tracking-tight">
						memeforge
					</span>
				</Link>
			</div>

			<div className="flex items-center gap-3">
				{/* Wizard step indicator */}
				{stepwise && (
					<span
						className="hidden text-xs text-zinc-500 md:flex"
						data-testid="stepwise-indicator"
					>
						<span className="font-medium text-zinc-200">Step {stage}/5</span>
						<span className="mx-2 text-zinc-700">·</span>
						{STUDIO_STEPS[stage - 1].title}
					</span>
				)}

				{/* Canvas mode toggle */}
				<div
					className="flex items-center gap-0.5 rounded-full border border-white/10 bg-white/[0.03] p-0.5"
					data-testid="mode-toggle"
				>
					<button
						type="button"
						onClick={() => setStepwise(true)}
						aria-pressed={stepwise}
						className={modeButton(stepwise)}
					>
						<Footprints className="size-3.5" />
						<span className="hidden sm:inline">Step-by-step</span>
					</button>
					<button
						type="button"
						onClick={() => setStepwise(false)}
						aria-pressed={!stepwise}
						className={modeButton(!stepwise)}
					>
						<LayoutGrid className="size-3.5" />
						<span className="hidden sm:inline">Show all</span>
					</button>
				</div>

				{/* Settings / API Keys vault */}
				<Button
					variant="outline"
					size="sm"
					className="gap-1.5"
					onClick={openSettings}
					data-testid="api-keys-button"
					title="Manage API keys in the encrypted local vault"
				>
					{vaultStatus === 'unlocked' ? (
						<LockOpen className="size-3.5 text-orange-400" />
					) : (
						<KeyRound className="size-3.5" />
					)}
					<span className="hidden sm:inline">Keys</span>
				</Button>

				{/* Backend reachability: the one semantic status dot. */}
				{isLoading ? (
					<Loader2 className="size-3.5 animate-spin text-zinc-600" />
				) : (
					<span
						className={cn(
							'flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium',
							online
								? 'bg-emerald-500/10 text-emerald-400'
								: 'bg-amber-500/10 text-amber-400'
						)}
						title={
							online
								? 'FastAPI backend online'
								: 'Backend offline, start it with: cd server && uvicorn app.main:app --reload'
						}
					>
						<span
							className={cn(
								'size-1.5 rounded-full',
								online ? 'bg-emerald-400' : 'bg-amber-400'
							)}
						/>
						{online ? 'API online' : 'API offline'}
					</span>
				)}
			</div>
			<ApiKeysSheet />
		</header>
	);
}
