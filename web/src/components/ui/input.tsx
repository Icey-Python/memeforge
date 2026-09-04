'use client';

import * as React from 'react';

import { cn } from '@/lib/utils';

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(
	({ className, type, ...props }, ref) => {
		return (
			<input
				type={type}
				className={cn(
					'flex h-9 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1 text-sm transition-colors placeholder:text-zinc-500 hover:border-white/20 focus-visible:border-orange-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/25 disabled:cursor-not-allowed disabled:opacity-50',
					className
				)}
				ref={ref}
				{...props}
			/>
		);
	}
);
Input.displayName = 'Input';

export { Input };
