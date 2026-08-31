from pathlib import Path
import json

root = Path('/home/ubuntu/metashield-protocol')
bg = root / 'extension/background.js'
manifest = root / 'extension/manifest.json'
s = bg.read_text(encoding='utf-8')

old_helper = '''async function getStoredOwnerKeyCandidates(userId) {
  const prefix = `user_${userId || "default"}_`;
  const keys = [prefix + "customWalletPrivateKey", prefix + "nativeWalletPrivateKey"];
  const stored = await chrome.storage.local.get(keys);
  return [...new Set(keys.map((key) => stored[key]).filter(Boolean))];
}
'''
new_helper = '''async function getStoredOwnerKeyCandidates(userId) {
  const prefix = `user_${userId || "default"}_`;
  const keys = [prefix + "customWalletPrivateKey", prefix + "nativeWalletPrivateKey", prefix + "legacyOwnerKeys"];
  const stored = await chrome.storage.local.get(keys);
  const direct = keys.slice(0, 2).map((key) => stored[key]).filter(Boolean);
  const legacy = Array.isArray(stored[prefix + "legacyOwnerKeys"])
    ? stored[prefix + "legacyOwnerKeys"].map((entry) => entry?.ownerSecret).filter(Boolean)
    : [];
  return [...new Set([...direct, ...legacy])];
}

async function shouldPreserveCurrentOwnerKey(userId, recoveredOwnerAddress) {
  const prefix = `user_${userId || "default"}_`;
  const keys = [
    prefix + "customWalletAddress", prefix + "customWalletPrivateKey",
    prefix + "nativeWalletAddress", prefix + "nativeWalletPrivateKey"
  ];
  const stored = await chrome.storage.local.get(keys);
  const currentAddress = (stored[prefix + "customWalletPrivateKey"] && stored[prefix + "customWalletAddress"])
    ? stored[prefix + "customWalletAddress"]
    : ((stored[prefix + "nativeWalletPrivateKey"] && stored[prefix + "nativeWalletAddress"])
      ? stored[prefix + "nativeWalletAddress"] : "");
  return Boolean(currentAddress && recoveredOwnerAddress && String(currentAddress).toLowerCase() !== String(recoveredOwnerAddress).toLowerCase());
}

async function storeLegacyOwnerKey(userId, shareB, ownerSecret) {
  const prefix = `user_${userId || "default"}_`;
  const key = prefix + "legacyOwnerKeys";
  const stored = await chrome.storage.local.get([key]);
  const existing = Array.isArray(stored[key]) ? stored[key] : [];
  const ownerAddress = String(shareB?.ownerAddress || "").toLowerCase();
  const next = existing.filter((entry) => entry?.ownerSecret !== ownerSecret && String(entry?.ownerAddress || "").toLowerCase() !== ownerAddress);
  next.unshift({
    ownerAddress,
    ownerSecret,
    setId: String(shareB?.setId || ""),
    keyTier: String(shareB?.keyTier || "legacy"),
    recoveredAt: new Date().toISOString(),
  });
  await chrome.storage.local.set({ [key]: next.slice(0, 8) });
  return { ownerAddress, setId: String(shareB?.setId || "") };
}
'''
if old_helper not in s:
    raise SystemExit('v1.0.62 owner-key helper block not found')
s = s.replace(old_helper, new_helper, 1)

needle1 = '''  const prefix = `user_${ownerUserId}_`;
  const update = {
    [prefix + (shareB.keyTier === "custom" ? "customWalletAddress" : "nativeWalletAddress")]: shareB.ownerAddress,
    [prefix + (shareB.keyTier === "custom" ? "customWalletPrivateKey" : "nativeWalletPrivateKey")]: ownerSecret,
    lastFbUserId: ownerUserId,
  };
'''
replacement1 = '''  const prefix = `user_${ownerUserId}_`;
  if (await shouldPreserveCurrentOwnerKey(ownerUserId, shareB.ownerAddress)) {
    const legacy = await storeLegacyOwnerKey(ownerUserId, shareB, ownerSecret);
    return {
      legacy: true,
      preservedCurrentOwner: true,
      ownerAddress: legacy.ownerAddress,
      setId: decoded.setId,
      accountId: decoded.accountId || "",
      needsVaultRotation: Boolean(suppliedShareB),
    };
  }
  const update = {
    [prefix + (shareB.keyTier === "custom" ? "customWalletAddress" : "nativeWalletAddress")]: shareB.ownerAddress,
    [prefix + (shareB.keyTier === "custom" ? "customWalletPrivateKey" : "nativeWalletPrivateKey")]: ownerSecret,
    lastFbUserId: ownerUserId,
  };
'''
if needle1 not in s:
    raise SystemExit('restoreFromRecoveryVault write block not found')
s = s.replace(needle1, replacement1, 1)

needle2 = '''  const update = {
    [prefix + (shareB.keyTier === "custom" ? "customWalletAddress" : "nativeWalletAddress")]: shareB.ownerAddress,
    [prefix + (shareB.keyTier === "custom" ? "customWalletPrivateKey" : "nativeWalletPrivateKey")]: ownerSecret,
    lastFbUserId: ownerUserId,
  };
  if (shareB.identityAlias) update[prefix + "identityAlias"] = shareB.identityAlias;
  await chrome.storage.local.set(update);
  await restoreSharingIdentityFromRecovery(shareB.sharingIdentityEnvelope, ownerSecret, prefix);
  return { accountId: data[prefix + "recoveryVaultAccountId"] || "", setId: shareB.setId };
'''
replacement2 = '''  if (await shouldPreserveCurrentOwnerKey(ownerUserId, shareB.ownerAddress)) {
    const legacy = await storeLegacyOwnerKey(ownerUserId, shareB, ownerSecret);
    return {
      legacy: true,
      preservedCurrentOwner: true,
      ownerAddress: legacy.ownerAddress,
      accountId: data[prefix + "recoveryVaultAccountId"] || "",
      setId: shareB.setId,
    };
  }
  const update = {
    [prefix + (shareB.keyTier === "custom" ? "customWalletAddress" : "nativeWalletAddress")]: shareB.ownerAddress,
    [prefix + (shareB.keyTier === "custom" ? "customWalletPrivateKey" : "nativeWalletPrivateKey")]: ownerSecret,
    lastFbUserId: ownerUserId,
  };
  if (shareB.identityAlias) update[prefix + "identityAlias"] = shareB.identityAlias;
  await chrome.storage.local.set(update);
  await restoreSharingIdentityFromRecovery(shareB.sharingIdentityEnvelope, ownerSecret, prefix);
  return { accountId: data[prefix + "recoveryVaultAccountId"] || "", setId: shareB.setId };
'''
# This exact block should now occur only in restoreFromLocalAAndVaultB because first was already replaced.
if needle2 not in s:
    raise SystemExit('restoreFromLocalAAndVaultB write block not found')
s = s.replace(needle2, replacement2, 1)

bg.write_text(s, encoding='utf-8')

m = json.loads(manifest.read_text(encoding='utf-8'))
before = m.get('version')
if before != '1.0.62':
    raise SystemExit(f'expected manifest 1.0.62, got {before!r}')
m['version'] = '1.0.63'
manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print('version_before=', before)
print('version_after=', m['version'])
print('legacy_keyring_helper=', 'async function storeLegacyOwnerKey' in s)
print('decrypt_reads_legacy=', 'legacyOwnerKeys' in s and 'entry?.ownerSecret' in s)
print('restore_conflict_guard_count=', s.count('shouldPreserveCurrentOwnerKey(ownerUserId, shareB.ownerAddress)'))
