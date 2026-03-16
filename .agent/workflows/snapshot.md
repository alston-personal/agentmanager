---
description: Create a dated snapshot summary from the current memory layer
---

# /snapshot - Create Memory Snapshot

## Steps

1. **Generate snapshot**
   ```bash
   python3 scripts/create_snapshot.py
   ```

2. **Confirm output path**
   Tell the user which snapshot file was created.

3. **Optional follow-up**
   Suggest committing the data repo if they want a durable checkpoint.
