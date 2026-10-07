"""«Свет и материалы» in the 3D studio (owner 2026-10-07: «было бы шикарно, если можно как-то свет тестировать и материалы»), Chromium and
WebKit. The Blender bridge is answered by the page itself (Playwright's route), so no Blender is needed: it lists the look's materials as
Blender would, and gives a frame per request, red for a variant and grey for the look as it is, so A/B shows which half is which.

What it checks: the outliner's «Materials» section has the card's variant and the look's materials; a material's pane shows the
parameters Blender reported (a factor for an input driven by nodes); the first change makes the card a variant, three.js mirrors it,
Blender's next preview carries it, History names it, ⌘Z and ⇧⌘Z take it back and forth; the bar's variant list switches the card back to
the look as it is and again; A/B renders the compared variant after the card's own and shows both halves with a line that drags; the
variant's light «Own light» sends the scene's lights with the frame, a light's colour temperature is a light's field; «Cancel» leaves
scene.json byte for byte and the card without a variant, «Save» writes the variants.

  HYIMG_REPO=<Hyimg checkout> python3 -m pytest tests/test_light_materials.py
"""
import io
import json
import os

import pytest
from playwright.sync_api import sync_playwright

from test_canvas_3d import hy as _hy, wait_file, model_in_the_middle   # noqa: F401
from test_3d_files import ENGINES, new_card, open_board, scene_of
from test_editor_ui import open_editor
from test_blender_bar import studio_scene

hy = _hy
SHOTS = os.environ.get("HYIMG_SHOTS")
LIVE_DOC = "p => import('/plugins/3d/engine.js').then(m => m.docOf(p))"
MATS = [{"name": n, "users": u, "parts": [f"Object_{i}" for i in range(u)], "principled": "Principled BSDF", "look": "M26",
         "params": {"base_color": {"value": [0.6, 0.6, 0.6], "linked": False}, "metallic": {"value": 0.2, "linked": False},
                    "roughness": {"value": None, "linked": True} if n == "resin" else {"value": 0.4, "linked": False}, "coat": {"value": 0, "linked": False}}}
        for n, u in (("frame metal", 4), ("glass", 1), ("lens", 1), ("resin", 3))]


def png(rgb):
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (64, 64), rgb).save(b, "PNG"); return b.getvalue()


def fake_bridge(page, log):
    """the bridge as the page sees it: every request kept in log, each job done at once with three steps"""
    jobs = {}

    def handle(route):
        body = json.loads(route.request.post_data or "{}"); log.append(body); act = body.get("action")
        if act == "look": return route.fulfill(json=dict(id="M26", key="k1", source="derived", updated="2026-10-07 00:27"))
        if act == "materials": return route.fulfill(json={"list": MATS})
        if act in ("preview", "final"):
            jid = f"j{len(jobs)}"; jobs[jid] = body
            return route.fulfill(json={"job": jid, "state": "building", "frames": 0, "look": {"id": "M26"}})
        if act == "job":
            b = jobs[body["job"]]
            return route.fulfill(json={"job": body["job"], "state": "done", "frames": 3, "look": {"id": "M26"}, "exact_camera": True, "elapsed": 0.1,
                                       "last": {"samples": 64, "step": 2, "steps": 3, "seconds": 0.1, "engine": b.get("engine"), "device": "GPU", "res": [64, 64]}})
        if act == "frame":
            b = jobs[body["job"]]
            return route.fulfill(body=png((200, 40, 60) if b.get("variant") else (128, 128, 128)), content_type="image/png")
        return route.fulfill(json={"ok": True})
    page.route("**/api/plugin/3d/blender", handle)


def set_slider(frame, label, v):
    frame.evaluate("""([label, v]) => { const r = [...document.querySelectorAll('.m3r .hy-slider')]
      .find(x => ((x.querySelector('.hy-slider-l') || {}).textContent || '').replace(/\\s+/g, ' ').trim() === label);
      const i = r.querySelector('input'); i.value = v; i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change', { bubbles: true })); }""", [label, v])


def choose(frame, label, option):
    frame.locator(".m3r .dialkit-select-trigger", has_text=label).first.click()
    frame.locator(".dialkit-select-option", has_text=option).first.click()


