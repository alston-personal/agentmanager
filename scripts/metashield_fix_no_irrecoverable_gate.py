from pathlib import Path
import json

ROOT = Path('/home/ubuntu/metashield-protocol')
bg_path = ROOT / 'extension/background.js'
side_path = ROOT / 'extension/sidepanel.js'
i18n_path = ROOT / 'extension/i18n.js'
server_path = ROOT / 'api/server.js'
manifest_path = ROOT / 'extension/manifest.json'

bg = bg_path.read_text()
side = side_path.read_text()
i18n = i18n_path.read_text()
server = server_path.read_text()
manifest = json.loads(manifest_path.read_text())

# --- background: authoritative recovery coverage helper ---
anchor = '''async function recoveryVaultStatus(userId) {
  const prefix = `user_${userId || "default"}_`;
'''
if anchor not in bg:
    raise SystemExit('background recoveryVaultStatus anchor missing')

helper = '''async function recoveryCoverageForOwnerKey(userId, ownerAddress) {
  const prefix = `user_${userId || "default"}_`;
  const keys = [
    prefix + "recoveryLocalShare",
    prefix + "recoveryVaultAccountId",
    prefix + "recoveryExportConfirmedVersion",
  ];
  const data = await chrome.storage.local.get(keys);
  const localShare = data[prefix + "recoveryLocalShare"];
  const expectedOwner = String(ownerAddress || "").toLowerCase();
  const recoveredOwner = String(localShare?.ownerAddress || "").toLowerCase();
  const setId = String(localShare?.setId || "");
  const accountId = String(data[prefix + "recoveryVaultAccountId"] || "");
  const confirmed = data[prefix + "recoveryExportConfirmedVersion"] === "2-of-3-vault-v1";
  const hasLocalA = Number(localShare?.share?.x) === 1;
  const ownerMatches = Boolean(expectedOwner && recoveredOwner && expectedOwner === recoveredOwner);
  const verified = Boolean(confirmed && hasLocalA && setId && accountId && ownerMatches);
  return {
    state: verified ? "RECOVERY_COVERED" : "RECOVERY_INCOMPLETE",
    verified,
    setId,
    accountId,
    ownerKeyId: expectedOwner,
    ownerMatches,
  };
}

'''
if 'async function recoveryCoverageForOwnerKey' not in bg:
    bg = bg.replace(anchor, helper + anchor, 1)

# Gate before post/media ciphertext generation/upload.
old = '''  const config = await getExtensionConfig(fbUserId);
  const storageNetwork = await getStorageNetworkPolicy();
  const postKeyBytes = crypto.getRandomValues(new Uint8Array(32));
  const ownerKeyEnvelope = await createOwnerEnvelope(postKeyBytes, config.walletPrivateKey);
'''
new = '''  const config = await getExtensionConfig(fbUserId);
  const recoveryCoverage = await recoveryCoverageForOwnerKey(userId, config.boundWalletAddress);
  if (!recoveryCoverage.verified) {
    const error = new Error(t("backup.recoveryRequiredBeforeBackup"));
    error.code = "RECOVERY_COVERAGE_REQUIRED";
    error.details = {
      recoveryState: recoveryCoverage.state,
      ownerMatches: recoveryCoverage.ownerMatches,
      hasRecoverySet: Boolean(recoveryCoverage.setId),
    };
    throw error;
  }
  const storageNetwork = await getStorageNetworkPolicy();
  const postKeyBytes = crypto.getRandomValues(new Uint8Array(32));
  const ownerKeyEnvelope = await createOwnerEnvelope(postKeyBytes, config.walletPrivateKey);
'''
if old not in bg:
    raise SystemExit('background backup config block missing')
bg = bg.replace(old, new, 1)

# Add non-secret lineage to API payload.
old = '''    encryptionVersion: "post-key-v2",
    keyEnvelope: ownerKeyEnvelope,
    accessCapabilityHash: config.accessCapabilityHash,
'''
new = '''    encryptionVersion: "post-key-v2",
    keyEnvelope: ownerKeyEnvelope,
    ownerKeyId: recoveryCoverage.ownerKeyId,
    recoverySetId: recoveryCoverage.setId,
    recoveryCoverage: "verified",
    accessCapabilityHash: config.accessCapabilityHash,
'''
if old not in bg:
    raise SystemExit('background api payload encryption block missing')
