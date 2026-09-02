'use client';

// Desc: Shared chrome for studio canvas nodes: card, header, handles.

import { Handle, Position } from '@xyflow/react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

export type HandleLayout = 'both' | 'source' | 'target' | 'none';

interface NodeShellProps {
	icon: LucideIcon;
	title: string;
	/** tailwind classes for the header accent strip */
	accent: string;
	badge?: React.ReactNode;
	children: React.ReactNode;
	footer?: React.ReactNode;
	handles?: HandleLayout;
	/** extra target handle id (e.g. preview node's gameplay input) */
	extraTargetId?: string;
	extraTargetPosition?: Position;
	className?: string;
}

const handleClass =
	'!h-3 !w-3 !border-2 !border-background !bg-muted-foreground/80';

export function NodeShell({
	icon: Icon,
	title,
	accent,
	badge,
	children,
	footer,
	handles = 'both',
	extraTargetId,
	extraTargetPosition = Position.Bottom,
	className
}: NodeShellProps) {
	return (
		<div
			className={cn(
				'w-[340px] rounded-xl border border-border/70 bg-card/95 shadow-2xl shadow-black/40 backdrop-blur',
				className
			)}
		>
			<div
				className={cn(
					'flex items-center justify-between gap-2 rounded-t-xl border-b border-border/60 px-4 py-2.5',
					accent
				)}
			>
				<div className="flex items-center gap-2">
					<Icon className="size-4" />
					<span className="text-sm font-semibold tracking-tight">{title}</span>
				</div>
				{badge}
			</div>
			<div className="space-y-3 p-4 text-sm">{children}</div>
			{footer}

			{(handles === 'target' || handles === 'both') && (
				<Handle
					type="target"
					position={Position.Left}
					className={handleClass}
				/>
			)}
			{(handles === 'source' || handles === 'both') && (
				<Handle
					type="source"
					position={Position.Right}
					className={handleClass}
				/>
			)}
			{extraTargetId && (
				<Handle
					type="target"
					id={extraTargetId}
					position={extraTargetPosition}
					className={handleClass}
				/>
			)}
		</div>
	);
}

/** Small status pill used in node headers. */
export function NodeBadge({
	children,
	variant = 'default'
}: {
	children: React.ReactNode;
	variant?: 'default' | 'success' | 'warn' | 'danger';
}) {
	const styles = {
		default: 'bg-muted text-muted-foreground',
		success: 'bg-emerald-500/15 text-emerald-400',
		warn: 'bg-amber-500/15 text-amber-400',
		danger: 'bg-red-500/15 text-red-400'
	} as const;
	return (
		<span
			className={cn(
				'rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
				styles[variant]
			)}
		>
			{children}
		</span>
	);
}

/** Styled native select (template has no shadcn Select installed). */
export function StudioSelect({
	id,
	value,
	onChange,
	options,
	placeholder
}: {
	id?: string;
	value: string;
	onChange: (value: string) => void;
	options: { value: string; label: string; disabled?: boolean }[];
	placeholder?: string;
}) {
	return (
		<select
			id={id}
			value={value}
			onChange={(e) => onChange(e.target.value)}
			className="h-9 w-full cursor-pointer appearance-none rounded-md border border-input bg-background px-3 pr-8 text-sm shadow-sm outline-none transition-colors focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
		>
			{placeholder && <option value="">{placeholder}</option>}
			{options.map((opt) => (
				<option key={opt.value} value={opt.value} disabled={opt.disabled}>
					{opt.label}
				</option>
			))}
		</select>
	);
}
