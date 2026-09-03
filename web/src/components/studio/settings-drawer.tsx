'use client';

// Settings / API Keys drawer: the encrypted key vault UI.
//
// Three states:
//  - uninitialized → create a vault with a master passphrase
//  - locked        → unlock with the passphrase (fresh session default)
//  - unlocked      → manage LLM / TTS / stock keys with per-field status
//
// SECURITY: keys are AES-GCM-256 encrypted (PBKDF2, 310k iterations)
// before they touch localStorage; decrypted keys live in memory only
// while the vault is unlocked (see store/credentials.ts + lib/vault-crypto.ts).

import { useQuery } from '@tanstack/react-query';
import {
	Check,
	ChevronDown,
	Eye,
	EyeOff,
	KeyRound,
	Loader2,
	Lock,
	LockOpen,
	ShieldCheck,
	Trash2
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetHeader,
	SheetTitle
} from '@/components/ui/sheet';
import { MemeforgeAPI } from '@/lib/memeforge';
import { cn } from '@/lib/utils';
import { useCredentialsStore } from '@/store/credentials';
import type { ApiKeys } from '@/types/studio';

// --- Field metadata -----------------------------------------------------------

type KeyField = keyof ApiKeys;

interface FieldDef {
	field: KeyField;
	label: string;
	placeholder: string;
	/** /health capabilities flag reporting a server .env default. */
	serverFlag: string;
	/** Status label when neither vault nor server has a key. */
	emptyLabel?: string;
	/** Plain text (regions, base URLs are not secrets). */
	plaintext?: boolean;
}

const LLM_FIELDS: FieldDef[] = [
	{
		field: 'openaiApiKey',
		label: 'OpenAI API Key',
		placeholder: 'sk-…',
		serverFlag: 'llm_openai'
	},
	{
		field: 'anthropicApiKey',
		label: 'Anthropic API Key',
		placeholder: 'sk-ant-…',
		serverFlag: 'llm_anthropic'
	},
	{
		field: 'openrouterApiKey',
		label: 'OpenRouter API Key',
		placeholder: 'sk-or-…',
		serverFlag: 'llm_openrouter'
	},
	{
		field: 'groqApiKey',
		label: 'Groq API Key',
		placeholder: 'gsk_…',
		serverFlag: 'llm_groq'
	}
];

const BASE_URL_FIELD: FieldDef = {
	field: 'llmBaseUrl',
	label: 'Custom Base URL',
	placeholder: 'https://openrouter.ai/api/v1',
	serverFlag: '',
	plaintext: true,
	emptyLabel: 'Using default endpoint'
};

const TTS_FIELDS: FieldDef[] = [
	{
		field: 'elevenlabsApiKey',
		label: 'ElevenLabs API Key',
		placeholder: 'xi-api key…',
		serverFlag: 'tts_elevenlabs'
	},
	{
		field: 'azureSpeechKey',
		label: 'Azure Speech Key',
		placeholder: 'subscription key…',
		serverFlag: 'tts_azure'
	},
	{
		field: 'azureSpeechRegion',
		label: 'Azure Speech Region',
		placeholder: 'eastus',
		serverFlag: 'tts_azure_region',
		plaintext: true
	}
];

const STOCK_FIELDS: FieldDef[] = [
	{
		field: 'pexelsApiKey',
		label: 'Pexels API Key',
		placeholder: 'free key from pexels.com/api',
		serverFlag: 'stock_pexels',
		emptyLabel: 'Free / demo mode'
	},
	{
		field: 'pixabayApiKey',
		label: 'Pixabay API Key',
		placeholder: 'free key from pixabay.com/api',
		serverFlag: 'stock_pixabay',
		emptyLabel: 'Free / demo mode'
	}
];

// --- Status pill ----------------------------------------------------------------

function KeyStatusPill({
	value,
	serverDefault,
	emptyLabel
}: {
	value: string;
	serverDefault: boolean;
	emptyLabel?: string;
}) {
	if (value) {
		return (
			<span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
				Configured (local vault)
			</span>
		);
	}
	if (serverDefault) {
		return (
			<span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">
				Using Server Default
			</span>
		);
	}
	return (
		<span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
			{emptyLabel ?? 'Not configured'}
		</span>
	);
}

// --- One key input (auto-saves on blur / Enter, flashes "Saved") ------------------

