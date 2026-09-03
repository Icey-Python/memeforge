// Encrypted API-key vault: Web Crypto helpers (AES-GCM-256 + PBKDF2).
//
// SECURITY CONTRACT (captain directive):
// - localStorage persists ONLY ciphertext + salt + iv — never a plaintext
//   key.
// - Keys are derived from the user's master passphrase with PBKDF2-SHA256
//   (310k iterations, per-blob random salt) and used for AES-GCM-256.
// - The derived CryptoKey and decrypted keys live purely in volatile
//   memory (module state + the zustand store) and are wiped on lock,
//   clear, or page reload.
// - Web Crypto requires a secure context: https or localhost.

import type { ApiKeys } from '@/types/studio';

/** localStorage key for the encrypted vault blob. */
export const VAULT_STORAGE_KEY = 'memeforge.api-key-vault.v1';

/** PBKDF2 iteration count (spec floor: 100k; OWASP-aligned: 310k). */
export const PBKDF2_ITERATIONS = 310_000;

/** Serialized vault: versioned ciphertext envelope (base64 fields). */
export interface VaultBlob {
	v: 1;
	kdf: 'PBKDF2-SHA256';
	iterations: number;
	/** PBKDF2 salt (base64, 16 bytes). */
	salt: string;
	/** AES-GCM IV (base64, 12 bytes). */
	iv: string;
	/** Ciphertext (base64) of the JSON key map. */
	ct: string;
}

// --- base64 helpers -----------------------------------------------------------

function toB64(bytes: Uint8Array): string {
	let binary = '';
	for (let i = 0; i < bytes.length; i++) {
		binary += String.fromCharCode(bytes[i]);
	}
	return btoa(binary);
}

function fromB64(b64: string): Uint8Array<ArrayBuffer> {
	const binary = atob(b64);
	const bytes = new Uint8Array(binary.length);
	for (let i = 0; i < binary.length; i++) {
		bytes[i] = binary.charCodeAt(i);
	}
	return bytes;
}

// --- localStorage persistence (ciphertext only) --------------------------------

export function readVaultBlob(): VaultBlob | null {
	if (typeof window === 'undefined') return null;
	try {
		const raw = window.localStorage.getItem(VAULT_STORAGE_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as VaultBlob;
		if (parsed?.v !== 1 || !parsed.salt || !parsed.iv || !parsed.ct) {
			return null;
		}
		return parsed;
	} catch {
		return null;
	}
}

export function writeVaultBlob(blob: VaultBlob): void {
	if (typeof window === 'undefined') return;
	window.localStorage.setItem(VAULT_STORAGE_KEY, JSON.stringify(blob));
}

export function removeVaultBlob(): void {
	if (typeof window === 'undefined') return;
	window.localStorage.removeItem(VAULT_STORAGE_KEY);
}

// --- session key cache (volatile; never persisted) ------------------------------

let sessionKey: CryptoKey | null = null;
let sessionSalt: string | null = null;

/** Cache the unlocked session's AES key so saves skip the PBKDF2 cost. */
export function setSessionKey(key: CryptoKey, saltB64: string): void {
	sessionKey = key;
	sessionSalt = saltB64;
}

/** The cached session key, when it matches the given vault salt. */
export function getSessionKey(saltB64: string): CryptoKey | null {
	return sessionKey && sessionSalt === saltB64 ? sessionKey : null;
}

/** Wipe the cached session key (lock / clear vault). */
export function clearSessionKey(): void {
	sessionKey = null;
	sessionSalt = null;
}

// --- crypto core ----------------------------------------------------------------

async function deriveKey(
	passphrase: string,
	salt: Uint8Array<ArrayBuffer>,
	iterations: number
): Promise<CryptoKey> {
	const material = await crypto.subtle.importKey(
		'raw',
		new TextEncoder().encode(passphrase),
		'PBKDF2',
		false,
		['deriveKey']
	);
	return crypto.subtle.deriveKey(
		{
			name: 'PBKDF2',
			salt: salt,
			iterations,
			hash: 'SHA-256'
		},
		material,
		{ name: 'AES-GCM', length: 256 },
		false, // non-extractable: the raw key material can never be read out
		['encrypt', 'decrypt']
	);
}

/** Only non-empty key values are serialized (keeps blobs small). */
function serializeKeys(keys: ApiKeys): Record<string, string> {
	const out: Record<string, string> = {};
	for (const [field, value] of Object.entries(keys)) {
		if (typeof value === 'string' && value.trim()) out[field] = value.trim();
	}
	return out;
}

/** Encrypt an ApiKeys map under a fresh salt + iv with the passphrase. */
export async function encryptVault(
	passphrase: string,
	keys: ApiKeys
): Promise<VaultBlob> {
	const salt = crypto.getRandomValues(new Uint8Array(16));
	const iv = crypto.getRandomValues(new Uint8Array(12));
	const key = await deriveKey(passphrase, salt, PBKDF2_ITERATIONS);
	const plaintext = new TextEncoder().encode(
		JSON.stringify(serializeKeys(keys))
	);
	const ct = await crypto.subtle.encrypt(
		{ name: 'AES-GCM', iv: iv },
		key,
		plaintext
	);
	const blob: VaultBlob = {
		v: 1,
		kdf: 'PBKDF2-SHA256',
		iterations: PBKDF2_ITERATIONS,
		salt: toB64(salt),
		iv: toB64(iv),
		ct: toB64(new Uint8Array(ct))
	};
	setSessionKey(key, blob.salt);
	return blob;
}

/** Re-encrypt keys with the cached session key (fast path, no PBKDF2). */
export async function reencryptVault(
	blob: VaultBlob,
	keys: ApiKeys
): Promise<VaultBlob> {
	const key = getSessionKey(blob.salt);
	if (!key) throw new Error('Vault is not unlocked');
	const iv = crypto.getRandomValues(new Uint8Array(12));
	const plaintext = new TextEncoder().encode(
		JSON.stringify(serializeKeys(keys))
	);
	const ct = await crypto.subtle.encrypt(
		{ name: 'AES-GCM', iv: iv },
		key,
		plaintext
	);
	return { ...blob, iv: toB64(iv), ct: toB64(new Uint8Array(ct)) };
}

/** Decrypt a vault blob; throws on a wrong passphrase (AES-GCM auth fail). */
export async function decryptVault(
	passphrase: string,
	blob: VaultBlob
): Promise<Record<string, string>> {
	const salt = fromB64(blob.salt);
	const iv = fromB64(blob.iv);
	const key = await deriveKey(passphrase, salt, blob.iterations);
	const plaintext = await crypto.subtle.decrypt(
		{ name: 'AES-GCM', iv: iv },
		key,
		fromB64(blob.ct)
	);
	setSessionKey(key, blob.salt);
	return JSON.parse(new TextDecoder().decode(plaintext)) as Record<
		string,
		string
	>;
}
