from pathlib import Path
import re

ROOT = Path('/home/ubuntu/metashield-protocol')
old_test = ROOT / 'scripts/test-threads-background.js'
s = old_test.read_text()

# Existing positive fixture must represent a production-safe key generation.
anchor = '''  "user_owner-1_nativeWalletPrivateKey": "1".repeat(64),
  "user_owner-1_identityAlias": "threadstest",
'''
replacement = '''  "user_owner-1_nativeWalletPrivateKey": "1".repeat(64),
  "user_owner-1_recoveryExportedAt": "2026-08-31T00:00:00.000Z",
  "user_owner-1_recoveryVaultAccountId": "fixture-vault-account",
  "user_owner-1_recoveryExportConfirmedVersion": "2-of-3-vault-v1",
  "user_owner-1_recoveryLocalShare": {
    format: "chamber-recovery-share-v2",
    scheme: "shamir-2-of-3",
    setId: "fixture-recovery-set-A",
    ownerUserId: "owner-1",
    facebookUserId: "owner-1",
    ownerAddress: "0x1111111111111111111111111111111111111111",
    keyTier: "native",
    share: { x: 1, data: "fixture-local-share-A" }
  },
  "user_owner-1_identityAlias": "threadstest",
'''
if '"user_owner-1_recoveryVaultAccountId": "fixture-vault-account"' not in s:
    if anchor not in s:
        raise SystemExit('positive fixture anchor missing')
    s = s.replace(anchor, replacement, 1)

anchor = '''  assert.equal(backupRequest.encryptionVersion, "post-key-v2");
  assert.ok(backupRequest.keyEnvelope?.wrapped_key);
'''
replacement = '''  assert.equal(backupRequest.encryptionVersion, "post-key-v2");
  assert.equal(backupRequest.ownerKeyId, "0x1111111111111111111111111111111111111111");
  assert.equal(backupRequest.recoverySetId, "fixture-recovery-set-A");
  assert.equal(backupRequest.recoveryCoverage, "verified");
  assert.ok(backupRequest.keyEnvelope?.wrapped_key);
'''
if 'assert.equal(backupRequest.recoveryCoverage, "verified");' not in s:
    if anchor not in s:
        raise SystemExit('positive lineage assertion anchor missing')
    s = s.replace(anchor, replacement, 1)

replacement = '''  assert.equal(storage["user_owner-1_recoveryLocalShare"].setId, "fixture-recovery-set-A");
  assert.equal(storage["user_owner-1_recoveryExportConfirmedVersion"], "2-of-3-vault-v1");
  console.log("Threads background pipeline passed: recovery-covered key generation, local post/media encryption, identity, receipt and Echo route.");
'''
if 'PREPARE_RECOVERY_VAULT' in s[s.find('.then(async (result) => {'):]:
    pattern = re.compile(
        r'''  const recovery = await new Promise\(\(resolve, reject\) => \{.*?^  console\.log\([^\n]*Threads background pipeline passed[^\n]*\);\n''',
        re.S | re.M,
    )
    s2, count = pattern.subn(replacement, s, count=1)
    if count != 1:
        raise SystemExit('post-backup recovery structure not found')
    s = s2
elif 'recovery-covered key generation' not in s:
    raise SystemExit('post-backup recovery block missing')
old_test.write_text(s)

