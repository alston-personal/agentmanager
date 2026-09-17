from pathlib import Path

ROOT = Path.cwd()
MARKER = "/* Mobile landscape workspace v2: touch-aware breakpoints and horizontal layout. */"


def replace_one(path: str, old: str, new: str):
    p = ROOT / path
    s = p.read_text()
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{path}: expected one match, got {n}: {old!r}")
    p.write_text(s.replace(old, new, 1))


def append_once(path: str, marker: str, text: str):
    p = ROOT / path
    s = p.read_text()
    if marker in s:
        return
    p.write_text(s.rstrip() + "\n\n" + text.strip() + "\n")


# The existing mobile CSS was width-only. iPhone landscape (844-932 CSS px)
# therefore fell back to desktop rules. Keep narrow-window support, but also
# identify coarse touch devices up to tablet width.
replace_one(
    "app/workbench.css",
    "@media(max-width:720px){",
    "@media(max-width:720px), (hover:none) and (pointer:coarse) and (max-width:1024px){",
)
replace_one(
    "components/floorplan-viewer.css",
    "@media(max-width:820px){",
    "@media(max-width:820px), (hover:none) and (pointer:coarse) and (max-width:1024px){",
)
replace_one(
    "components/floorplan-viewer.css",
    "@media(max-width:900px) and (max-height:520px) and (orientation:landscape){",
    "@media (hover:none) and (pointer:coarse) and (orientation:landscape) and (max-width:1024px) and (max-height:600px){",
)
replace_one(
    "app/mobile-pwa.css",
    "@media (max-width: 820px) {",
    "@media (max-width: 820px), (hover:none) and (pointer:coarse) and (max-width:1024px) {",
)
replace_one(
    "app/mobile-pwa.css",
    "@media (display-mode: standalone) and (max-width: 820px) {",
    "@media (display-mode: standalone) and (max-width:820px), (display-mode:standalone) and (hover:none) and (pointer:coarse) and (max-width:1024px) {",
)