function KeyFieldInput({
	def,
	serverDefault
}: {
	def: FieldDef;
	serverDefault: boolean;
}) {
	const keys = useCredentialsStore((s) => s.keys);
	const saveKeys = useCredentialsStore((s) => s.saveKeys);

	const storeValue = keys?.[def.field] ?? '';
	const [draft, setDraft] = useState(storeValue);
	const [saved, setSaved] = useState(false);
	const [reveal, setReveal] = useState(false);

	// External updates (unlock, inline node saves) sync into the draft.
	useEffect(() => {
		setDraft(storeValue);
	}, [storeValue]);

	const commit = async () => {
		if (draft === storeValue) return;
		const ok = await saveKeys({ [def.field]: draft });
		if (ok) {
			setSaved(true);
			window.setTimeout(() => setSaved(false), 1600);
		}
	};

	return (
		<div className="space-y-1.5" data-testid={`vault-field-${def.field}`}>
			<div className="flex items-center justify-between gap-2">
				<Label htmlFor={`vault-${def.field}`} className="text-xs">
					{def.label}
				</Label>
				<KeyStatusPill
					value={storeValue}
					serverDefault={serverDefault}
					emptyLabel={def.emptyLabel}
				/>
			</div>
			<div className="relative">
				<Input
					id={`vault-${def.field}`}
					type={def.plaintext || reveal ? 'text' : 'password'}
					value={draft}
					placeholder={def.placeholder}
					autoComplete="off"
					spellCheck={false}
					onChange={(e) => setDraft(e.target.value)}
					onBlur={() => void commit()}
					onKeyDown={(e) => {
						if (e.key === 'Enter') void commit();
					}}
					className={cn('h-8 pr-8 text-xs', !def.plaintext && 'pr-9')}
					data-testid={`vault-input-${def.field}`}
				/>
				{!def.plaintext && (
					<button
						type="button"
						onClick={() => setReveal((r) => !r)}
						aria-label={reveal ? 'Hide key' : 'Reveal key'}
						className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
					>
						{reveal ? (
							<EyeOff className="size-3.5" />
						) : (
							<Eye className="size-3.5" />
						)}
					</button>
				)}
			</div>
			{saved && (
				<p
					className="flex items-center gap-1 text-[10px] text-emerald-400"
					data-testid={`vault-saved-${def.field}`}
				>
					<Check className="size-3" /> Saved — encrypted to the local vault
				</p>
			)}
		</div>
	);
}

// --- Vault sections ---------------------------------------------------------------

