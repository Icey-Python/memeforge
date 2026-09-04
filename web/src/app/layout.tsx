import './globals.css';
import { Check, Info, Loader2, TriangleAlert, X } from 'lucide-react';
import type { Metadata, Viewport } from 'next';
import { DM_Sans } from 'next/font/google';
import { Toaster } from 'sonner';
import { QueryProvider } from '@/hooks/query/query-provider';

const dmSans = DM_Sans({
	subsets: ['latin'],
	display: 'swap',
	variable: '--font-dm-sans',
	weight: ['100', '200', '300', '400', '500', '600', '700', '800', '900']
});

export const metadata: Metadata = {
	title: {
		default: 'Memeforge, short-form video studio',
		template: '%s | Memeforge'
	},
	description:
		'AI vertical video studio: scroll-stopping scripts, kinetic captions synced word by word, neural voiceovers, and fast-cutting stock montages rendered in 1080x1920.',
	keywords: [
		'video generator',
		'short-form video',
		'shorts',
		'tiktok',
		'reels',
		'AI',
		'gaming'
	]
};

export const viewport: Viewport = {
	width: 'device-width',
	initialScale: 1,
	maximumScale: 1,
	themeColor: '#09090b'
};

export default function RootLayout({
	children
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html lang="en" className="dark">
			<body className={`${dmSans.className} antialiased`}>
				<QueryProvider>{children}</QueryProvider>
				{/* Sleek dark toasts: zinc-900 surface, clean white text and
				 * neutral icons — one minimalist look for every toast type. */}
				<Toaster
					position="top-center"
					theme="dark"
					icons={{
						success: <Check className="size-5 text-zinc-100" />,
						error: <X className="size-5 text-zinc-100" />,
						info: <Info className="size-5 text-zinc-100" />,
						warning: <TriangleAlert className="size-5 text-zinc-100" />,
						loading: <Loader2 className="size-5 animate-spin text-zinc-100" />
					}}
					toastOptions={{
						duration: 2000,
						style: {
							background: '#18181b',
							border: '1px solid rgba(255, 255, 255, 0.08)',
							color: '#fafafa',
							borderRadius: '9999px'
						}
					}}
				/>
			</body>
		</html>
	);
}