append_once(
    "app/mobile-pwa.css",
    MARKER,
    r'''
/* Mobile landscape workspace v2: touch-aware breakpoints and horizontal layout. */
@media (hover:none) and (pointer:coarse) and (orientation:landscape) and (max-width:1024px) and (max-height:600px) {
  html, body, #root {
    height: 100% !important;
    min-height: 0 !important;
    overflow: hidden !important;
  }

  .app-shell:not(.mode-search) {
    width: 100% !important;
    height: 100dvh !important;
    min-height: 100dvh !important;
    display: grid !important;
    grid-template-rows: auto minmax(0, 1fr) !important;
    overflow: hidden !important;
  }

  /* One compact landscape header. Respect left/right notch safe areas. */
  .app-shell .masthead {
    min-height: 46px !important;
    height: auto !important;
    padding-top: max(4px, env(safe-area-inset-top)) !important;
    padding-right: max(8px, env(safe-area-inset-right)) !important;
    padding-bottom: 4px !important;
    padding-left: max(8px, env(safe-area-inset-left)) !important;
    display: grid !important;
    grid-template-columns: auto minmax(250px, 1fr) auto !important;
    grid-template-areas: "brand switch actions" !important;
    gap: 6px 8px !important;
    align-items: center !important;
  }
  .app-shell .masthead > .brand { grid-area: brand !important; gap: 5px !important; }
  .app-shell .brand-mark { padding: 5px !important; }
  .app-shell .brand strong { font-size: 15px !important; letter-spacing: 1px !important; }
  .app-shell .masthead > div:nth-of-type(1) {
    grid-area: switch !important;
    width: min(100%, 390px) !important;
    justify-self: center !important;
    display: grid !important;
    grid-template-columns: 1fr 1fr !important;
    gap: 3px !important;
    padding: 2px !important;
  }
  .app-shell .masthead > div:nth-of-type(1) > button {
    min-height: 32px !important;
    padding: 4px 8px !important;
    font-size: 9.5px !important;
    line-height: 1.15 !important;
  }
  .app-shell .mast-actions { grid-area: actions !important; gap: 3px !important; }
  .app-shell .mast-actions .phase { display: none !important; }
  .app-shell .mast-actions button {
    width: 34px !important;
    height: 34px !important;
    min-height: 34px !important;
    padding: 0 !important;
  }
  .app-shell .mast-actions button span { display: none !important; }

  /* Landscape should use the width we gained instead of stacking two tall panes. */
  .app-shell .workspace {
    width: 100% !important;
    max-width: none !important;
    height: 100% !important;
    min-height: 0 !important;
    margin: 0 !important;
    display: grid !important;
    grid-template-columns: minmax(235px, 34vw) minmax(0, 1fr) !important;
    grid-template-rows: minmax(0, 1fr) !important;
    overflow: hidden !important;
    border-radius: 0 !important;
  }
  .app-shell .controls {
    height: 100% !important;
    min-height: 0 !important;
    overflow: hidden !important;
    border-right: 1px solid #e0e5d7 !important;
    border-bottom: 0 !important;
  }
  .control-tabs { height: 38px !important; }
  .control-tab { min-width: 0 !important; font-size: 9px !important; gap: 2px !important; }
  .control-tab span { font-size: 7.5px !important; }
  .app-shell .controls .control-panel {
    min-height: 0 !important;
    padding: 8px 10px 12px !important;
    overflow-y: auto !important;
    overscroll-behavior: contain !important;
    -webkit-overflow-scrolling: touch !important;
  }

  .app-shell .drawing-area {
    height: 100% !important;
    min-height: 0 !important;
    padding-top: 5px !important;
    padding-right: max(6px, env(safe-area-inset-right)) !important;
    padding-bottom: max(6px, env(safe-area-inset-bottom)) !important;
    padding-left: 6px !important;
    overflow: hidden !important;
    display: flex !important;
    flex-direction: column !important;
  }
  .app-shell .drawing-top {
    flex: none !important;
    margin: 0 0 4px !important;
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 8px !important;
  }
  .drawing-top h2 {
    max-width: 31vw !important;
    font-size: 11px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
  }
  .view-switch {
    width: auto !important;
    flex: none !important;
    display: grid !important;
    grid-template-columns: repeat(3, minmax(76px, 1fr)) !important;
    gap: 2px !important;
    padding: 2px !important;
  }
  .view-switch button {
    min-height: 32px !important;
    padding: 4px 6px !important;
    font-size: 9px !important;
  }

  /* Main drawing/3D area fills the remaining landscape height. */
  .app-shell .drawing-area > section.w-full {
    height: auto !important;
    min-height: 0 !important;
    flex: 1 1 0 !important;
    overflow: hidden !important;
  }
  .floorplan-viewer {
    height: 100% !important;
    min-height: 0 !important;
    border-radius: 9px !important;
  }
  .fv-toolbar {
    flex: none !important;
    padding: 5px 7px !important;
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: 7px !important;
  }
  .fv-toolbar > div:first-child {
    min-width: 94px !important;
    flex-direction: column !important;
    align-items: flex-start !important;
    justify-content: center !important;
    gap: 1px !important;
  }
  .fv-toolbar > div:first-child span { display: none !important; }
  .fv-toolbar strong { font-size: 10.5px !important; white-space: nowrap !important; }
  .fv-options {
    flex: 1 1 auto !important;
    width: auto !important;
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    gap: 4px !important;
  }
  .fv-options button { min-height: 32px !important; padding: 4px 8px !important; font-size: 9.5px !important; }
  .fv-footer {
    flex: none !important;
    order: 1 !important;
    display: grid !important;
    grid-template-columns: 1fr !important;
    gap: 3px !important;
    padding: 4px 5px !important;
  }
  .fv-footer nav { grid-template-columns: repeat(4, minmax(0, 1fr)) !important; gap: 4px !important; }
  .fv-footer nav button { min-height: 34px !important; padding: 4px 3px !important; font-size: 9.5px !important; }
  .fv-height { display: none !important; }
  .fv-stage {
    order: 2 !important;
    min-height: 0 !important;
    height: auto !important;
    flex: 1 1 0 !important;
  }
  .fv-caption { top: 6px !important; left: 7px !important; }
  .fv-caption small { font-size: 8.5px !important; max-width: 55vw !important; }

  /* 2D mode gets the same usable-height treatment. */
  .app-shell .canvas {
    flex: 1 1 0 !important;
    min-height: 0 !important;
    overflow: auto !important;
  }
  .app-shell .canvas.has-image svg {
    width: max(100%, 560px) !important;
    height: auto !important;
    max-height: none !important;
  }
  .work-bottom { min-height: 30px !important; padding: 3px 6px !important; }

  .pwa-reload {
    left: max(8px, env(safe-area-inset-left)) !important;
    bottom: max(8px, env(safe-area-inset-bottom)) !important;
    min-height: 36px !important;
    padding: 0 10px !important;
    font-size: 10px !important;
  }
  .app-shell > button.fixed {
    right: max(8px, env(safe-area-inset-right)) !important;
    bottom: max(8px, env(safe-area-inset-bottom)) !important;
    width: 38px !important;
    height: 38px !important;
  }
}

/* Very short landscape phones: reclaim a little more vertical room. */
@media (hover:none) and (pointer:coarse) and (orientation:landscape) and (max-height:430px) and (max-width:1024px) {
  .app-shell .masthead { min-height: 42px !important; }
  .app-shell .brand-mark { display: none !important; }
  .control-tabs { height: 35px !important; }
  .app-shell .controls .control-panel { padding-top: 6px !important; }
  .app-shell .drawing-top { margin-bottom: 3px !important; }
  .view-switch button { min-height: 29px !important; }
  .fv-toolbar { padding-block: 4px !important; }
  .fv-options button { min-height: 29px !important; }
  .fv-footer nav button { min-height: 31px !important; }
}
'''
)

