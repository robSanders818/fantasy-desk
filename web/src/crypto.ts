// Decrypts data/desk.fdk in the browser.
// Format (must match scripts/encrypt.py):
//   "FDK1" | salt(16) | iv(12) | AES-256-GCM(gzip(json)),  key = PBKDF2-SHA256(passphrase, salt, 310000)

import type { Bundle } from "./types";

const MAGIC = "FDK1";
const ITERATIONS = 310_000;

async function gunzip(buf: ArrayBuffer): Promise<ArrayBuffer> {
  const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).arrayBuffer();
}

export async function decryptBundle(file: ArrayBuffer, passphrase: string): Promise<Bundle> {
  const b = new Uint8Array(file);
  if (new TextDecoder().decode(b.slice(0, 4)) !== MAGIC) throw new Error("Unrecognized data file");
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: b.slice(4, 20), iterations: ITERATIONS, hash: "SHA-256" },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"],
  );
  let plain: ArrayBuffer;
  try {
    plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b.slice(20, 32) }, key, b.slice(32));
  } catch {
    throw new Error("Wrong passphrase");
  }
  return JSON.parse(new TextDecoder().decode(await gunzip(plain)));
}

const STORE = "fantasy-desk:passphrase";

export function savedPassphrase(): string | null {
  try {
    return localStorage.getItem(STORE);
  } catch {
    return null;
  }
}

export function rememberPassphrase(p: string | null) {
  try {
    if (p) localStorage.setItem(STORE, p);
    else localStorage.removeItem(STORE);
  } catch {
    /* private mode: just don't remember */
  }
}
