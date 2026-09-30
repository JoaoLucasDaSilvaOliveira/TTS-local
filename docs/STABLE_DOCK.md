# Persistent dock window

Expansion/collapse keeps the same top-level QWidget, QWindow and native surface.
The dock sets its frameless, translucent, always-on-top flags before first show.
Transitions only resize that window and reveal/disable/hide its scrollable child
content. Rapid reversals stop the current size animation and begin at its current
size; header playback controls stay available. No transition calls top-level
`show()`, `hide()`, `close()` or changes its window flags.

The previous implementation toggled `WindowDoesNotAcceptFocus` on every expansion.
[Qt documents that changing QWidget window flags hides the widget](https://doc.qt.io/qt-6/qwidget.html#windowFlags-prop).
On the tested Qt Wayland backend this also replaced the native surface, allowing
KWin's normal close/open effects to run. A stable QWidget or numerical `winId()`
alone is insufficient evidence; surface events and compositor window lifetime
must also be observed.

## Keyboard and selection tradeoff

The window remains focus-capable so expanded controls support Tab, text input,
file dialogs and Escape. Expansion deliberately requests activation and focuses
the header; activation is subject to the compositor's policy. Collapse clears
widget focus and disables the content immediately, then hides it at animation end.
The four header buttons use `NoFocus` in compact mode and `StrongFocus` expanded.

`WA_ShowWithoutActivating` is set permanently before showing the dock. This avoids
requesting activation at initial show, but **does not guarantee that clicking a
compact control preserves the editor's window focus or visible selection**.
[Qt's focus policies](https://doc.qt.io/qt-6/qwidget.html#focusPolicy-prop) govern
widget focus; Wayland/KWin still decides which native window receives keyboard
focus after a click. A permanently non-focusable window would prevent expanded
keyboard interaction. Changing the QWidget native flags would reintroduce the
surface replacement bug. This implementation therefore makes no nonactivation
guarantee for compact clicks.

Panel's existing selection cache preserves externally captured text independently
of an editor's visible highlight. Copy the selection with Ctrl+C before clicking
if the editor/compositor does not preserve it or PRIMARY was not captured in time.
The dock does not write or replace clipboard content, restore another app's focus,
change desktop focus policy, or add a layer-shell backend.

## Verification

Run the regression suite from the checkout with its existing Python environment:

```sh
PYTHONPATH=src python -m pytest -q tests/test_stable_dock.py
```

The tests cover repeated and reversed transitions with/without motion, fixed
QWindow/native ID/flags, absence of top-level hide/show/close/platform-surface
events, expanded keyboard input/Tab/Escape, and compact widget focus policy.
Offscreen tests prove the application invariant, not actual Wayland protocol or
compositor behavior.

Run a separate lightweight dock process on the real Wayland session:

```sh
QT_QPA_PLATFORM=wayland PYTHONPATH=src python scripts/check_dock_surface.py
```

It requires only Qt and does not start/load the audio service or modify the
installed runtime. It prints JSON and fails on a replaced QWindow/native ID,
changed flags, invisible top-level, or a hide/show/close/surface event during 23
rapid transitions. Initial creation/show and final intentional close are excluded.
Use a temporary KWin observer filtered to this process/window alongside the probe
to check one initial window addition, zero additions/removals during transitions,
and one removal on final exit. Then manually verify expanded keyboard/file-dialog
behavior, Escape, compact playback controls, external selection cache, and
clipboard preservation in the actual editor. Do not infer those results from the
offscreen run or Qt counters alone.
