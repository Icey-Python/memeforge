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
		'AI vertical video generator: scripts via LLM connectors, free TikTok meme + neural voices, and vertical 1080x1920 full-screen renders.',
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
				<Toaster
					position="top-center"
					richColors
					icons={{
						success: <Check className="size-5 text-primary" />,
						error: <X className="size-5 text-primary" />,
						info: <Info className="size-5 text-primary" />,
						warning: <TriangleAlert className="text-primary size-5" />,
						loading: <Loader2 className="text-primary size-5 animate-spin" />
					}}
					toastOptions={{
						duration: 2000
					}}
				/>
			</body>
		</html>
	);
}
