import { Flame } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function NotFound() {
	return (
		<section className="flex min-h-dvh flex-col items-center justify-center gap-6 px-6 text-center">
			<span className="flex size-14 items-center justify-center rounded-2xl bg-orange-500">
				<Flame className="size-7 text-zinc-950" />
			</span>
			<div>
				<h1 className="text-4xl font-bold tracking-tight">404</h1>
				<p className="mt-2 text-zinc-500">
					This page is so rare it does not exist yet.
				</p>
			</div>
			<Button asChild className="gap-2">
				<Link href="/">Back to the forge</Link>
			</Button>
		</section>
	);
}