# Immersive indoor mode must outrank all normal workspace sizing rules. Both
# sides use !important, so increase selector specificity deliberately.
append_once(
    "components/indoor-joystick.css",
    "/* Immersive landscape hard override v2. */",
    r'''
/* Immersive landscape hard override v2. */
body.fv-immersive-open .app-shell .drawing-area > section.floorplan-viewer.fv-immersive,
body.fv-immersive-open .floorplan-viewer.fv-immersive {
  position: fixed !important;
  inset: 0 !important;
  z-index: 2147483000 !important;
  width: 100vw !important;
  height: 100dvh !important;
  min-height: 100dvh !important;
  max-height: none !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  overflow: hidden !important;
}
body.fv-immersive-open .pwa-reload,
body.fv-immersive-open .app-shell > button.fixed {
  display: none !important;
}

@media (hover:none) and (pointer:coarse) and (orientation:landscape) and (max-height:600px) {
  .floorplan-viewer.fv-immersive .fv-stage { min-height: 0 !important; height: 100dvh !important; }
  .fv-indoor-topbar {
    top: max(6px, env(safe-area-inset-top));
    left: max(8px, env(safe-area-inset-left));
    right: max(8px, env(safe-area-inset-right));
    grid-template-columns: auto minmax(120px, 1fr) auto;
    gap: 7px;
  }
  .fv-indoor-topbar button, .fv-indoor-topbar select { min-height: 36px; padding: 5px 9px; font-size: 10.5px; }
  .fv-indoor-room { justify-self: center; max-width: 220px; }
  .fv-indoor-room select { max-width: 145px; }
  .fv-joysticks {
    bottom: max(7px, env(safe-area-inset-bottom));
    padding-left: max(10px, env(safe-area-inset-left));
    padding-right: max(10px, env(safe-area-inset-right));
  }
  .fv-stick-wrap { width: 110px; gap: 4px; }
  .fv-stick-base { width: 96px; height: 96px; }
  .fv-stick-knob { width: 44px; height: 44px; margin: -22px 0 0 -22px; }
  .fv-stick-label { font-size: 9.5px; padding: 2px 7px; }
}

@media (hover:none) and (pointer:coarse) and (orientation:landscape) and (max-height:370px) {
  .fv-indoor-topbar button, .fv-indoor-topbar select { min-height: 32px; font-size: 9.5px; }
  .fv-stick-wrap { width: 96px; }
  .fv-stick-base { width: 82px; height: 82px; }
  .fv-stick-knob { width: 38px; height: 38px; margin: -19px 0 0 -19px; }
  .fv-stick-label { display: none; }
}
'''
)

print("patched mobile landscape breakpoints and layout")