bg = bg.replace(old, new, 1)

# --- sidepanel: proactive UX gate, no fake success path ---
old = '''    const recoveryState = await chrome.storage.local.get([prefix + "recoveryExportedAt", prefix + "recoveryLocalShare", prefix + "recoveryExportConfirmedVersion"]);
    const recoveryMissing = !recoveryState[prefix + "recoveryExportedAt"] || !recoveryState[prefix + "recoveryLocalShare"] || recoveryState[prefix + "recoveryExportConfirmedVersion"] !== "2-of-3-vault-v1";
'''
new = '''    const recoveryState = await chrome.storage.local.get([prefix + "recoveryExportedAt", prefix + "recoveryLocalShare", prefix + "recoveryVaultAccountId", prefix + "recoveryExportConfirmedVersion", prefix + "customWalletAddress", prefix + "nativeWalletAddress"]);
    const activeWallet = String(activeProfile?.walletAddress || recoveryState[prefix + "customWalletAddress"] || recoveryState[prefix + "nativeWalletAddress"] || "").toLowerCase();
    const recoveryOwner = String(recoveryState[prefix + "recoveryLocalShare"]?.ownerAddress || "").toLowerCase();
    const recoveryMissing = !recoveryState[prefix + "recoveryExportedAt"] ||
      !recoveryState[prefix + "recoveryLocalShare"] ||
      !recoveryState[prefix + "recoveryVaultAccountId"] ||
      recoveryState[prefix + "recoveryExportConfirmedVersion"] !== "2-of-3-vault-v1" ||
      !activeWallet || !recoveryOwner || activeWallet !== recoveryOwner;
    if (recoveryMissing) {
      setStatus(t("backup.recoveryRequiredBeforeBackup"), true);
      const recoveryError = new Error(t("backup.recoveryRequiredBeforeBackup"));
      recoveryError.code = "RECOVERY_COVERAGE_REQUIRED";
      throw recoveryError;
    }
'''
if old not in side:
    raise SystemExit('sidepanel recoveryMissing block missing')
side = side.replace(old, new, 1)

# Once fail-closed, success is always recovery-covered. Remove old pending success branches/notices.
side = side.replace('''    setStatus(recoveryMissing
      ? t("backup.successRecoveryPending")
      : t("backup.success"));
''', '''    setStatus(t("backup.success"));
''', 1)

# Remove legacy recovery notice block if present.
start_marker = '''    if (recoveryMissing) {
      const recoveryNotice = document.createElement("div");
'''
if start_marker in side:
    start = side.index(start_marker)
    # Block ends immediately before transaction text in current tree.
    end_marker = '''    tx.textContent = t("backup.transactionCreated", { tx: result.txId.slice(0, 12) });'''
    end = side.index(end_marker, start)
    side = side[:start] + side[end:]

# --- i18n message ---
if '"backup.recoveryRequiredBeforeBackup"' not in i18n:
    # Add to both known locale dictionaries near an existing backup key when possible.
    zh_anchor = '"backup.success":'
    en_anchor = '"backup.success":'
    # We avoid fragile locale detection by inserting after each first two occurrences.
    msg_zh = '"backup.recoveryRequiredBeforeBackup": "為避免產生未來可能無法解密的備份，請先完成目前 Chamber 金鑰的復原保護，再重新備份。",\n    '
    msg_en = '"backup.recoveryRequiredBeforeBackup": "To prevent an unreadable backup, finish recovery protection for the current Chamber owner key before backing up.",\n    '
    pos1 = i18n.find(zh_anchor)
    if pos1 < 0:
        raise SystemExit('i18n backup.success anchor missing')
    line_end = i18n.find('\n', pos1)
    i18n = i18n[:line_end+1] + '    ' + msg_zh + i18n[line_end+1:]
    pos2 = i18n.find(en_anchor, line_end + len(msg_zh) + 1)
    if pos2 >= 0:
        line_end2 = i18n.find('\n', pos2)
        i18n = i18n[:line_end2+1] + '    ' + msg_en + i18n[line_end2+1:]

