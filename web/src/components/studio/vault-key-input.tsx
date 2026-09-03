'use client';

// Shared API-key input backed by the encrypted browser vault.
//
// Secrets never touch localStorage in plaintext: typing only edits a
// local draft (no API calls on keystrokes); "Save Key" encrypts the
// value into the vault — creating or unlocking it with a master
// passphrase when needed — and hydrates the pipeline's in-memory
// credentials via onSaved. Callers pass the value on to the backend
// with each request, so no server .env is ever required.

import { Check, Loader2, Lock, ShieldCheck, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { useVaultStore } from '@/store/vault';

interface VaultKeyInputProps {
	/** Vault entry id, e.g. 'llm.openai.apiKey' or 'stock.pexels.apiKey'. */
	vaultKey: string;
	/** HTML id for the key input. */
	id: string;
	label: string;
	placeholder?: string;
	/** Receives the freshly saved secret (hydrate store fields). */
	onSaved?: (secret: string) => void;
	/** Receives an empty string when the saved key is removed. */
	onDeleted?: () => void;
	className?: string;
}

export function VaultKeyInput({
	vaultKey,
	id,
	label,
	placeholder,
	onSaved,
	onDeleted,
	className
}: VaultKeyInputProps) {
	const status = useVaultStore((s) => s.status);
	const busy = useVaultStore((s) => s.busy);
	const vaultError = useVaultStore((s) => s.error);
	const saved = useVaultStore((s) => Boolean(s.entries[vaultKey]));
	const syncStatus = useVaultStore((s) => s.syncStatus);
	const createVault = useVaultStore((s) => s.createVault);
	const unlock = useVaultStore((s) => s.unlock);
	const saveEntry = useVaultStore((s) => s.saveEntry);
	const deleteEntry = useVaultStore((s) => s.deleteEntry);

	const [draft, setDraft] = useState('');
	// 'passphrase' unlocks an existing vault; 'create' sets a new one up.
	const [gate, setGate] = useState<'hidden' | 'passphrase' | 'create'>(
		'hidden'
	);
	const [passphrase, setPassphrase] = useState('');
	const [confirm, setConfirm] = useState('');
	const [localError, setLocalError] = useState<string | null>(null);
	const [justSaved, setJustSaved] = useState(false);

	// Reconcile the vault status with localStorage once on mount.
	useEffect(() => {
		syncStatus();
	}, [syncStatus]);

	const error = localError ?? vaultError;

	const finishSave = (secret: string) => {
		setDraft('');
		setPassphrase('');
		setConfirm('');
		setGate('hidden');
		setJustSaved(true);
		onSaved?.(secret);
		setTimeout(() => setJustSaved(false), 2500);
	};

	const openGate = () => {
		setLocalError(null);
		setGate(status === 'empty' ? 'create' : 'passphrase');
	};

	/** Run the gate action: unlock (and save the draft, if any). */
	const runGate = async () => {
		if (gate === 'create') {
			if (passphrase.length < 8) {
				setLocalError('Passphrase must be at least 8 characters.');
				return;
			}
			if (passphrase !== confirm) {
				setLocalError('Passphrases do not match.');
				return;
			}
			if (!(await createVault(passphrase))) return;
		} else if (!(await unlock(passphrase))) {
			return;
		}
		// Unlocked — persist the draft if the user typed one.
		const secret = draft.trim();
		if (secret && (await saveEntry(vaultKey, secret))) finishSave(secret);
		else setGate('hidden');
	};

	const save = async () => {
		const secret = draft.trim();
		if (!secret) {
			setLocalError('Type a key first.');
			return;
		}
		setLocalError(null);

		// Unlocked vault: encrypt + persist right away.
		if (status === 'unlocked') {
			if (await saveEntry(vaultKey, secret)) finishSave(secret);
			return;
		}

		// Locked/empty: the first Save opens the passphrase gate.
		if (gate === 'hidden') {
			openGate();
			return;
		}
		await runGate();
	};

	const remove = async () => {
		if (await deleteEntry(vaultKey)) {
			setDraft('');
			onDeleted?.();
		}
	};

	const gateVisible = gate !== 'hidden';
	// Offer a keyless unlock when a locked vault holds saved keys.
	const showUnlockLink = status === 'locked' && !gateVisible;

	return (
		<div className={cn('space-y-1.5', className)} data-testid="vault-key-input">
			<Label htmlFor={id} className="flex items-center gap-1.5">
				{label}
				{saved ? (
					<span
						className="flex items-center gap-0.5 rounded-full bg-emerald-500/15 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-emerald-400"
						data-testid="vault-key-saved"
					>
						<ShieldCheck className="size-2.5" />
						{justSaved ? 'saved!' : 'saved · encrypted'}
					</span>
				) : null}
			</Label>
			<div className="flex gap-1.5">
				<Input
					id={id}
					type="password"
					autoComplete="off"
					value={draft}
					placeholder={saved ? 'Saved in vault — type to replace' : placeholder}
					onChange={(e) => {
						setDraft(e.target.value);
						setLocalError(null);
					}}
					onKeyDown={(e) => {
						if (e.key === 'Enter') void save();
					}}
					className="h-8 text-xs"
				/>
				<Button
					size="sm"
					variant="outline"
					className="h-8 shrink-0 gap-1 px-2.5 text-xs"
					onClick={() => void save()}
					disabled={busy}
					data-testid="vault-key-save"
				>
					{busy ? (
						<Loader2 className="size-3.5 animate-spin" />
					) : justSaved ? (
						<Check className="size-3.5 text-emerald-400" />
					) : (
						<Lock className="size-3.5" />
					)}
					Save Key
				</Button>
				{saved && (
					<Button
						size="sm"
						variant="ghost"
						className="h-8 shrink-0 px-2"
						onClick={() => void remove()}
						disabled={busy}
						aria-label={`Remove saved ${label}`}
						title="Remove the saved key from the vault"
					>
						<Trash2 className="size-3.5" />
					</Button>
				)}
			</div>

			{showUnlockLink && (
				<button
					type="button"
					onClick={openGate}
					className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
					data-testid="vault-unlock-link"
				>
					<ShieldCheck className="size-3 text-emerald-400" />
					Saved keys are locked — unlock the vault
				</button>
			)}

			{gateVisible && (
				<div
					className="space-y-1.5 rounded-lg border border-border/60 bg-muted/30 p-2"
					data-testid="vault-passphrase-gate"
				>
					<p className="flex items-center gap-1.5 text-[11px] leading-snug text-muted-foreground">
						<ShieldCheck className="size-3 shrink-0 text-emerald-400" />
						{gate === 'create'
							? 'Keys are encrypted in your browser (AES-GCM-256). Pick a master passphrase — you will enter it once per session.'
							: 'Enter your vault master passphrase to use saved keys.'}
					</p>
					<div className="flex gap-1.5">
						<Input
							type="password"
							autoComplete="new-password"
							value={passphrase}
							placeholder="Master passphrase"
							onChange={(e) => {
								setPassphrase(e.target.value);
								setLocalError(null);
							}}
							onKeyDown={(e) => {
								if (e.key === 'Enter') void runGate();
							}}
							className="h-8 text-xs"
							data-testid="vault-passphrase"
						/>
						<Button
							size="sm"
							variant="outline"
							className="h-8 shrink-0 px-2.5 text-xs"
							onClick={() => void runGate()}
							disabled={busy}
						>
							{busy ? (
								<Loader2 className="size-3.5 animate-spin" />
							) : (
								<Lock className="size-3.5" />
							)}
							{gate === 'create' ? 'Create vault' : 'Unlock'}
						</Button>
					</div>
					{gate === 'create' && (
						<Input
							type="password"
							autoComplete="new-password"
							value={confirm}
							placeholder="Confirm passphrase"
							onChange={(e) => {
								setConfirm(e.target.value);
								setLocalError(null);
							}}
							onKeyDown={(e) => {
								if (e.key === 'Enter') void runGate();
							}}
							className="h-8 text-xs"
							data-testid="vault-passphrase-confirm"
						/>
					)}
				</div>
			)}

			{error && (
				<p className="text-[11px] leading-snug text-red-400" role="alert">
					{error}
				</p>
			)}
		</div>
	);
}