function PassphraseInput({
	id,
	value,
	onChange,
	placeholder
}: {
	id: string;
	value: string;
	onChange: (v: string) => void;
	placeholder: string;
}) {
	const [reveal, setReveal] = useState(false);
	return (
		<div className="relative">
			<Input
				id={id}
				type={reveal ? 'text' : 'password'}
				value={value}
				placeholder={placeholder}
				autoComplete="new-password"
				onChange={(e) => onChange(e.target.value)}
				onKeyDown={(e) => {
					if (e.key === 'Enter') e.currentTarget.form?.requestSubmit();
				}}
				className="h-9 pr-9 text-sm"
				data-testid={id}
			/>
			<button
				type="button"
				onClick={() => setReveal((r) => !r)}
				aria-label={reveal ? 'Hide passphrase' : 'Reveal passphrase'}
				className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
			>
				{reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
			</button>
		</div>
	);
}

function CreateVaultSection() {
	const createVault = useCredentialsStore((s) => s.createVault);
	const busy = useCredentialsStore((s) => s.busy);
	const [passphrase, setPassphrase] = useState('');
	const [confirm, setConfirm] = useState('');
	const [localError, setLocalError] = useState<string | null>(null);

	const submit = async (e: React.FormEvent) => {
		e.preventDefault();
		if (passphrase.length < 8) {
			setLocalError('Use at least 8 characters.');
			return;
		}
		if (passphrase !== confirm) {
			setLocalError('Passphrases do not match.');
			return;
		}
		setLocalError(null);
		await createVault(passphrase);
	};

	return (
		<form className="space-y-4" onSubmit={(e) => void submit(e)}>
			<div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs leading-relaxed text-muted-foreground">
				<p className="flex items-center gap-1.5 font-medium text-emerald-300">
					<ShieldCheck className="size-3.5" /> Create your key vault
				</p>
				<p className="mt-1">
					Keys are encrypted with AES-GCM-256 (PBKDF2, 310k iterations) before
					they touch localStorage. Decrypted keys exist only in memory while the
					vault is unlocked — zero plaintext keys on disk.
				</p>
			</div>
			<div className="space-y-1.5">
				<Label htmlFor="vault-passphrase">Master passphrase</Label>
				<PassphraseInput
					id="vault-passphrase"
					value={passphrase}
					onChange={setPassphrase}
					placeholder="At least 8 characters"
				/>
			</div>
			<div className="space-y-1.5">
				<Label htmlFor="vault-passphrase-confirm">Confirm passphrase</Label>
				<PassphraseInput
					id="vault-passphrase-confirm"
					value={confirm}
					onChange={setConfirm}
					placeholder="Repeat the passphrase"
				/>
			</div>
			{localError && (
				<p className="text-xs text-red-400" role="alert">
					{localError}
				</p>
			)}
			<Button type="submit" size="sm" className="w-full" disabled={busy}>
				{busy ? (
					<Loader2 className="size-4 animate-spin" />
				) : (
					<KeyRound className="size-4" />
				)}
				Create vault
			</Button>
		</form>
	);
}

function UnlockSection() {
	const unlock = useCredentialsStore((s) => s.unlock);
	const busy = useCredentialsStore((s) => s.busy);
	const [passphrase, setPassphrase] = useState('');

	const submit = async (e: React.FormEvent) => {
		e.preventDefault();
		await unlock(passphrase);
	};

	return (
		<form className="space-y-4" onSubmit={(e) => void submit(e)}>
			<div className="flex items-center gap-2 rounded-lg border border-border/60 bg-muted/20 p-3 text-xs text-muted-foreground">
				<Lock className="size-4 shrink-0 text-amber-400" />
				The vault is locked for this session. Enter your master passphrase to
				decrypt your keys.
			</div>
			<div className="space-y-1.5">
				<Label htmlFor="vault-unlock-passphrase">Master passphrase</Label>
				<PassphraseInput
					id="vault-unlock-passphrase"
					value={passphrase}
					onChange={setPassphrase}
					placeholder="Your vault passphrase"
				/>
			</div>
			<Button type="submit" size="sm" className="w-full" disabled={busy}>
				{busy ? (
					<Loader2 className="size-4 animate-spin" />
				) : (
					<LockOpen className="size-4" />
				)}
				Unlock vault
			</Button>
			<ForgotPassphrase />
		</form>
	);
}

function ForgotPassphrase() {
	const clearVault = useCredentialsStore((s) => s.clearVault);
	const [confirming, setConfirming] = useState(false);

	if (!confirming) {
		return (
			<p className="text-center text-[11px] text-muted-foreground">
				Forgot the passphrase?{' '}
				<button
					type="button"
					className="underline transition-colors hover:text-foreground"
					onClick={() => setConfirming(true)}
				>
					Clear the vault and start over
				</button>
			</p>
		);
	}
	return (
		<div className="rounded-lg border border-red-500/30 bg-red-500/5 p-2.5 text-[11px] text-red-300">
			<p>
				Clearing the vault permanently deletes the encrypted blob from this
				browser. Saved keys cannot be recovered without the passphrase.
			</p>
			<div className="mt-2 flex gap-2">
				<Button
					type="button"
					size="sm"
					variant="destructive"
					className="h-7 flex-1"
					onClick={clearVault}
				>
					<Trash2 className="size-3.5" /> Clear vault
				</Button>
				<Button
					type="button"
					size="sm"
					variant="ghost"
					className="h-7 flex-1"
					onClick={() => setConfirming(false)}
				>
					Cancel
				</Button>
			</div>
		</div>
	);
}

function SectionCard({
	title,
	children
}: {
	title: string;
	children: React.ReactNode;
}) {
	return (
		<section className="rounded-lg border border-border/60 bg-card/60 p-3">
			<h3 className="mb-3 text-xs font-semibold tracking-wide uppercase">
				{title}
			</h3>
			<div className="space-y-3">{children}</div>
		</section>
	);
}

function ManageKeysSection({
	caps
}: {
	caps: Record<string, boolean> | undefined;
}) {
	const lock = useCredentialsStore((s) => s.lock);
	const isSet = (flag: string) => Boolean(caps?.[flag]);

	return (
		<div className="space-y-4">
			<div
				className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2.5 text-xs text-emerald-300"
				data-testid="vault-unlocked-banner"
			>
				<LockOpen className="size-4 shrink-0" />
				Vault unlocked — keys apply to requests in this session and re-encrypt
				on every save.
			</div>

			<SectionCard title="LLM Keys">
				<KeyFieldInput
					def={LLM_FIELDS[0]}
					serverDefault={isSet(LLM_FIELDS[0].serverFlag)}
				/>
				<KeyFieldInput
					def={LLM_FIELDS[1]}
					serverDefault={isSet(LLM_FIELDS[1].serverFlag)}
				/>
				<KeyFieldInput
					def={LLM_FIELDS[2]}
					serverDefault={isSet(LLM_FIELDS[2].serverFlag)}
				/>
				<KeyFieldInput
					def={LLM_FIELDS[3]}
					serverDefault={isSet(LLM_FIELDS[3].serverFlag)}
				/>
				<KeyFieldInput def={BASE_URL_FIELD} serverDefault={false} />
				<p className="text-[10px] leading-snug text-muted-foreground">
					The custom base URL applies when the model connector leaves its own
					URL blank (e.g. point it at OpenRouter or Groq and the matching key is
					used automatically).
				</p>
			</SectionCard>

			<SectionCard title="TTS Keys">
				{TTS_FIELDS.map((def) => (
					<KeyFieldInput
						key={def.field}
						def={def}
						serverDefault={isSet(def.serverFlag)}
					/>
				))}
				<p className="text-[10px] leading-snug text-muted-foreground">
					Free engines — Edge-TTS, Meme Classic (Brian), TikTok, Google — need
					no keys.
				</p>
			</SectionCard>

			<SectionCard title="Stock Video Keys">
				{STOCK_FIELDS.map((def) => (
					<KeyFieldInput
						key={def.field}
						def={def}
						serverDefault={isSet(def.serverFlag)}
					/>
				))}
			</SectionCard>

			<div className="flex gap-2">
				<Button
					variant="outline"
					size="sm"
					className="flex-1"
					onClick={lock}
					data-testid="lock-vault"
				>
					<Lock className="size-4" /> Lock Vault
				</Button>
				<ForgotPassphrase />
			</div>
		</div>
	);
}

// --- The drawer -------------------------------------------------------------------

export function ApiKeysSheet() {
	const status = useCredentialsStore((s) => s.status);
	const settingsOpen = useCredentialsStore((s) => s.settingsOpen);
	const openSettings = useCredentialsStore((s) => s.openSettings);
	const closeSettings = useCredentialsStore((s) => s.closeSettings);
	const initFromStorage = useCredentialsStore((s) => s.initFromStorage);
	const error = useCredentialsStore((s) => s.error);

	// Hydrate the vault status on mount (ciphertext presence check only —
	// no decryption happens until the user enters the passphrase).
	useEffect(() => {
		initFromStorage();
	}, [initFromStorage]);

	// Server-default presence drives the "Using Server Default" pills;
	// shares the ['health'] query with the studio header.
	const { data: health } = useQuery({
		queryKey: ['health'],
		queryFn: MemeforgeAPI.health,
		retry: false,
		refetchInterval: 30_000
	});

	return (
		<Sheet
			open={settingsOpen}
			onOpenChange={(open) => (open ? openSettings() : closeSettings())}
		>
			<SheetContent
				side="right"
				className="w-full overflow-y-auto p-0 sm:max-w-md"
				data-testid="api-keys-drawer"
			>
				<SheetHeader className="border-b border-border/60">
					<SheetTitle className="flex items-center gap-2 text-base">
						<KeyRound className="size-4" /> Settings — API Keys
					</SheetTitle>
					<SheetDescription className="text-xs">
						Encrypted local vault · AES-GCM-256 + PBKDF2 · keys stay in this
						browser
					</SheetDescription>
				</SheetHeader>
				<div className="space-y-4 p-4">
					{status === 'uninitialized' && <CreateVaultSection />}
					{status === 'locked' && <UnlockSection />}
					{status === 'unlocked' && (
						<ManageKeysSection caps={health?.capabilities} />
					)}
					{error && (
						<p className="text-xs text-red-400" role="alert">
							{error}
						</p>
					)}
				</div>
			</SheetContent>
		</Sheet>
	);
}

// --- Compact inline section for studio nodes ---------------------------------------
//
// Shown by VoiceoverNode (ElevenLabs / Azure) and GameplayNode (stock tab)
// so keys can be managed in context without opening the drawer.

export function InlineVaultSection({
	title,
	fields,
	compact
}: {
	title: string;
	fields: FieldDef[];
	/** Hide the collapsible chrome (single field rows stay compact). */
	compact?: boolean;
}) {
	const status = useCredentialsStore((s) => s.status);
	const openSettings = useCredentialsStore((s) => s.openSettings);
	const [open, setOpen] = useState(false);

	if (status !== 'unlocked') {
		return (
			<div className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-muted/20 px-2.5 py-2 text-[11px] text-muted-foreground">
				<span className="flex items-center gap-1.5">
					<KeyRound className="size-3.5 shrink-0 text-amber-400" />
					{status === 'locked'
						? 'Key vault locked — unlock to use saved keys.'
						: 'Save keys in the encrypted vault.'}
				</span>
				<Button
					variant="outline"
					size="sm"
					className="h-6 shrink-0 px-2 text-[10px]"
					onClick={openSettings}
					data-testid="inline-open-settings"
				>
					{status === 'locked' ? 'Unlock' : 'Set up'}
				</Button>
			</div>
		);
	}

	const body = (
		<div className="space-y-3 rounded-lg border border-border/60 bg-muted/20 p-2.5">
			{fields.map((def) => (
				<InlineKeyField key={def.field} def={def} />
			))}
		</div>
	);

	if (compact) {
		return (
			<div className="space-y-1.5" data-testid="inline-vault-section">
				<button
					type="button"
					onClick={() => setOpen((o) => !o)}
					className="flex w-full items-center justify-between text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
					aria-expanded={open}
				>
					<span className="flex items-center gap-1.5">
						<KeyRound className="size-3.5 text-emerald-400" />
						{title}
					</span>
					<ChevronDown
						className={cn(
							'size-3.5 transition-transform',
							open && 'rotate-180'
						)}
					/>
				</button>
				{open && body}
			</div>
		);
	}

	return (
		<div className="space-y-3" data-testid="inline-vault-section">
			<p className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
				<KeyRound className="size-3.5 text-emerald-400" />
				{title}
			</p>
			{body}
		</div>
	);
}

/** Inline variant: local draft + explicit "Save key" button + flash. */
function InlineKeyField({ def }: { def: FieldDef }) {
	const keys = useCredentialsStore((s) => s.keys);
	const saveKeys = useCredentialsStore((s) => s.saveKeys);
	const busy = useCredentialsStore((s) => s.busy);

	const storeValue = keys?.[def.field] ?? '';
	const [draft, setDraft] = useState(storeValue);
	const [saved, setSaved] = useState(false);

	useEffect(() => {
		setDraft(storeValue);
	}, [storeValue]);

	const dirty = draft !== storeValue;

	const save = async () => {
		if (!dirty) return;
		const ok = await saveKeys({ [def.field]: draft });
		if (ok) {
			setSaved(true);
			window.setTimeout(() => setSaved(false), 1600);
		}
	};

	return (
		<div className="space-y-1">
			<div className="flex items-center justify-between gap-2">
				<Label htmlFor={`inline-${def.field}`} className="text-[11px]">
					{def.label}
				</Label>
				{storeValue ? (
					<span className="text-[10px] font-medium text-emerald-400">
						✓ saved
					</span>
				) : null}
			</div>
			<div className="flex gap-1.5">
				<Input
					id={`inline-${def.field}`}
					type={def.plaintext ? 'text' : 'password'}
					value={draft}
					placeholder={def.placeholder}
					autoComplete="off"
					spellCheck={false}
					onChange={(e) => setDraft(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === 'Enter') void save();
					}}
					className="h-8 flex-1 text-xs"
					data-testid={`inline-input-${def.field}`}
				/>
				<Button
					size="sm"
					variant="outline"
					className="h-8 shrink-0 px-2.5 text-xs"
					onClick={() => void save()}
					disabled={busy || (!dirty && !storeValue)}
				>
					{saved ? <Check className="size-3.5" /> : null}
					{saved ? 'Saved' : 'Save key'}
				</Button>
			</div>
			{saved && (
				<p
					className="text-[10px] text-emerald-400"
					data-testid={`inline-saved-${def.field}`}
				>
					Saved — encrypted to the local vault
				</p>
			)}
		</div>
	);
}
