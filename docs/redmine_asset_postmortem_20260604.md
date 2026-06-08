# Redmine Asset Audit Notes

Date: 2026-06-04

## What we verified

- Live Redmine asset traffic for `/system/rich/...` is served from `/home/dqa03/system/redmine_app/redmine_system/...`.
- The `attachments` table currently has `427` files whose `disk_filename` no longer exists under `/home/dqa03/system/redmine_app/files`.
- The `rich_rich_files` table initially appeared to have more misses, but one case was a filename-normalization mismatch (`:` stored as `_`) rather than true data loss.
- After correcting that one rich filename locally, the remaining `rich_rich_files` gap is `665` files.
- A sampled live request for `https://dqa02.vivotek.tw/system/rich/.../Backup檔案-2.png` returned `HTTP 200`.
- The local backup tree `redmine_system/bkp/rich_files/...` did not contain any of the remaining missing rich files.
- The local time-machine trees checked on this host also did not contain sampled missing files.

## Most likely explanation

There are two different situations mixed together:

- A routing/testing mismatch did exist earlier: `dqa03.vivotek.tw` does not serve Redmine assets, while `dqa02.vivotek.tw` does.
- At least one rich asset failure was caused by filename normalization drift, not missing content. The file existed, but the stored filename used `:` while the filesystem copy used `_`.
- The remaining `665` rich files and `427` standard attachments appear to be genuine host-local gaps, not just URL or encoding confusion.

## Why this can happen

- The deployment keeps multiple Redmine-related trees: live, backup, time-machine, restore, and snapshot archives.
- Asset serving depends on nginx alias rules plus Redmine plugin conventions, so a path can look broken even when the file still exists.
- Filename normalization rules were not being audited, so a path-level mismatch could survive unnoticed.
- There is no lightweight scheduled audit proving that DB references and filesystem contents still match after restore, migration, or manual copy work.

## Prevention

- Run `scripts/audit_redmine_assets.py` after restore, migration, or storage changes.
- Save the JSON and CSV outputs as part of Redmine maintenance evidence.
- Add a scheduled read-only audit that alerts only when missing counts are non-zero.
- Test asset URLs with the real production host header `dqa02.vivotek.tw` during validation.
- Keep backup restore actions additive: copy only missing files, never overwrite existing live assets blindly.
- Add a second audit rule for rich assets that flags filename normalization mismatches in directories that already contain a sibling file.
- Keep an off-host archive of both `/files` and `/redmine_system/rich` that is searchable by exact filename before snapshot pruning.

## Recovery approach

The new audit script supports a safe recovery mode:

```bash
python3 scripts/audit_redmine_assets.py --restore
```

That mode only copies back missing `rich_rich_files` originals when the same file exists in the local `bkp` tree, or when the same directory already contains a safe sibling source that can be duplicated under the expected name. It does not restart containers or overwrite existing files.
