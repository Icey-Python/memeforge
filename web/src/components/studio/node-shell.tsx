'use client';

// Desc: Shared chrome for studio canvas nodes: card, header, handles.
//
// Design system: one accent (orange) across selection states, active
// controls and focus rings. Node chrome itself stays neutral zinc so the
// canvas reads calm; `node-card` is the hook for the selected-node
// highlight in globals.css.

import { Handle, Position } from '@xyflow/react';
import { ChevronDown, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

export type HandleLayout = 'both' | 'source' | 'target' | 'none';

interface NodeShellProps {
	icon: LucideIcon;
	title: string;
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
	'!h-2.5 !w-2.5 !border-2 !border-zinc-950 !bg-zinc-600 !transition-colors hover:!bg-orange-500';

export function NodeShell({
	icon: Icon,
	title,
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
				'node-card w-[340px] rounded-xl border border-white/10 bg-zinc-900/95 shadow-xl shadow-black/30 backdrop-blur',
				className
			)}
		>
			<div className="flex items-center justify-between gap-2 px-4 pt-3.5">
				<div className="flex items-center gap-2">
					<Icon className="size-4 text-zinc-500" />
					<span className="text-[13px] font-medium text-zinc-200">{title}</span>
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
		default: 'bg-white/[0.06] text-zinc-400',
		success: 'bg-orange-500/10 text-orange-400',
		warn: 'bg-amber-500/10 text-amber-400',
		danger: 'bg-red-500/10 text-red-400'
	} as const;
	return (
		<span
			className={cn(
				'rounded-full px-2 py-0.5 text-[10px] font-medium',
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
	groups,
	placeholder
}: {
	id?: string;
	value: string;
	onChange: (value: string) => void;
	/** flat option list (used instead of `groups`) */
	options?: { value: string; label: string; disabled?: boolean }[];
	/** grouped options rendered as <optgroup> categories */
	groups?: {
		label: string;
		options: { value: string; label: string; disabled?: boolean }[];
	}[];
	placeholder?: string;
}) {
	return (
		<div className="relative">
			<select
				id={id}
				value={value}
				onChange={(e) => onChange(e.target.value)}
				className="h-9 w-full cursor-pointer appearance-none rounded-lg border border-white/10 bg-white/[0.03] px-3 pr-8 text-sm transition-colors hover:border-white/20 focus-visible:border-orange-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/25 disabled:cursor-not-allowed disabled:opacity-50"
			>
				{placeholder && <option value="">{placeholder}</option>}
				{options?.map((opt) => (
					<option key={opt.value} value={opt.value} disabled={opt.disabled}>
						{opt.label}
					</option>
				))}
				{groups?.map((group) => (
					<optgroup key={group.label} label={group.label}>
						{group.options.map((opt) => (
							<option key={opt.value} value={opt.value} disabled={opt.disabled}>
								{opt.label}
							</option>
						))}
					</optgroup>
				))}
			</select>
			<ChevronDown className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-zinc-500" />
		</div>
	);
}