@pytest.mark.parametrize("hy", ["en"], indirect=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_materials_variants_light_and_ab(hy, engine):
    port, lib = hy
    with sync_playwright() as p:
        browser, page, frame, errors = open_board(p, engine, port)
        log = []; fake_bridge(page, log)
        cid = new_card(frame); scene = scene_of(lib, frame, cid)
        model_in_the_middle(frame, scene)
        studio_scene(scene); frame.wait_for_timeout(4000)
        rel = str(scene).split("/lib/", 1)[-1]
        open_editor(frame, cid)
        # the section: the card's variant first, then the materials three.js shows (scene.glb's names) until Blender lists them
        frame.wait_for_selector('.ms[data-s="materials"]:not([hidden]) .row[data-mat="resin"]', timeout=15000)
        rows = frame.locator('.ms[data-s="materials"] .row .nm').all_inner_texts()
        assert rows[0].startswith("No changes") and [r.strip() for r in rows[1:]] == ["frame metal", "glass", "lens", "resin"], rows
        frame.click(".m3bplate [data-eng=EEVEE]")
        # a material's pane: Blender's parameters, the node-driven roughness as a factor
        frame.click('.row[data-mat="resin"]')
        frame.wait_for_function("() => [...document.querySelectorAll('.m3r .hy-slider-l')].some(x => x.textContent.trim() === 'Roughness ×')", timeout=15000)
        labels = frame.evaluate("() => [...document.querySelectorAll('.m3r .dk :is(.hy-slider-l, .dialkit-color-label, .dialkit-button)')].map(x => x.textContent.trim())")
        assert {"Base color", "Metallic", "Roughness ×", "Coat", "Reset material"} <= set(labels), labels
        assert frame.locator('.row[data-mat="resin"].sel').count() == 1, "the picked material has the list's selected row"
        assert any(b.get("action") == "materials" for b in log)
        set_slider(frame, "Metallic", 0.9); set_slider(frame, "Roughness ×", 0.5)
        frame.wait_for_timeout(500)
        d = frame.evaluate(LIVE_DOC, rel); it = frame.evaluate(f"() => board.items[{json.dumps(cid)}]")
        v = d["variants"][0]
        assert v["materials"] == {"resin": {"metallic": 0.9, "roughness": {"mul": 0.5}}} and v["light"] == "studio" and it["variant"] == v["id"], (v, it)
        assert v["name"] == "M26 · materials"
        mirrored = frame.evaluate("() => import('/plugins/3d/variants.js').then(m => m.liveMaterial('resin'))")
        assert abs(mirrored["metalness"] - 0.9) < 1e-6, ("three.js mirrors the variant", mirrored)
        for _ in range(50):   # the preview 0.35 s after the last change
            pv = [b for b in log if b.get("action") == "preview" and (b.get("variant") or {}).get("materials")]
            if pv: break
            frame.wait_for_timeout(100)
        assert pv and pv[-1]["variant"]["materials"]["resin"]["metallic"] == 0.9, log[-4:]
        frame.click(".m3tabs [data-tab=hist]")
        hist = frame.locator(".m3hist .hrow").all_inner_texts()
        assert any("resin" in h for h in hist), hist
        frame.click(".m3tabs [data-tab=props]")
        if SHOTS: page.screenshot(path=os.path.join(SHOTS, f"lm-material-{engine}.png"))
        # ⌘Z takes the change back, the variant with it; ⇧⌘Z brings it again
        frame.locator(".m3r .ih").click()
        page.keyboard.press("Meta+z"); frame.wait_for_timeout(400)
        assert not (frame.evaluate(LIVE_DOC, rel).get("variants")) and "variant" not in frame.evaluate(f"() => board.items[{json.dumps(cid)}]")
        page.keyboard.press("Meta+Shift+z"); frame.wait_for_timeout(400)
        assert frame.evaluate(LIVE_DOC, rel)["variants"][0]["materials"]["resin"]["metallic"] == 0.9
        # the bar: back to the look as it is, and to the variant again
        vid = frame.evaluate(f"() => board.items[{json.dumps(cid)}].variant")
        frame.select_option("#handles .m3bplate [data-var]", "")
        frame.wait_for_function(f"() => !board.items[{json.dumps(cid)}].variant")
        frame.select_option("#handles .m3bplate [data-var]", vid)
        frame.wait_for_function(f"() => board.items[{json.dumps(cid)}].variant === {json.dumps(vid)}")
        # A/B: the look as it is on the left, rendered after the card's own variant, a line between them that drags
        n0 = len(log)
        frame.click("#handles .m3bplate [data-ab]")
        frame.wait_for_function(f"() => board.items[{json.dumps(cid)}].compare === 'base'")
        frame.wait_for_selector(".plg-live .m3split:not([hidden])", timeout=15000)
        later = [b for b in log[n0:] if b.get("action") == "preview"]
        assert any(not b.get("variant") for b in later), "A, the look as it is, was rendered"
        assert frame.locator(".plg-live img.m3bimgA:not([hidden])").count() == 1
        assert frame.locator(".plg-live .m3split .la").inner_text().startswith("A · No changes")
        h = frame.locator(".plg-live .m3split .hd").bounding_box(); card = frame.locator(f".plg[data-id={cid}]").bounding_box()
        page.mouse.move(h["x"] + h["width"] / 2, h["y"] + h["height"] / 2); page.mouse.down()
        page.mouse.move(card["x"] + card["width"] * 0.25, h["y"] + h["height"] / 2, steps=5); page.mouse.up()
        ab = frame.evaluate(f"() => +getComputedStyle(document.querySelector('.plg[data-id={cid}]')).getPropertyValue('--ab')")
        assert 0.15 < ab < 0.35, ab
        if SHOTS: page.screenshot(path=os.path.join(SHOTS, f"lm-ab-{engine}.png"))
        # the variant's own light: the scene's lamps go with the frame
        frame.click('.row[data-lm="variant"]')
        frame.wait_for_selector(".m3r .dialkit-select-trigger", timeout=10000)
        choose(frame, "Light", "Own light")
        frame.wait_for_function("p => import('/plugins/3d/engine.js').then(m => m.docOf(p).variants[0].light === 'own')", arg=rel)
        for _ in range(50):   # the preview 0.35 s after the change, once the one running has ended
            own = [b for b in log if b.get("action") == "preview" and (b.get("variant") or {}).get("light") == "own"]
            if own: break
            frame.wait_for_timeout(100)
        lamps = frame.evaluate(LIVE_DOC, rel)["lights"]
        assert own and [l["id"] for l in own[-1]["lights"]] == [l["id"] for l in lamps] and lamps, (own[-1:], lamps)
        if SHOTS: page.screenshot(path=os.path.join(SHOTS, f"lm-variant-{engine}.png"))
        # a light's colour temperature
        frame.click('.ms[data-s="lights"] .row[data-u] .nm')
        frame.wait_for_function("() => [...document.querySelectorAll('.m3r .hy-slider-l')].some(x => x.textContent.replace(/\\s+/g, ' ').trim() === 'Temperature, K')", timeout=10000)
        frame.evaluate("""() => { const row = [...document.querySelectorAll('.m3r .dk *')].find(e => e.children.length && e.textContent.replace(/\\s+/g, ' ').trim().startsWith('By temperature')
          && e.querySelector('.dialkit-segmented-button')); [...row.querySelectorAll('.dialkit-segmented-button')].find(b => b.textContent.trim() === 'On').click(); }""")
        set_slider(frame, "Temperature, K", 3200); frame.wait_for_timeout(400)
        assert any(l.get("temp") == 3200 for l in frame.evaluate(LIVE_DOC, rel)["lights"])
        assert "Blender renders the card with these lamps" in frame.locator(".m3r .inf").inner_text()
        if SHOTS: page.screenshot(path=os.path.join(SHOTS, f"lm-light-{engine}.png"))
        # «Cancel»: nothing of it stays
        raw = scene.read_text()
        frame.click("#dock [data-a=cancel]") if frame.locator("#dock [data-a=cancel]").count() else frame.click(".m3t [data-a=cancel]")
        frame.wait_for_selector("#hyConfirm.on", timeout=5000); frame.wait_for_timeout(300)
        frame.click("#hyConfirm button.ok"); frame.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
        frame.wait_for_timeout(600)
        assert scene.read_text() == raw and "variant" not in frame.evaluate(f"() => board.items[{json.dumps(cid)}]")
        # again, and «Save» writes the variant into scene.json
        open_editor(frame, cid)
        frame.wait_for_selector('.row[data-mat="glass"]', timeout=15000)
        frame.click('.row[data-mat="glass"]')
        frame.wait_for_function("() => [...document.querySelectorAll('.m3r .hy-slider-l')].some(x => x.textContent.trim() === 'Roughness')", timeout=15000)
        set_slider(frame, "Roughness", 0.1); frame.wait_for_timeout(500)
        frame.locator(".m3r .ih").click(); page.keyboard.press("Meta+Enter"); frame.wait_for_function("() => !document.querySelector('.plg-live')", timeout=20000)
        d = wait_file(scene, lambda d: bool(d.get("variants")))
        it = frame.evaluate(f"() => board.items[{json.dumps(cid)}]")
        assert d["variants"][0]["materials"] == {"glass": {"roughness": 0.1}} and it["variant"] == d["variants"][0]["id"], (d.get("variants"), it)
        assert not errors, errors
        browser.close()
