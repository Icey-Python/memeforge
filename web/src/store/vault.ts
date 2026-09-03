'use client';

// Desc: Secure in-memory key vault shared by every studio node.
//
// Decrypted secrets live ONLY in this store's memory (never persisted);
// the persisted form is the AES-GCM-256 blob from lib/vault-crypto.ts,
// unlocked with a master passphrase. On unlock / save / lock the vault
// hydrates the pipeline store's credential fields so requests carry the
// keys without the user re-typing them.
//
// Vault entry ids:
//   llm.{preset}.apiKey    — OpenAI / Anthropic / Groq / OpenRouter / custom
//   tts.{provider}.apiKey  — ElevenLabs / Azure
//   stock.{provider}.apiKey — Pexels / Pixabay

import { create } from 'zustand';
import {
	decryptVault,
	deriveVaultKey,
	encryptVault,
	loadVaultBlob,
	newSaltB64,
	saveVaultBlob,
	VaultCryptoError,
	vaultExists
} from '@/lib/vault-crypto';
import { usePipelineStore } from '@/store/pipeline';

export type VaultStatus = 'locked' | 'empty' | 'unlocked';

/** Session-only derived AES key — never leaves memory, never serialized. */
let sessionKey: CryptoKey | null = null;
let sessionSalt = '';

/** Copy vault entries into the pipeline store's credential fields. */
function hydratePipeline(entries: Record<string, string>): void {
	const pipeline = usePipelineStore.getState();
	const model = pipeline.model;
	pipeline.setCredentials({
		llmApiKey: entries[`llm.${model.provider}.apiKey`] ?? '',
		ttsApiKey: entries[`tts.${pipeline.ttsProvider}.apiKey`] ?? '',
		stockPexelsKey: entries['stock.pexels.apiKey'] ?? '',
		stockPixabayKey: entries['stock.pixabay.apiKey'] ?? ''
	});
}

interface VaultStore {
	status: VaultStatus;
	busy: boolean;
	error: string | null;
	/** Decrypted secrets — in-memory only, never written to disk. */
	entries: Record<string, string>;
	/** Reconcile `status` with localStorage (call once on mount). */
	syncStatus: () => void;
	/** Create a new vault (fails if one already exists). */
	createVault: (passphrase: string) => Promise<boolean>;
	/** Decrypt the vault with the master passphrase. */
	unlock: (passphrase: string) => Promise<boolean>;
	/** Drop the in-memory key + secrets (blob stays encrypted on disk). */
	lock: () => void;
	/** Encrypt + persist one secret (requires an unlocked vault). */
	saveEntry: (id: string, secret: string) => Promise<boolean>;
	deleteEntry: (id: string) => Promise<boolean>;
}

export const useVaultStore = create<VaultStore>((set, get) => ({
	status: 'locked',
	busy: false,
	error: null,
	entries: {},

	syncStatus: () => {
		if (get().status === 'unlocked') return; // keep the live session
		set({ status: vaultExists() ? 'locked' : 'empty', error: null });
	},

	createVault: async (passphrase) => {
		if (vaultExists()) {
			set({ error: 'A vault already exists — unlock it instead.' });
			return false;
		}
		if (passphrase.length < 8) {
			set({ error: 'Passphrase must be at least 8 characters.' });
			return false;
		}
		set({ busy: true, error: null });
		try {
			const salt = newSaltB64();
			const key = await deriveVaultKey(passphrase, salt);
			const blob = await encryptVault(key, salt, {});
			saveVaultBlob(blob);
			sessionKey = key;
			sessionSalt = salt;
			set({ status: 'unlocked', entries: {}, busy: false });
			return true;
		} catch (err) {
			set({ busy: false, error: `Vault setup failed: ${String(err)}` });
			return false;
		}
	},

	unlock: async (passphrase) => {
		const blob = loadVaultBlob();
		if (!blob) {
			set({ error: 'No saved vault yet — save a key to create one.' });
			return false;
		}
		set({ busy: true, error: null });
		try {
			const key = await deriveVaultKey(
				passphrase,
				blob.kdf.salt,
				blob.kdf.iterations
			);
			const entries = await decryptVault(key, blob);
			sessionKey = key;
			sessionSalt = blob.kdf.salt;
			set({ status: 'unlocked', entries, busy: false });
			hydratePipeline(entries);
			return true;
		} catch (err) {
			const message =
				err instanceof VaultCryptoError
					? 'Wrong passphrase — try again.'
					: `Unlock failed: ${String(err)}`;
			set({ busy: false, error: message });
			return false;
		}
	},

	lock: () => {
		sessionKey = null;
		sessionSalt = '';
		set({ status: vaultExists() ? 'locked' : 'empty', entries: {} });
		// Clear the hydrated pipeline credentials too.
		hydratePipeline({});
	},

	saveEntry: async (id, secret) => {
		if (!sessionKey) {
			set({ error: 'Vault is locked — unlock it before saving keys.' });
			return false;
		}
		set({ busy: true, error: null });
		try {
			const entries = { ...get().entries, [id]: secret };
			const blob = await encryptVault(sessionKey, sessionSalt, entries);
			saveVaultBlob(blob);
			set({ entries, status: 'unlocked', busy: false });
			hydratePipeline(entries);
			return true;
		} catch (err) {
			set({ busy: false, error: `Saving the key failed: ${String(err)}` });
			return false;
		}
	},

	deleteEntry: async (id) => {
		if (!sessionKey) return false;
		set({ busy: true, error: null });
		try {
			const entries = { ...get().entries };
			delete entries[id];
			const blob = await encryptVault(sessionKey, sessionSalt, entries);
			saveVaultBlob(blob);
			set({ entries, busy: false });
			hydratePipeline(entries);
			return true;
		} catch (err) {
			set({ busy: false, error: `Removing the key failed: ${String(err)}` });
			return false;
		}
	}
}));

/** Read one decrypted secret (empty string when locked/missing). */
export function vaultSecret(id: string): string {
	return useVaultStore.getState().entries[id] ?? '';
}
