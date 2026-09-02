'use client';

// Studio top bar: brand, backend health indicator, nav.

import { useQuery } from '@tanstack/react-query';
import { Flame, Home, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { MemeforgeAPI } from '@/lib/memeforge';
import { cn } from '@/lib/utils';

export function StudioHeader() {
	const { data: health, isLoading } = useQuery({
		queryKey: ['health'],
		queryFn: MemeforgeAPI.health,
		retry: false,
		refetchInterval: 30_000
	});

	const online = health?.status === 'ok';

	return (
		<header className="z-10 flex h-14 shrink-0 items-center justify-between border-b border-border/60 bg-card/70 px-4 backdrop-blur">
			<div className="flex items-center gap-3">
				<Link
					href="/"
					className="flex items-center gap-2 transition-opacity hover:opacity-80"
				>
					<span className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-fuchsia-500 to-violet-600">
						<Flame className="size-4 text-white" />
					</span>
					<span className="text-lg font-bold tracking-tight">
						meme
						<span className="bg-gradient-to-r from-fuchsia-400 to-violet-400 bg-clip-text text-transparent">
							forge
						</span>
					</span>
				</Link>
				<span className="hidden rounded-full border border-border/60 px-2.5 py-0.5 text-xs text-muted-foreground sm:block">
					Reddit-style meme video studio
				</span>
			</div>

			<div className="flex items-center gap-3">
				{isLoading ? (
					<Loader2 className="size-3.5 animate-spin text-muted-foreground" />
				) : (
					<span
						className={cn(
							'flex items-center gap-1.5 text-xs',
							online ? 'text-emerald-400' : 'text-amber-400'
						)}
						title={
							online
								? 'FastAPI backend online'
								: 'Backend offline — start it with: cd server && uvicorn app.main:app --reload'
						}
					>
						<span
							className={cn(
								'size-2 rounded-full',
								online ? 'bg-emerald-400' : 'bg-amber-400'
							)}
						/>
						{online ? 'API online' : 'API offline'}
					</span>
				)}
				<Button asChild variant="ghost" size="sm" className="gap-1.5">
					<Link href="/">
						<Home className="size-3.5" /> Home
					</Link>
				</Button>
			</div>
		</header>
	);
}
