from pathlib import Path
import json

root = Path('/home/ubuntu/metashield-protocol')
bg = root / 'extension/background.js'
manifest = root / 'extension/manifest.json'
s = bg.read_text(encoding='utf-8')

helper_anchor = '''// AES-GCM owner encryption. The owner secret never leaves the extension
// service worker; Echo must ask the extension to decrypt.
'''
helper = '''async function getStoredOwnerKeyCandidates(userId) {
  const prefix = `user_${userId || "default"}_`;
  const keys = [prefix + "customWalletPrivateKey", prefix + "nativeWalletPrivateKey"];
  const stored = await chrome.storage.local.get(keys);
  return [...new Set(keys.map((key) => stored[key]).filter(Boolean))];
}

'''
if 'async function getStoredOwnerKeyCandidates(userId)' not in s:
    if helper_anchor not in s:
        raise SystemExit('owner helper anchor not found')
    s = s.replace(helper_anchor, helper + helper_anchor, 1)

old = '''      let lastError = null;
      for (const userId of candidateUserIds) {
        try {
          const [config, sharing] = await Promise.all([getExtensionConfig(userId), getOrCreateSharingIdentity(userId)]);
          let bytes;
          if (request.ownerKeyEnvelope || request.recipientKeyEnvelope) {
            const postKeyBytes = request.recipientKeyEnvelope
              ? await unwrapRecipientEnvelope(request.recipientKeyEnvelope, sharing)
              : await unwrapOwnerEnvelope(request.ownerKeyEnvelope, config.walletPrivateKey);
            const postKey = await importPostKey(postKeyBytes);
            bytes = new Uint8Array(await crypto.subtle.decrypt(
              { name: "AES-GCM", iv: base64ToBytes(request.iv) },
              postKey,
              base64ToBytes(request.ciphertext)
            ));
          } else {
            bytes = await decryptBytes(request.ciphertext, request.iv, config.walletPrivateKey);
          }
          sendResponse({
            success: true,
            plaintext: request.mode === "bytes" ? "" : new TextDecoder().decode(bytes),
            data: request.mode === "bytes" ? bytesToBase64(bytes) : ""
          });
          return;
        } catch (err) {
          lastError = err;
        }
      }
      sendResponse({ success: false, error: lastError?.message || "Owner decryption failed" });
'''
new = '''      let lastError = null;
      for (const userId of candidateUserIds) {
        if (request.recipientKeyEnvelope) {
          try {
            const sharing = await getOrCreateSharingIdentity(userId);
            const postKeyBytes = await unwrapRecipientEnvelope(request.recipientKeyEnvelope, sharing);
            const postKey = await importPostKey(postKeyBytes);
            const bytes = new Uint8Array(await crypto.subtle.decrypt(
              { name: "AES-GCM", iv: base64ToBytes(request.iv) },
              postKey,
              base64ToBytes(request.ciphertext)
            ));
            sendResponse({
              success: true,
              plaintext: request.mode === "bytes" ? "" : new TextDecoder().decode(bytes),
              data: request.mode === "bytes" ? bytesToBase64(bytes) : ""
            });
            return;
          } catch (err) {
            lastError = err;
          }
          continue;
        }

        // Owner decryption must be read-only and backward compatible. A profile
        // can retain both an older native owner key and a newer custom owner key;
        // old envelopes must remain decryptable after identity/wallet migration.
        const ownerSecrets = await getStoredOwnerKeyCandidates(userId);
        for (const ownerSecret of ownerSecrets) {
          try {
            let bytes;
            if (request.ownerKeyEnvelope) {
              const postKeyBytes = await unwrapOwnerEnvelope(request.ownerKeyEnvelope, ownerSecret);
              const postKey = await importPostKey(postKeyBytes);
              bytes = new Uint8Array(await crypto.subtle.decrypt(
                { name: "AES-GCM", iv: base64ToBytes(request.iv) },
                postKey,
                base64ToBytes(request.ciphertext)
              ));
            } else {
              bytes = await decryptBytes(request.ciphertext, request.iv, ownerSecret);
            }
            sendResponse({
              success: true,
              plaintext: request.mode === "bytes" ? "" : new TextDecoder().decode(bytes),
              data: request.mode === "bytes" ? bytesToBase64(bytes) : ""
            });
            return;
          } catch (err) {
            lastError = err;
          }
        }
      }
      sendResponse({ success: false, error: lastError?.message || "No stored Chamber owner key could decrypt this backup" });
'''
if old not in s:
    raise SystemExit('decrypt block not found')
s = s.replace(old, new, 1)

old_grant = '''      let lastError = null;
      for (const userId of candidateUserIds) {
        try {
          const config = await getExtensionConfig(userId);
          const postKeyBytes = await unwrapOwnerEnvelope(request.ownerKeyEnvelope, config.walletPrivateKey);
          const envelope = await createRecipientEnvelope(postKeyBytes, request.recipientPublicKey, request.recipientKeyId);
          sendResponse({ success: true, recipientKeyEnvelope: envelope });
          return;
        } catch (err) {
          lastError = err;
        }
      }
      sendResponse({ success: false, error: lastError?.message || "Grant creation failed" });
'''
new_grant = '''      let lastError = null;
      for (const userId of candidateUserIds) {
        const ownerSecrets = await getStoredOwnerKeyCandidates(userId);
        for (const ownerSecret of ownerSecrets) {
          try {
            const postKeyBytes = await unwrapOwnerEnvelope(request.ownerKeyEnvelope, ownerSecret);
            const envelope = await createRecipientEnvelope(postKeyBytes, request.recipientPublicKey, request.recipientKeyId);
            sendResponse({ success: true, recipientKeyEnvelope: envelope });
            return;
          } catch (err) {
            lastError = err;
          }
        }
      }
      sendResponse({ success: false, error: lastError?.message || "No stored Chamber owner key could create this grant" });
'''
if old_grant not in s:
    raise SystemExit('grant block not found')
s = s.replace(old_grant, new_grant, 1)

bg.write_text(s, encoding='utf-8')

m = json.loads(manifest.read_text(encoding='utf-8'))
before = m.get('version')
if before not in ('1.0.61', '1.0.62'):
    raise SystemExit(f'unexpected extension version: {before}')
m['version'] = '1.0.62'
manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print(f'version_before={before}')
print('version_after=1.0.62')
print('owner_key_fallback_helper=', 'getStoredOwnerKeyCandidates' in s)
print('decrypt_uses_stored_candidates=', 'const ownerSecrets = await getStoredOwnerKeyCandidates(userId);' in s)
print('decrypt_no_config_generation=', 'No stored Chamber owner key could decrypt this backup' in s)
