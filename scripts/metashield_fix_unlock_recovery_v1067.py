#!/usr/bin/env python3
from pathlib import Path
import json, sys

root=Path(sys.argv[1] if len(sys.argv)>1 else '/home/ubuntu/metashield-protocol')
page=root/'web-feed/app/[wallet_address]/[platform]/page.tsx'
manifest=root/'extension/manifest.json'
s=page.read_text()
m=json.loads(manifest.read_text())
old=m.get('version')
if old not in ('1.0.66','1.0.67'):
    raise SystemExit(f'unexpected version {old}')

# Make existing A+B recovery callable as a real success/failure primitive.
if 'setRecoveryStatus(ft("repairSuccess"));\n      return true;' not in s:
    s=s.replace('''      await requestExtensionRecovery("RESTORE_RECOVERY_AB", { shareB: verifyData.authentication.shareB });
      setRecoveryStatus(ft("repairSuccess"));
    } catch (error: any) {
      setRecoveryStatus(ft("repairFailed", { error: error.message }));
    } finally {''','''      await requestExtensionRecovery("RESTORE_RECOVERY_AB", { shareB: verifyData.authentication.shareB });
      setRecoveryStatus(ft("repairSuccess"));
      return true;
    } catch (error: any) {
      setRecoveryStatus(ft("repairFailed", { error: error.message }));
      return false;
    } finally {''',1)

helper='''  const isOwnerRecoveryDecryptError = (error: unknown) => {
    const message = error instanceof Error ? error.message : String(error || "");
    return /Owner decryption failed|No stored Chamber owner key could decrypt/i.test(message);
  };

  const decryptPostDataWithOwnerRecovery = async (
    post: PostItem,
    onTextDecrypted: (text: string) => void,
    onMediaProgress: (completed: number, total: number, failed: number) => void,
    recoveryGate: { attempted: boolean }
  ) => {
    try {
      return await decryptPostData(post, onTextDecrypted, onMediaProgress);
    } catch (error) {
      if (!recoveryGate.attempted && isPostOwner(post) && isOwnerRecoveryDecryptError(error)) {
        recoveryGate.attempted = true;
        const restored = await restoreWithLocalAAndVaultB();
        if (restored) return await decryptPostData(post, onTextDecrypted, onMediaProgress);
      }
      throw error;
    }
  };

'''
anchor='  const handleDecryptPost = async (post: PostItem, index: number) => {'
if 'const decryptPostDataWithOwnerRecovery = async (' not in s:
    if anchor not in s: raise SystemExit('handleDecryptPost anchor missing')
    s=s.replace(anchor,helper+anchor,1)

# Single-post unlock: one recovery ceremony max per click.
if 'const recoveryGate = { attempted: false };\n    setPosts' not in s:
    s=s.replace('''  const handleDecryptPost = async (post: PostItem, index: number) => {
    setPosts''','''  const handleDecryptPost = async (post: PostItem, index: number) => {
    const recoveryGate = { attempted: false };
    setPosts''',1)
s=s.replace('''const { decryptedText, decryptedMedia, mediaFailed, mediaTotal } = await decryptPostData(
        post,''','''const { decryptedText, decryptedMedia, mediaFailed, mediaTotal } = await decryptPostDataWithOwnerRecovery(
        post,''',1)
# Add gate as fourth argument after media progress callback in single handler.
needle='''          : item))
      );

      setPosts((current) => current.map((item) => item.txId === post.txId'''
repl='''          : item)),
        recoveryGate
      );

      setPosts((current) => current.map((item) => item.txId === post.txId'''
if needle in s: s=s.replace(needle,repl,1)

# Bulk unlock shares one gate, so a failed Passkey does not prompt once per post.
if 'const recoveryGate = { attempted: false };\n    let failures = 0;' not in s:
    s=s.replace('''    setIsDecryptingAll(true);
    let failures = 0;''','''    setIsDecryptingAll(true);
    const recoveryGate = { attempted: false };
    let failures = 0;''',1)
s=s.replace('''const result = await decryptPostData(
          target,''','''const result = await decryptPostDataWithOwnerRecovery(
          target,''',1)
needle2='''            : item))
        );
        mediaFailures += result.mediaFailed;'''
repl2='''            : item)),
          recoveryGate
        );
        mediaFailures += result.mediaFailed;'''
if needle2 in s: s=s.replace(needle2,repl2,1)

required=[
 'return true;\n    } catch (error: any) {\n      setRecoveryStatus(ft("repairFailed"',
 'const decryptPostDataWithOwnerRecovery = async (',
 'isOwnerRecoveryDecryptError(error)',
 'await restoreWithLocalAAndVaultB()',
 'await decryptPostDataWithOwnerRecovery(\n        post,',
 'await decryptPostDataWithOwnerRecovery(\n          target,',
]
for q in required:
    if q not in s: raise SystemExit('missing v1.0.67 contract: '+q[:80])
page.write_text(s)
m['version']='1.0.67'
manifest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
print('unlock_recovery_patch=PASS')
print('version_before='+str(old))
print('version_after=1.0.67')
