// Desc: Encrypted key vault primitives (WebCrypto, client-side only).
//
// API keys never touch localStorage in plaintext. The whole vault is one
// AES-GCM-256-encrypted blob whose key is derived from a master
// passphrase via PBKDF2-HMAC-SHA256 (310k iterations, per OWASP). The
// derived CryptoKey is non-extractable and lives only in memory for the
// session (see store/vault.ts); decryption failures surface as
// VaultCryptoError (wrong passphrase / corrupted blob).
//
// Requires a secure context (https or localhost) for crypto.subtle.

/** OWASP-recommended PBKDF2-HMAC-SHA256 iteration count. */
export const KDF_ITERATIONS = 310_000;

const SALT_BYTES = 16;
const IV_BYTES = 12;
export const VAULT_STORAGE_KEY = 'memeforge.vault.v1';

/** The encrypted blob persisted to localStorage (never plaintext). */
export interface EncryptedVault {
	version: 1;
	kdf: {
		algorithm: 'PBKDF2-SHA256';
		iterations: number;
		/** base64 */
		salt: string;
	};
	cipher: {
		algorithm: 'AES-GCM-256';
		/** base64 */
		iv: string;
		/** base64 ciphertext */
		ct: string;
	};
}

export class VaultCryptoError extends Error {}

function toB64(bytes: Uint8Array): string {
	let binary = '';
	for (const b of bytes) binary += String.fromCharCode(b);
	return btoa(binary);
}

function fromB64(b64: string): Uint8Array<ArrayBuffer> {
	return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

/** Derive the (non-extractable) AES-GCM-256 key from a passphrase. */
export async function deriveVaultKey(
	passphrase: string,
	saltB64: string,
	iterations: number = KDF_ITERATIONS
): Promise<CryptoKey> {
	const material = await crypto.subtle.importKey(
		'raw',
		new TextEncoder().encode(passphrase),
		'PBKDF2',
		false,
		['deriveKey']
	);
	return crypto.subtle.deriveKey(
		{ name: 'PBKDF2', salt: fromB64(saltB64), iterations, hash: 'SHA-256' },
		material,
		{ name: 'AES-GCM', length: 256 },
		// non-extractable: the raw key material never leaves WebCrypto
		false,
		['encrypt', 'decrypt']
	);
}

export function newSaltB64(): string {
	return toB64(crypto.getRandomValues(new Uint8Array(SALT_BYTES)));
}

/** Encrypt the entries map into a fresh blob (new random IV). */
export async function encryptVault(
	key: CryptoKey,
	saltB64: string,
	entries: Record<string, string>
): Promise<EncryptedVault> {
	const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
	const plaintext = new TextEncoder().encode(JSON.stringify(entries));
	const ct = await crypto.subtle.encrypt(
		{ name: 'AES-GCM', iv },
		key,
		plaintext
	);
	return {
		version: 1,
		kdf: {
			algorithm: 'PBKDF2-SHA256',
			iterations: KDF_ITERATIONS,
			salt: saltB64
		},
		cipher: {
			algorithm: 'AES-GCM-256',
			iv: toB64(iv),
			ct: toB64(new Uint8Array(ct))
		}
	};
}

/** Decrypt a blob back into the entries map; throws VaultCryptoError. */
export async function decryptVault(
	key: CryptoKey,
	blob: EncryptedVault
): Promise<Record<string, string>> {
	try {
		const plaintext = await crypto.subtle.decrypt(
			{ name: 'AES-GCM', iv: fromB64(blob.cipher.iv) },
			key,
			fromB64(blob.cipher.ct)
		);
		const parsed = JSON.parse(new TextDecoder().decode(plaintext));
		if (
			typeof parsed !== 'object' ||
			parsed === null ||
			Array.isArray(parsed)
		) {
			throw new Error('bad shape');
		}
		return parsed as Record<string, string>;
	} catch {
		// AES-GCM auth failure == wrong passphrase; anything else is a
		// corrupted blob. Either way it is a vault-level error.
		throw new VaultCryptoError('Could not decrypt the vault');
	}
}

export function loadVaultBlob(): EncryptedVault | null {
	if (typeof window === 'undefined') return null;
	try {
		const raw = window.localStorage.getItem(VAULT_STORAGE_KEY);
		return raw ? (JSON.parse(raw) as EncryptedVault) : null;
	} catch {
		return null;
	}
}

export function saveVaultBlob(blob: EncryptedVault): void {
	window.localStorage.setItem(VAULT_STORAGE_KEY, JSON.stringify(blob));
}

export function vaultExists(): boolean {
	if (typeof window === 'undefined') return false;
	return window.localStorage.getItem(VAULT_STORAGE_KEY) !== null;
}
