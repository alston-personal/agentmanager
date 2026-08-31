#!/usr/bin/env python3
from pathlib import Path
import json, sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/metashield-protocol')
ext = root / 'extension'
manifest_path = ext / 'manifest.json'
content_path = ext / 'content.js'
page_path = root / 'web-feed' / 'app' / '[wallet_address]' / '[platform]' / 'page.tsx'
test_dir = ext / 'tests'
test_path = test_dir / 'passkey-recovery-bridge-contract.test.mjs'

manifest = json.loads(manifest_path.read_text())
version = manifest.get('version')
if version not in ('1.0.65', '1.0.66'):
    raise SystemExit(f'unexpected extension version: {version!r}; expected 1.0.65 or idempotent 1.0.66')

content = content_path.read_text()
page = page_path.read_text()
required_content = [
    'NATIVE_PASSKEY_REGISTER: createNativePasskey',
    'NATIVE_PASSKEY_AUTHENTICATE: authenticateNativePasskey',
    'event.data.source === "echo-portal"',
    'const responseType = `${event.data.type}_RESPONSE`',
    'credential\n        }, "https://studio.milkcat.org")',
]
for needle in required_content:
    if needle not in content:
        raise SystemExit(f'missing existing Passkey bridge contract in content.js: {needle}')
required_page = [
    'requestExtensionRecovery<any>("NATIVE_PASSKEY_REGISTER", { optionsJSON })',
    'requestExtensionRecovery<any>("NATIVE_PASSKEY_AUTHENTICATE", { optionsJSON })',
    'type.startsWith("NATIVE_PASSKEY_") ? 70_000 : 10_000',
]
for needle in required_page:
    if needle not in page:
        raise SystemExit(f'missing Echo Passkey request contract: {needle}')

marker = '  // v1.0.66 contract: Echo system-Passkey requests are executed by the extension content bridge.\n'
anchor = '  const nativePasskeyActions = {\n'
if marker not in content:
    if anchor not in content:
        raise SystemExit('nativePasskeyActions insertion anchor not found')
    content = content.replace(anchor, marker + anchor, 1)
    content_path.write_text(content)

manifest['version'] = '1.0.66'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')

test_dir.mkdir(exist_ok=True)
test_path.write_text(r'''import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const ext = path.resolve(here, '..');
const root = path.resolve(ext, '..');
const content = fs.readFileSync(path.join(ext, 'content.js'), 'utf8');
const manifest = JSON.parse(fs.readFileSync(path.join(ext, 'manifest.json'), 'utf8'));
const page = fs.readFileSync(path.join(root, 'web-feed', 'app', '[wallet_address]', '[platform]', 'page.tsx'), 'utf8');

assert.equal(manifest.version, '1.0.66');
assert.match(content, /NATIVE_PASSKEY_REGISTER:\s*createNativePasskey/);
assert.match(content, /NATIVE_PASSKEY_AUTHENTICATE:\s*authenticateNativePasskey/);
assert.match(content, /event\.data\.source === ["']echo-portal["']/);
assert.match(content, /const responseType = `\$\{event\.data\.type\}_RESPONSE`/);
assert.match(content, /requestId:\s*event\.data\.requestId \|\| ["']["']/);
assert.match(content, /success:\s*true[\s\S]{0,120}credential/);
assert.match(content, /success:\s*false[\s\S]{0,160}error:/);
assert.match(content, /["']https:\/\/studio\.milkcat\.org["']/);
assert.match(page, /requestExtensionRecovery<any>\(["']NATIVE_PASSKEY_REGISTER["'],\s*\{\s*optionsJSON\s*\}\)/);
assert.match(page, /requestExtensionRecovery<any>\(["']NATIVE_PASSKEY_AUTHENTICATE["'],\s*\{\s*optionsJSON\s*\}\)/);
assert.match(page, /type\.startsWith\(["']NATIVE_PASSKEY_["']\) \? 70_000 : 10_000/);
assert.match(page, /event\.data\?\.requestId !== requestId/);
console.log('passkey_recovery_bridge_contract=PASS');
''')

print('passkey_bridge_patch=PASS')
print('version_before=' + version)
print('version_after=1.0.66')
print('content_bridge=present')
print('echo_contract=present')
print('contract_test=' + str(test_path))
