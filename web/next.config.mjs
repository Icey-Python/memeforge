/** @type {import('next').NextConfig} */
const nextConfig = {
	// Emit a self-contained server bundle (`.next/standalone`) for the
	// Docker production image (web/Dockerfile). Harmless for local
	// `next dev` / `next build` / `next start`.
	output: 'standalone',
};

export default nextConfig;