g9 = r'''const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const extensionDir = path.resolve(__dirname, "../extension");
const OWNER_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const OWNER_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const SECRET_A = "a".repeat(64);
const SECRET_B = "b".repeat(64);

function makeHarness(overrides = {}) {
  const storage = {
    lastFbUserId: "owner-1",
    activeChamberProfileId: "profile-1",
    chamberProfiles: [{ id: "profile-1", name: "G9 Tester", alias: "g9test", walletAddress: OWNER_B, ownerUserId: "owner-1" }],
    "user_owner-1_customWalletAddress": OWNER_B,
    "user_owner-1_customWalletPrivateKey": SECRET_B,
    "user_owner-1_identityAlias": "g9test",
    "user_owner-1_identityPlatform": "threads",
    "user_owner-1_identityActorType": "personal",
    "user_owner-1_identityActorId": "threads-g9",
    ...overrides,
  };
  let listener = null;
  const fetches = [];
  const select = (keys) => {
    if (keys == null) return { ...storage };
    if (typeof keys === "string") return { [keys]: storage[keys] };
    if (Array.isArray(keys)) return Object.fromEntries(keys.map((key) => [key, storage[key]]));
    return Object.fromEntries(Object.entries(keys).map(([key, fallback]) => [key, storage[key] ?? fallback]));
  };
  const context = vm.createContext({
    console, crypto: webcrypto, TextEncoder, TextDecoder, Uint8Array, ArrayBuffer, Blob, FormData,
    URL, URLSearchParams, Response, Headers, Request, setTimeout, clearTimeout,
    setInterval: () => 1, clearInterval: () => {},
    btoa: (v) => Buffer.from(v, "binary").toString("base64"),
    atob: (v) => Buffer.from(v, "base64").toString("binary"),
    self: { crypto: webcrypto, addEventListener: () => {} },
    chrome: {
      sidePanel: { setPanelBehavior: async () => {} },
      runtime: { getManifest: () => ({ version: "1.0.64" }), onMessage: { addListener: (v) => { listener = v; } } },
      storage: {
        local: {
          get: (keys, cb) => { const v = select(keys); if (cb) { cb(v); return; } return Promise.resolve(v); },
          set: (values, cb) => { Object.assign(storage, values); cb?.(); return Promise.resolve(); },
          remove: (keys, cb) => { for (const key of (Array.isArray(keys) ? keys : [keys])) delete storage[key]; cb?.(); return Promise.resolve(); },
        },
        onChanged: { addListener: () => {} },
      },
    },
    fetch: async (url, options = {}) => {
      const target = String(url);
      fetches.push(target);
      if (target.endsWith("/dev-errors")) return new Response(JSON.stringify({ success: true }), { status: 202, headers: { "Content-Type": "application/json" } });
      if (target === "https://cdninstagram.example/g9.jpg") return new Response(new Blob([Uint8Array.from([1,2,3])], { type: "image/jpeg" }), { status: 200, headers: { "Content-Type": "image/jpeg" } });
      if (target.endsWith("/chamber-api/media")) return new Response(JSON.stringify({ success: true, txId: "media-g9", url: "https://gateway.irys.xyz/media-g9", network: "devnet" }), { status: 200, headers: { "Content-Type": "application/json" } });
      if (target.endsWith("/chamber-api/backup")) return new Response(JSON.stringify({ success: true, requestId: "req-g9", txId: "post-g9", echoUrl: "https://studio.milkcat.org/echo/g9test/threads?post=post-g9&network=devnet", network: "devnet" }), { status: 200, headers: { "Content-Type": "application/json" } });
      throw new Error(`Unexpected fetch: ${target}`);
    },
  });
  context.globalThis = context;
  context.importScripts = (...files) => files.forEach((file) => vm.runInContext(fs.readFileSync(path.join(extensionDir, file), "utf8"), context, { filename: file }));
  vm.runInContext(fs.readFileSync(path.join(extensionDir, "background.js"), "utf8"), context, { filename: "background.js" });
  assert.equal(typeof listener, "function");
  return { storage, fetches, context, listener };
}

function send(listener, message) {
  return new Promise((resolve) => {
    const keepOpen = listener(message, {}, resolve);
    assert.equal(keepOpen, true);
  });
}

const post = {
  platform: "threads", fbUserId: "owner-1", identityActorId: "threads-g9", identityActorType: "personal",
  identityDisplayName: "@g9test", textContent: "G9 must fail before upload", sourceUrl: "https://www.threads.com/@g9test/post/G9_Test",
  authorName: "@g9test", authorUrl: "https://www.threads.com/@g9test", publishedAt: 1786660000, timestamp: 1786660000,
  isOwnAuthor: true, contentExpanded: true, mediaUrls: ["https://cdninstagram.example/g9.jpg"],
  media: { primary_fb_cdn: "https://cdninstagram.example/g9.jpg", album: false, albumComplete: true, albumLoadedCount: 1, albumExpectedCount: 1, videoDetected: false },
};

(async () => {
  {
    const h = makeHarness();
    const result = await send(h.listener, { action: "BACKUP_HISTORIC_POST", payload: post });
    assert.equal(result.success, false);
    assert.equal(result.code, "RECOVERY_COVERAGE_REQUIRED");
    assert.equal(h.fetches.filter((u) => !u.endsWith("/dev-errors")).length, 0, `unexpected upload-side fetches: ${h.fetches.join(", ")}`);
  }

  {
    const h = makeHarness({
      "user_owner-1_recoveryExportedAt": "2026-08-31T00:00:00Z",
      "user_owner-1_recoveryVaultAccountId": "vault-A",
      "user_owner-1_recoveryExportConfirmedVersion": "2-of-3-vault-v1",
      "user_owner-1_recoveryLocalShare": { setId: "set-A", ownerAddress: OWNER_A, share: { x: 1, data: "fixture" } },
    });
    const result = await send(h.listener, { action: "BACKUP_HISTORIC_POST", payload: post });
    assert.equal(result.success, false);
    assert.equal(result.code, "RECOVERY_COVERAGE_REQUIRED");
    assert.equal(h.fetches.filter((u) => !u.endsWith("/dev-errors")).length, 0);
  }

  {
    const h = makeHarness();
    await h.context.storeLegacyOwnerKey("owner-1", { ownerAddress: OWNER_A, setId: "set-A", keyTier: "native" }, SECRET_A);
    assert.equal(h.storage["user_owner-1_customWalletAddress"], OWNER_B);
    assert.equal(h.storage["user_owner-1_customWalletPrivateKey"], SECRET_B);
    assert.equal(h.storage["user_owner-1_legacyOwnerKeys"][0].ownerAddress, OWNER_A);
    assert.equal(h.storage["user_owner-1_legacyOwnerKeys"][0].ownerSecret, SECRET_A);

    async function makeEncrypted(ownerSecret, text) {
      const postKeyBytes = webcrypto.getRandomValues(new Uint8Array(32));
      const envelope = await h.context.createOwnerEnvelope(postKeyBytes, ownerSecret);
      const postKey = await h.context.importPostKey(postKeyBytes);
      const iv = webcrypto.getRandomValues(new Uint8Array(12));
      const ciphertext = new Uint8Array(await webcrypto.subtle.encrypt({ name: "AES-GCM", iv }, postKey, new TextEncoder().encode(text)));
      return { envelope, iv: h.context.bytesToBase64(iv), ciphertext: h.context.bytesToBase64(ciphertext) };
    }

    const oldObj = await makeEncrypted(SECRET_A, "generation-A-content");
    const newObj = await makeEncrypted(SECRET_B, "generation-B-content");
    const oldResult = await send(h.listener, { action: "DECRYPT_OWNER_DATA", ownerKeyEnvelope: oldObj.envelope, iv: oldObj.iv, ciphertext: oldObj.ciphertext, mode: "text" });
    const newResult = await send(h.listener, { action: "DECRYPT_OWNER_DATA", ownerKeyEnvelope: newObj.envelope, iv: newObj.iv, ciphertext: newObj.ciphertext, mode: "text" });
    assert.equal(oldResult.success, true);
    assert.equal(oldResult.plaintext, "generation-A-content");
    assert.equal(newResult.success, true);
    assert.equal(newResult.plaintext, "generation-B-content");
    assert.equal(h.storage["user_owner-1_customWalletAddress"], OWNER_B, "Generation B must remain active after recovering A");
    assert.equal(h.storage["user_owner-1_customWalletPrivateKey"], SECRET_B, "Generation B private key must not be overwritten");
  }

  console.log("G9 regressions passed: missing/mismatched recovery blocks before upload; legacy Generation A and active Generation B both decrypt without key replacement.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
'''
(ROOT / 'scripts/test-no-irrecoverable-preservation.js').write_text(g9)
print('g9_tests_installed=true')
