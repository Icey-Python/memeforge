'use client';

import * as React from 'react';

import { cn } from '@/lib/utils';

const Textarea = React.forwardRef<
	HTMLTextAreaElement,
	React.ComponentProps<'textarea'>
>(({ className, ...props }, ref) => {
	return (
		<textarea
			className={cn(
				'flex min-h-[60px] w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm transition-colors placeholder:text-zinc-500 hover:border-white/20 focus-visible:border-orange-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/25 disabled:cursor-not-allowed disabled:opacity-50',
				className
			)}
			ref={ref}
			{...props}
		/>
	);
});
Textarea.displayName = 'Textarea';

export { Textarea };
