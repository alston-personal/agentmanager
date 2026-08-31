from pathlib import Path

p = Path('/home/ubuntu/metashield-protocol/web-feed/app/components/RealLeopardCatCard.tsx')
s = p.read_text(encoding='utf-8')

needle = '''  const mediaUrls = post.payload.is_encrypted ? (post.decryptedMedia || []) : storedMediaUrls;
  const platform = post.payload.platform || "threads";
'''
replacement = '''  const mediaUrls = post.payload.is_encrypted ? (post.decryptedMedia || []) : storedMediaUrls;
  const platform = post.payload.platform || "threads";
  const isUnlocked = !post.payload.is_encrypted || typeof post.decryptedContent === "string";
'''
if needle not in s:
    raise SystemExit('expected media/platform block not found')
s = s.replace(needle, replacement, 1)

old = '''                  {post.payload.is_encrypted ? "🔒 " + ft("guardedByLeopard") : (post.payload.content?.slice(0, 32) || ft("leopardTouchBelly"))}
'''
new = '''                  {post.payload.is_encrypted
                    ? (isUnlocked ? "🔓 " + ft("decrypted") : "🔒 " + ft("guardedByLeopard"))
                    : (post.payload.content?.slice(0, 32) || ft("leopardTouchBelly"))}
'''
if old not in s:
    raise SystemExit('expected collapsed lock teaser not found')
s = s.replace(old, new, 1)

old = '''                  {post.payload.is_encrypted ? "ENCRYPTED" : "PUBLIC"}
'''
new = '''                  {post.payload.is_encrypted ? (isUnlocked ? "UNLOCKED" : "ENCRYPTED") : "PUBLIC"}
'''
if old not in s:
    raise SystemExit('expected encryption status badge not found')
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('echo_unlock_state_patch=PASS')
print('has_isUnlocked=', 'const isUnlocked =' in s)
print('collapsed_uses_isUnlocked=', 'isUnlocked ? "🔓 " + ft("decrypted")' in s)
print('badge_uses_isUnlocked=', 'isUnlocked ? "UNLOCKED" : "ENCRYPTED"' in s)
