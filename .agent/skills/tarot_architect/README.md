# Tarot Architect: Skill Maturation Guide

This skill was distilled from the `leopardcat-tarot` project, where AI Agents repeatedly suffered from "Context Drift" regarding image framing, borders, and biological accuracy.

## Why this exists
- To enforce pure **Dual-Layer Prompting** (separate style from scene).
- To prevent "Framed images" or "Miniature borders" in Full Bleed requirements.
- To ensure correct **Taiwan Leopard Cat** markers (Facial stripes, Ear spots, Rosettes).

## Integration
This skill is "Injected" (回注) from the project back into the `agentmanager`.
- Project: `/home/ubuntu/leopardcat-tarot`
- Skill Manager: `/home/ubuntu/agentmanager/.agent/skills/tarot_architect`

## Maintenance
If the rendering script or style presets change, this skill's `SKILL.md` should be updated to maintain the global "Experience" of the AI swarm.
