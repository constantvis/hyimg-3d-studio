# Hyimg 3D

A plugin for [Hyimg](https://github.com/constantvis/Hyimg), the local Figma + Lightroom + Miro for working with AI agents. A 3D scene lies on the board as a card: you turn it, frame it and snapshot it into an image, and an agent can carry the same scene into Blender and back. [Русская версия](README.ru.md).

![A 3D card on the Hyimg board](docs/images/3d-card.webp)

## What it does

- A scene is a plain `scene.json` in Blender's terms: metres, z up, lights in watts, a camera with a focal length and sensor. It lives in the project folder at `3d/scenes/<name>/`.
- Double click a card to open it in 3D Studio: a layer tree with search, transform tools, lights, cameras and materials, in the spirit of Spline. Several cards can show the same scene from different cameras.
- In the studio ⌥-drag or the middle button turns the camera, Space-drag or the right button moves the view, the wheel zooms. ⌘K (or Actions in the dock) lists every command with a search. Point at Undo or Redo to see which step it takes.
- Snapshot renders the view, object masks and depth to `3d/shots/`, each with a json of the scene, camera and mask legend, ready to feed an image model.
- Whatever the plugin makes writes how long it took and where it ran, in Hyimg's fields (`seconds`, `compute`, see Hyimg's `docs/data.md`): snapshots,
  Blender's final frames («Blender Cycles · GPU · 128 samples») and STEP files FreeCAD converts. Hyimg's Info card shows them as Time and Compute.
- Models come from the project's `3d/models/<id>/model.json`; a new scene starts with a neutral stand-in.
- A new card asks for a file: Open file… (glb, gltf, obj, stl, fbx, and STEP or IGES, which FreeCAD converts once in the background), the media library with its 3D filter, or one of the recent files. Previews turn under the pointer.
- Heavy scenes are guarded: the card weighs a scene before loading it.

![3D Studio: scene tree and object properties](docs/images/3d-editor.webp)

## Install

```sh
cd hyimg && ./scripts/install_plugins.sh --3d
```

Or by hand: clone this repository and run `ln -s <path to hyimg-3d-studio> ~/Library/Application\ Support/Hyimg/plugins/3d`, then View › Restart Server in Hyimg. There is no build step; three.js is in `vendor/`. Blender (tested on 5.2) is only needed for the bridge. FreeCAD (tested on 1.1.1, found in /Applications) is only needed for STEP and IGES files; nothing is installed for you.

**For agents:** don't install the plugin silently. Ask the person whether they want 3D objects (3D scenes as cards on the board, with a bridge to Blender), and install only after a yes.

## Blender bridge (for agents)

```bash
# build a new .blend from a scene
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python blender/hyimg_scene.py -- apply "<library>/3d/scenes/<name>/scene.json" --fresh --save-as "<library>/3d/scenes/<name>/scene.blend"
# write a .blend back to the scene; --cards puts a card per camera on the board
/Applications/Blender.app/Contents/MacOS/Blender "<file.blend>" -b --python blender/hyimg_scene.py -- export "<scene.json>" --cards
```

Objects carry `hyimg_id`, `hyimg_src`, `hyimg_ai` and `hyimg_mask` properties in Blender, which is how the scene recognises them on the next trip. The scene format is described at the top of `scene.js`.

## Blender in the card

A scene made from a Blender studio's renders (`tools/studio_angles.py`: one camera per picture, the studio's geometry once) gets a
«three.js · EEVEE · Cycles» switch in 3D Studio. On EEVEE or Cycles the card shows Blender's frame of its camera, rendered in steps a
moment after the camera stops; «OK» renders the picture's final frame (its size, samples, exposure) and saves it beside the card with a
json that can reproduce it. Blender runs once per project behind Hyimg's server (`bridge.py`, `blender/bridge_server.py`) and builds the
studio's current materials by running the studio's own script up to its render, read only (`blender/studio_looks.py`). The current
materials come from the studio's `looks/current.json`, or from its newest series of renders until that file exists.

## Tests

```bash
HYIMG_REPO=<path to hyimg> python3 -m pytest tests/test_canvas_3d.py
HYIMG_REPO=<path to hyimg> python3 -m pytest tests/test_3d_files.py   # a file into a card, the library's 3D filter, the turn on hover
python3 -m pytest tests/test_blender_bridge.py tests/unit   # the Blender bridge on a tiny studio it makes (needs Blender), the helpers
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python tests/blender_test.py -- <empty folder>
node tests/convert_test.mjs <same folder>
```

**For agents changing the code:** a source file stays around 1000 lines (the check fails above 1100) and a line around 160 characters (fails above 200). A file near the limit is split by responsibility, one concern per module. The rule and its exceptions are in Hyimg's `AGENTS.md`, section «Размер файлов». `scripts/check.sh --fast` in `hyimg` checks this repository too.

## License

[PolyForm Noncommercial 1.0.0](LICENSE): free to use, study and change for yourself and for noncommercial purposes. Commercial use only with the author's permission. Third-party code in `vendor/` keeps its own licenses: three.js (MIT), Draco (Apache-2.0), DialKit (MIT).
