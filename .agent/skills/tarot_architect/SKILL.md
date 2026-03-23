---
name: tarot_architect
description: Handles high-fidelity Tarot card generation, ensuring style consistency (Dual-Layer), biological accuracy, and rendering composition.
---

# 🃏 Tarot Architect Skill

Formalizes the knowledge and process for generating custom Tarot/Oracle card decks. Extracted from the `leopardcat-tarot` project to ensure zero style drift and perfect technical execution across all agents.

## 🎯 Core Responsibilities

1. **Dual-Layer Prompting**: Maintain the separation of Style (Layer 1) and Narrative (Layer 2).
2. **Biological Integrity**: Enforce strict biological markers for animal-themed decks (e.g., Taiwan Leopard Cat features).
3. **Technical Perfection**: Guarantee full bleed (no borders) and specific aspect ratios (2:3).
4. **Final Composition**: Manage the transition from raw AI illustration to final GFX-composited card (using local rendering scripts).

## 🎨 Dual-Layer Architecture (Protocol)

| Layer | Type | Responsibility | Storage |
| :--- | :--- | :--- | :--- |
| **Layer 1** | Style Baseline | Medium, Line weight, Base palette, Vibe | `style_presets.json` |
| **Layer 2** | Narrative Content| Scene, Subject action, Card meaning | `card-*.json` (image_prompt) |

### ⚠️ Critical Generation Constraints
- **Full Bleed**: Content MUST touch all edges. No paper margins. No vintage borders.
- **Strict Anthropomorphism**: Upright posture, wearing clothes/armor. No 4-legged animals.
- **No Text in Artwork**: Never allow the AI to generate text, numbers, or labels.

## 🧬 Biological Markers (Taiwan Leopard Cat)
- **White ear spots**: Large white patches behind black ears.
- **White forehead stripes**: Two distinct vertical stripes between eyes.
- **Rosettes**: Leopard cat specific patterns, NOT generic leopard spots.

## ⚙️ Rendering Pipeline
Once the illustration is generated, the final card MUST be composited using the local rendering pipeline:
- Script: `generator/render_card.py`
- Input: `generator/cards/card-*.json` (contains palette and metadata)
- Output: `art/renders/card-*.png`

## 🚀 Commands
- `/generate-card [card-id]`: Execute the full dual-layer and render cycle.
- `/fix-style`: Audit all card JSONs for prompt contamination and revert to Layer 2 purity.
- `/sync-manifest`: Rebuild the gallery manifest and ensure sorting integrity.
