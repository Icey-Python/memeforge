'use client';

// Desc: Encrypted API-key vault state (settings drawer + node key inputs).
//
// SECURITY CONTRACT: decrypted keys live only in this volatile store while
// the vault is unlocked; localStorage holds nothing but AES-GCM ciphertext
// (see lib/vault-crypto.ts). On reload the vault starts locked and asks
// for the master passphrase again.

import { create } from 'zustand';
import { mergeApiKeys } from '@/lib/credentials';
import {
	clearSessionKey,
	decryptVault,
	encryptVault,
	readVaultBlob,
	reencryptVault,
	removeVaultBlob,
	writeVaultBlob
} from '@/lib/vault-crypto';
import type { ApiKeys, VaultStatus } from '@/types/studio';

interface CredentialsStore {
	/** Vault lifecycle: no vault yet / exists but locked / decrypted. */
	status: VaultStatus;
	/** Decrypted keys — non-null ONLY while unlocked (volatile memory). */
	keys: ApiKeys | null;
	/** A crypto operation (derive/encrypt/decrypt) is in flight. */
	busy: boolean;
	error: string | null;
	/** Settings / API Keys drawer visibility (shared with the nodes). */
	settingsOpen: boolean;
	/** Bumped on every key save — lets queries refetch with fresh creds. */
	revision: number;

	initFromStorage: () => void;
	openSettings: () => void;
	closeSettings: () => void;
	/** Create a fresh vault (encrypting the current in-memory keys). */
	createVault: (passphrase: string) => Promise<boolean>;
	/** Decrypt the vault with the master passphrase. */
	unlock: (passphrase: string) => Promise<boolean>;
	/** Update keys in memory + re-encrypt the stored blob (unlocked only). */
	saveKeys: (patch: Partial<ApiKeys>) => Promise<boolean>;
	/** Wipe decrypted keys from memory; the blob stays on disk. */
	lock: () => void;
	/** Delete the stored blob + wipe memory (irreversible). */
	clearVault: () => void;
}

export const useCredentialsStore = create<CredentialsStore>((set, get) => ({
	status: 'uninitialized',
	keys: null,
	busy: false,
	error: null,
	settingsOpen: false,
	revision: 0,

	initFromStorage: () => {
		if (get().status !== 'uninitialized') return; // already hydrated
		set({ status: readVaultBlob() ? 'locked' : 'uninitialized' });
	},

	openSettings: () => set({ settingsOpen: true, error: null }),
	closeSettings: () => set({ settingsOpen: false }),

	createVault: async (passphrase) => {
		if (get().busy) return false;
		if (passphrase.length < 8) {
			set({ error: 'Passphrase must be at least 8 characters.' });
			return false;
		}
		set({ busy: true, error: null });
		try {
			const keys = get().keys ?? mergeApiKeys({});
			const blob = await encryptVault(passphrase, keys);
			writeVaultBlob(blob);
			set({
				status: 'unlocked',
				keys,
				busy: false,
				error: null,
				revision: get().revision + 1
			});
			return true;
		} catch {
			set({ busy: false, error: 'Could not create the vault.' });
			return false;
		}
	},

	unlock: async (passphrase) => {
		const blob = readVaultBlob();
		if (!blob) {
			set({ error: 'No vault found — create one first.' });
			return false;
		}
		if (get().busy) return false;
		set({ busy: true, error: null });
		try {
			const stored = await decryptVault(passphrase, blob);
			set({
				status: 'unlocked',
				keys: mergeApiKeys(stored),
				busy: false,
				error: null,
				revision: get().revision + 1
			});
			return true;
		} catch {
			// AES-GCM auth failure = wrong passphrase (or corrupted blob).
			set({
				busy: false,
				error: 'Wrong passphrase — could not decrypt the vault.'
			});
			return false;
		}
	},

	saveKeys: async (patch) => {
		const { status, keys } = get();
		if (status !== 'unlocked' || !keys) {
			set({ error: 'Unlock the key vault first.' });
			return false;
		}
		const next: ApiKeys = { ...keys, ...patch };
		const blob = readVaultBlob();
		if (!blob) {
			set({ error: 'Vault missing — create a new one.' });
			return false;
		}
		set({ busy: true, error: null });
		try {
			writeVaultBlob(await reencryptVault(blob, next));
			set({
				keys: next,
				busy: false,
				error: null,
				revision: get().revision + 1
			});
			return true;
		} catch {
			// Decrypted keys stay usable in memory; only persistence failed.
			set({ keys: next, busy: false, error: 'Could not persist the vault.' });
			return false;
		}
	},

	lock: () => {
		clearSessionKey();
		set({ status: 'locked', keys: null, error: null });
	},

	clearVault: () => {
		removeVaultBlob();
		clearSessionKey();
		set({
			status: 'uninitialized',
			keys: null,
			error: null,
			revision: get().revision + 1
		});
	}
}));
