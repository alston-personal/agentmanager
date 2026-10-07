# AgentOS Mobile Node Protocol

Status: initial architecture contract

## Principle

A phone joins AgentOS as a Realm Node, but mobile Node presence is not equivalent to desktop-style always-on execution.

```
Mobile App
  -> Enrollment / Device Identity
  -> ONE
  -> Mobile Node Core
  -> Capability / Executor Adapters
```

Node identity and capability readiness are separate.

## Identity

A Mobile Node owns:
- realm_id
- node_id
- device public-key identity
- enrollment/revocation state
- heartbeat/presence state
- push transport hints
- capability manifest

Push tokens are transport addresses, never Node identity.

Private device credentials remain in platform secure storage.

## Presence

Recommended states:
- enrolled
- reachable
- foreground
- background
- suspended
- revoked

A suspended iOS app may still be enrolled while no executor is currently runnable.

## Executors

Examples:
- mobile.notification
- mobile.camera
- mobile.photo-picker
- mobile.share-sheet
- mobile.location
- mobile.shortcut
- mobile.screen
- android.accessibility

Each executor independently reports:
- available
- ready
- busy
- permission_required
- auth_required
- suspended
- unavailable

## iOS

Baseline:
- APNs/push-driven wake/signaling
- no assumption of permanent polling daemon
- user-mediated camera/photo/share actions
- App Intents / Shortcuts for approved actions
- screen capture/stream only through OS-supported explicit user consent

Do not advertise arbitrary cross-app pointer/keyboard control as a baseline iOS capability.

## Android

Baseline:
- FCM wake/signaling
- foreground service for long-running active sessions where appropriate
- user-mediated media/camera actions

Optional governed executors:
- MediaProjection screen executor
- AccessibilityService UI executor

Enabling those executors is separate from enrolling the Node.

## Enrollment flow

1. Mobile app generates a device key.
2. User scans a ONE enrollment QR or opens an AgentOS universal/deep link.
3. App submits a join request containing its node manifest and public identity.
4. ONE exposes pending approval.
5. Human approves once.
6. Mobile app claims enrollment and receives Realm binding.
7. App registers push transport hints.
8. App publishes heartbeat and executor readiness.

## Continuation

Mobile Node participates in the same Work binding contract:

```
Work
 -> Node
 -> Executor
 -> Participant
 -> Session
```

A bare `continue` from a mobile session resolves mobile-local bound Work first.

## Security

- No silent TOTP/authenticator-secret extraction.
- No silent screen capture.
- No Accessibility/UI control without explicit local enablement.
- Remote actions are allowlisted and receipted.
- Revocation must invalidate future task execution.
- Location/camera/media permissions remain OS/user governed.

## MVP acceptance

- one iOS and one Android device enroll as separate Nodes;
- identity survives app restart;
- revoke prevents authenticated execution;
- push can cause app/node to return a bounded receipt where OS permits;
- notification capability works;
- camera/photo user-mediated capability returns a receipt;
- Node presence and executor readiness are independently visible;
- continuation resolver does not leak work between mobile and desktop Nodes.
