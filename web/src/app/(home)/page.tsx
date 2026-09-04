'use client';

import { ArrowRight, AudioLines, Bot, Film, Gamepad2 } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

const STEPS = [
	{
		icon: Bot,
		title: 'Connect a model',
		body: 'OpenAI-compatible clouds or local Ollama. Bring your own brain.'
	},
	{
		icon: AudioLines,
		title: 'Pick a voice',
		body: 'Classic TikTok meme voices, free neural voices, or ElevenLabs.'
	},
	{
		icon: Gamepad2,
		title: 'Choose a background',
		body: 'Preset gameplay loops or auto-selected stock clips.'
	},
	{
		icon: Film,
		title: 'Forge the short',
		body: 'Vertical 1080×1920 with an optional hook card and captions.'
	}
];

export default function Home() {
	return (
		<main className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden px-6 py-16">
			<div className="relative z-10 flex max-w-4xl flex-col items-center text-center">
				<span className="mb-6 rounded-full border border-orange-500/25 bg-orange-500/10 px-4 py-1.5 text-[13px] text-orange-300">
					AI vertical video generation
				</span>

				<h1 className="text-balance text-5xl font-bold leading-[1.05] tracking-tight md:text-6xl">
					Turn any topic into a{' '}
					<span className="text-orange-400">scroll-stopping short</span>
				</h1>

				<p className="mt-6 max-w-xl text-balance text-lg leading-relaxed text-zinc-400">
					Wire a model, a voice, and background clips into one pipeline. Renders
					vertical 1080×1920 shorts with captions.
				</p>

				<div className="mt-10 flex flex-wrap items-center justify-center gap-4">
					<Button asChild size="lg" className="h-11 gap-2 px-7 text-base">
						<Link href="/studio">
							Open the Studio <ArrowRight className="size-4" />
						</Link>
					</Button>
				</div>

				<div className="mt-20 grid w-full gap-y-8 sm:grid-cols-2 lg:grid-cols-4 lg:divide-x lg:divide-white/[0.06]">
					{STEPS.map((step) => (
						<div
							key={step.title}
							className="px-0 text-left lg:px-8 lg:first:pl-0"
						>
							<step.icon className="size-5 text-orange-400" />
							<h3 className="mt-3 text-sm font-medium">{step.title}</h3>
							<p className="mt-1.5 text-sm leading-snug text-zinc-500">
								{step.body}
							</p>
						</div>
					))}
				</div>

				<p className="mt-16 text-xs text-zinc-600">
					Runs entirely on your machine · Next.js + FastAPI + ffmpeg
				</p>
			</div>
		</main>
	);
}
