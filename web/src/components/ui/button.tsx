'use client';

// Pill-shaped buttons on a single orange accent (see globals.css tokens).
// Shape system: interactive controls are full pills, cards 12px, inputs 8px.

import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const buttonVariants = cva(
	'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring/60 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
	{
		variants: {
			variant: {
				default: 'bg-primary text-primary-foreground hover:bg-orange-400',
				destructive:
					'bg-destructive text-white shadow-sm hover:bg-destructive/90',
				outline:
					'border border-white/10 bg-transparent hover:border-white/20 hover:bg-white/5',
				secondary: 'bg-white/[0.07] text-zinc-200 hover:bg-white/10',
				ghost: 'hover:bg-white/[0.07] hover:text-zinc-100',
				link: 'text-orange-400 underline-offset-4 hover:underline'
			},
			size: {
				default: 'h-9 px-4',
				sm: 'h-8 px-3.5 text-xs',
				lg: 'h-11 px-6',
				icon: 'size-9'
			}
		},
		defaultVariants: {
			variant: 'default',
			size: 'default'
		}
	}
);

export interface ButtonProps
	extends React.ButtonHTMLAttributes<HTMLButtonElement>,
		VariantProps<typeof buttonVariants> {
	asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
	({ className, variant, size, asChild = false, ...props }, ref) => {
		const Comp = asChild ? Slot : 'button';
		return (
			<Comp
				className={cn(buttonVariants({ variant, size, className }))}
				ref={ref}
				{...props}
			/>
		);
	}
);
Button.displayName = 'Button';

export { Button, buttonVariants };
