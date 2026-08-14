# AgentOS Ecosystem Manifests v0.1

This document defines the shared nouns used by AgentOS. The files are declarative
and belong to the logic layer of a project or module; credentials and runtime
state remain outside the repository.

## Resource envelope

Every resource uses the following envelope:

    apiVersion: agentos/v1
    kind: Project | Module | Node | Environment
    metadata:
      id: stable-lowercase-id
      version: 0.1.0
      labels: {}
    spec: {}

metadata.id is stable identity. metadata.version is an immutable semantic
version for artifacts and desired configuration. A changed artifact must get a
new version and digest; nodes never overwrite an installed version in place.

## Project

A Project owns business source and declares module dependencies. It does not
contain provider keys, node-local paths, or mutable execution state.

Required spec fields:

- modules: module requirements (id, version, optional alias and config)
- environments: names of deployable environments

## Module

A Module is a versioned, distributable capability. It owns its implementation,
input/output contracts, required permissions, and resource requirements.

Required spec fields:

- runtime: python, node, container, or binary
- entrypoint: runtime entrypoint
- capabilities: callable capability contracts
- artifact: immutable registry reference and SHA-256 digest

Permissions are declared, then approved by the Control Plane. A module cannot
read arbitrary node secrets merely because it runs on a trusted node.

## Node

A Node is an execution host, not a source repository. Its manifest describes
resources, labels, endpoints, and advertised capabilities. The Node Agent sends
the live heartbeat; the manifest is the desired/static identity.

## Environment

An Environment binds one Project to locked module versions, policies, and node
selection. production must use a lockfile and immutable artifact digests.

## Version and ownership rules

1. Project source is canonical in its project repository.
2. Module source is canonical in its module repository; installed copies are
   caches managed by the Node Agent.
3. Control Plane state is authoritative for registration, leases, rollout, and
   audit; it is not a replacement for source control.
4. Secrets live in the secret manager or node secret store and are referenced by
   name only.
5. Every task and artifact is addressable by an ID and digest, so retries are
   idempotent and rollbacks are possible.
