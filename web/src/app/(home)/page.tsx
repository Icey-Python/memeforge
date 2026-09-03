'use client';

import { ArrowRight, AudioLines, Bot, Film, Gamepad2 } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

const STEPS = [
	{
		icon: Bot,
		title: 'Connect a model',
		body: 'OpenAI-compatible clouds or local Ollama — bring your own brain.',
		color: 'text-violet-300'
	},
	{
		icon: AudioLines,
		title: 'Pick a voice',
		body: 'Classic TikTok meme voices, free Azure neural voices, or ElevenLabs.',
		color: 'text-emerald-300'
	},
	{
		icon: Gamepad2,
		title: 'Choose gameplay',
		body: 'Minecraft parkour, Subway Surfers, GTA stunts — the classics.',
		color: 'text-sky-300'
	},
	{
		icon: Film,
		title: 'Forge the short',
		body: 'Full-screen 1080×1920 background, optional hook card, center captions.',
		color: 'text-rose-300'
	}
];

export default function Home() {
	return (
		<main className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden px-6 py-16">
			{/* glow backdrop */}
			<div
				aria-hidden
				className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_-10%,rgba(217,70,239,0.18),transparent),radial-gradient(40%_35%_at_80%_100%,rgba(139,92,246,0.12),transparent)]"
			/>

			<div className="relative z-10 flex max-w-5xl flex-col items-center text-center">
				<span className="mb-6 rounded-full border border-fuchsia-500/30 bg-fuchsia-500/10 px-4 py-1.5 text-sm text-fuchsia-300">
					AI vertical video generation, on autopilot
				</span>

				<h1 className="text-balance text-5xl font-black leading-[1.05] tracking-tight md:text-7xl">
					Turn any topic into a{' '}
					<span className="bg-gradient-to-r from-fuchsia-400 via-violet-400 to-sky-400 bg-clip-text text-transparent">
						scroll-stopping short
					</span>
				</h1>

				<p className="mt-6 max-w-2xl text-balance text-lg leading-relaxed text-muted-foreground">
					Memeforge wires your model connector, voiceover engine, and background
					clips into one visual pipeline — then renders viral-style vertical
					1080×1920 shorts: full-screen video, an optional hook or quote card,
					and kinetic captions with punchline SFX.
				</p>

				<div className="mt-10 flex flex-wrap items-center justify-center gap-4">
					<Button
						asChild
						size="lg"
						className="h-12 gap-2 bg-gradient-to-r from-fuchsia-600 to-violet-600 px-8 text-base text-white hover:from-fuchsia-500 hover:to-violet-500"
					>
						<Link href="/studio">
							Open the Studio <ArrowRight className="size-4" />
						</Link>
					</Button>
					<Button
						asChild
						variant="outline"
						size="lg"
						className="h-12 border-border/60 px-8 text-base"
					>
						<Link href="/studio">View the pipeline</Link>
					</Button>
				</div>

				<div className="mt-16 grid w-full gap-4 sm:grid-cols-2 lg:grid-cols-4">
					{STEPS.map((step) => (
						<div
							key={step.title}
							className="rounded-xl border border-border/60 bg-card/60 p-5 text-left backdrop-blur transition-colors hover:border-fuchsia-500/30"
						>
							<step.icon className={`size-5 ${step.color}`} />
							<h3 className="mt-3 text-sm font-semibold">{step.title}</h3>
							<p className="mt-1.5 text-sm leading-snug text-muted-foreground">
								{step.body}
							</p>
						</div>
					))}
				</div>

				<p className="mt-14 text-xs text-muted-foreground/60">
					Next.js + React Flow frontend · FastAPI + ffmpeg backend · runs
					entirely on your machine
				</p>
			</div>
		</main>
	);
}
