# WoW pixel outbound status probe (candidate)

The native Addon now offers a manual **Status probe** button. On click, it renders a 200-cell × 4px RGB strip at the top-left of the UI for at most 20 seconds. Each cell uses only 0/1 RGB primaries (3 bits per cell). Its frame follows the bounded `wow_bridge_protocol.py` 0xC7 0x1A/Fletcher16 codec and contains solely `wow.control.status`, a session ID and a 16-bit request ID.

**This is not an authenticated Bridge connection.** No screen capture process or reply transport is installed by this change. The addon continues to show Bridge unavailable; text Q&A remains disabled. A session ID is for deduplication only, not authorization. Existing ONE/Node checks are required *before* any real status data or state transitions may be returned.

WoW client build and 1:1 pixel placement need actual Windows game testing; scaling, occlusion and focus may break a probe. Never mark this feature READY without a decoded live capture receipt.
