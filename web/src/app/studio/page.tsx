import type { Metadata } from 'next';

import { MemeCanvas } from '@/components/studio/meme-canvas';
import { StudioHeader } from '@/components/studio/studio-header';

export const metadata: Metadata = {
	title: 'Studio',
	description:
		'Wire model connectors, voiceover, and background clips into a vertical short.'
};

export default function StudioPage() {
	return (
		<div className="flex h-dvh w-full flex-col overflow-hidden">
			<StudioHeader />
			<main className="relative min-h-0 flex-1">
				<MemeCanvas />
			</main>
		</div>
	);
}