# --- API: require and persist G9 lineage ---
old = '''    const { extensionVersion, fbUserId, content, platform, mediaUrls, mediaItems, mediaMeta, isEncrypted, encryptionVersion, keyEnvelope, accessCapabilityHash, privacy, timestamp, publishedAt, authorName, authorUrl, isDebug, network: requestedNetwork, sourceUrl, boundWallet, identityAlias, identityActorType, identityActorId, identityDisplayName } = req.body;
'''
new = '''    const { extensionVersion, fbUserId, content, platform, mediaUrls, mediaItems, mediaMeta, isEncrypted, encryptionVersion, keyEnvelope, ownerKeyId, recoverySetId, recoveryCoverage, accessCapabilityHash, privacy, timestamp, publishedAt, authorName, authorUrl, isDebug, network: requestedNetwork, sourceUrl, boundWallet, identityAlias, identityActorType, identityActorId, identityDisplayName } = req.body;
'''
if old not in server:
    raise SystemExit('server backup destructure block missing')
server = server.replace(old, new, 1)

validation_anchor = '''    if (!content || content.trim().length === 0) {
      return res.status(400).json({ error: "content is required" });
    }

'''
validation = '''    if (encryptionVersion === "post-key-v2") {
      const normalizedOwnerKeyId = String(ownerKeyId || "").toLowerCase();
      const normalizedBoundWallet = String(boundWallet || "").toLowerCase();
      if (recoveryCoverage !== "verified" || !recoverySetId || !normalizedOwnerKeyId || (normalizedBoundWallet && normalizedOwnerKeyId !== normalizedBoundWallet)) {
        return res.status(409).json({
          error: "Recovery coverage is required before preservation",
          code: "RECOVERY_COVERAGE_REQUIRED"
        });
      }
    }

'''
if validation not in server:
    if validation_anchor not in server:
        raise SystemExit('server content validation anchor missing')
    server = server.replace(validation_anchor, validation_anchor + validation, 1)

old = '''      key_envelope: keyEnvelope || null,
      media: {
'''
new = '''      key_envelope: keyEnvelope || null,
      owner_key_id: ownerKeyId || null,
      recovery_set_id: recoverySetId || null,
      recovery_coverage: recoveryCoverage || null,
      media: {
'''
if old not in server:
    raise SystemExit('server payload key envelope block missing')
server = server.replace(old, new, 1)

old = '''        { name: "Logical-Source-ID", value: logicalSourceId },
      ];
'''
new = '''        { name: "Logical-Source-ID", value: logicalSourceId },
        { name: "Recovery-Coverage", value: String(recoveryCoverage || "none") },
        { name: "Recovery-Set-ID", value: String(recoverySetId || "") },
        { name: "Owner-Key-ID", value: String(ownerKeyId || "") },
      ];
'''
if old not in server:
    raise SystemExit('server tags anchor missing')
server = server.replace(old, new, 1)

old = '''      quota: quotaResult || null,
    };
'''
new = '''      quota: quotaResult || null,
      ownerKeyId: ownerKeyId || null,
      recoverySetId: recoverySetId || null,
      recoveryCoverage: recoveryCoverage || null,
    };
'''
if old not in server:
    raise SystemExit('server response quota anchor missing')
server = server.replace(old, new, 1)

old = '''      logicalSourceId,
      isDebug: isDebugMode,
'''
new = '''      logicalSourceId,
      ownerKeyId: ownerKeyId || null,
      recoverySetId: recoverySetId || null,
      recoveryCoverage: recoveryCoverage || null,
      isDebug: isDebugMode,
'''
if old not in server:
    raise SystemExit('server receipt logicalSourceId anchor missing')
server = server.replace(old, new, 1)

# Tester-visible version bump.
if manifest.get('version') != '1.0.63':
    raise SystemExit(f'unexpected manifest version {manifest.get("version")}; expected 1.0.63')
manifest['version'] = '1.0.64'

bg_path.write_text(bg)
side_path.write_text(side)
i18n_path.write_text(i18n)
server_path.write_text(server)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')

print('version_after=1.0.64')
print('background_gate=', 'RECOVERY_COVERAGE_REQUIRED' in bg and 'recoveryCoverageForOwnerKey' in bg)
print('sidepanel_fail_closed=', 'recoveryError.code = "RECOVERY_COVERAGE_REQUIRED"' in side)
print('server_gate=', 'Recovery coverage is required before preservation' in server)
print('server_lineage=', all(x in server for x in ['owner_key_id', 'recovery_set_id', 'recovery_coverage']))
