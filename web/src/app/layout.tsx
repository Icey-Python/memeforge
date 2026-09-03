import './globals.css';
import {
	IconAlertTriangle,
	IconCheck,
	IconInfoCircle,
	IconLoader2,
	IconX
} from '@tabler/icons-react';
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
		default: 'Memeforge — short-form video studio',
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
						success: <IconCheck className="text-primary size-5" />,
						error: <IconX className="text-primary size-5" />,
						info: <IconInfoCircle className="text-primary size-5" />,
						warning: <IconAlertTriangle className="text-primary size-5" />,
						loading: (
							<IconLoader2 className="text-primary size-5 animate-spin" />
						)
					}}
					toastOptions={{
						duration: 2000
					}}
				/>
			</body>
		</html>
	);
}
