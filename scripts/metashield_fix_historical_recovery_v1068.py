#!/usr/bin/env python3
from pathlib import Path
import json, sys

root=Path(sys.argv[1] if len(sys.argv)>1 else '/home/ubuntu/metashield-protocol')
bg=root/'extension/background.js'; mf=root/'extension/manifest.json'; tests=root/'extension/tests'; test=tests/'historical-recovery-contract.test.mjs'
s=bg.read_text()
old='''  const ownerUserId = String(shareB.ownerUserId || shareB.facebookUserId || "");\n  if (currentUserId && currentUserId !== "default" && ownerUserId !== String(currentUserId)) {\n    throw new Error(t("crypto.accountMismatch"));\n  }\n  const ownerSecret = ChamberSecretSharing.combine2of3(recoveryShares);'''
new='''  const ownerUserId = String(shareB.ownerUserId || shareB.facebookUserId || "");\n  // v1.0.68: B+C disaster recovery is authoritative for the historical owner\n  // generation selected by Recovery Code C's accountId. The active browser\n  // profile may legitimately be a newer generation and must not veto restore.\n  // Security remains fail-closed on Vault Passkey authentication (server),\n  // C/B setId equality (above), and the owner recovery checksum (below).\n  const historicalRecovery = Boolean(suppliedShareB && decoded.accountId && decoded.setId);\n  if (!historicalRecovery && currentUserId && currentUserId !== "default" && ownerUserId !== String(currentUserId)) {\n    throw new Error(t("crypto.accountMismatch"));\n  }\n  const ownerSecret = ChamberSecretSharing.combine2of3(recoveryShares);'''
if old not in s:
    if 'const historicalRecovery = Boolean(suppliedShareB && decoded.accountId && decoded.setId);' not in s:
        raise SystemExit('account mismatch guard anchor not found')
else:
    s=s.replace(old,new,1); bg.write_text(s)
m=json.loads(mf.read_text()); before=m.get('version')
if before not in ('1.0.67','1.0.68'): raise SystemExit(f'unexpected version {before}')
m['version']='1.0.68'; mf.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
tests.mkdir(exist_ok=True)
test.write_text(r'''import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const ext=path.resolve(here,'..');
const bg=fs.readFileSync(path.join(ext,'background.js'),'utf8');
const mf=JSON.parse(fs.readFileSync(path.join(ext,'manifest.json'),'utf8'));
assert.equal(mf.version,'1.0.68');
assert.match(bg,/decoded\.setId && decoded\.setId !== shareB\.setId[^\n]*crypto\.shareSetMismatch/);
assert.match(bg,/const historicalRecovery = Boolean\(suppliedShareB && decoded\.accountId && decoded\.setId\)/);
assert.match(bg,/if \(!historicalRecovery && currentUserId && currentUserId !== "default" && ownerUserId !== String\(currentUserId\)\)/);
assert.match(bg,/recoveryChecksum\(ownerUserId, shareB\.ownerAddress, ownerSecret\) !== shareB\.checksum/);
assert.match(bg,/shouldPreserveCurrentOwnerKey\(ownerUserId, shareB\.ownerAddress\)/);
assert.match(bg,/storeLegacyOwnerKey\(ownerUserId, shareB, ownerSecret\)/);
console.log('historical_recovery_contract=PASS');
''')
print(f'version_before={before}\nversion_after=1.0.68\nhistorical_recovery_patch=PASS')
