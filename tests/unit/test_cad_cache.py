"""cad.py's cache: one glb per content of a STEP file (the key is its sha1), the meta beside it, the cache kept under its size,
and the glb dressed so a part without a CAD colour is not a black mirror (owner 2026-10-06)."""
import json
import os
import struct

import pytest

import cad

JSON, BIN = 0x4E4F534A, 0x004E4942


def glb(doc, bin_=b""):
    j = json.dumps(doc).encode()
    j += b" " * (-len(j) % 4)
    chunks = struct.pack("<II", len(j), JSON) + j
    if bin_:
        b = bin_ + b"\0" * (-len(bin_) % 4)
        chunks += struct.pack("<II", len(b), BIN) + b
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def unpack(data):
    """(json doc, the bytes after the json chunk); checks the header and the chunk lengths on the way"""
    magic, version, total = struct.unpack("<4sII", data[:12])
    assert magic == b"glTF" and version == 2 and total == len(data)
    jl, jt = struct.unpack("<II", data[12:20])
    assert jt == JSON and jl % 4 == 0
    return json.loads(data[20:20 + jl]), data[20 + jl:]


def put(key, data=b"glb", meta=None):
    os.makedirs(cad.CACHE, exist_ok=True)
    with open(cad._glb(key), "wb") as f:
        f.write(data)
    if meta is not None:
        with open(cad._meta(key), "w") as f:
            json.dump(meta, f)


K1, K2, K3 = "1" * 40, "2" * 40, "3" * 40


# ---- keys


def test_the_same_bytes_give_the_same_key(tmp_path):
    a, b = tmp_path / "a.step", tmp_path / "b.stp"
    a.write_bytes(b"ISO-10303-21; part")
    b.write_bytes(b"ISO-10303-21; part")
    assert cad._sha1(str(a)) == cad._sha1(str(b))


def test_one_changed_byte_gives_another_key(tmp_path):
    a, b = tmp_path / "a.step", tmp_path / "b.step"
    a.write_bytes(b"ISO-10303-21; part")
    b.write_bytes(b"ISO-10303-21; parT")
    assert cad._sha1(str(a)) != cad._sha1(str(b))


def test_the_key_is_the_files_sha1_also_for_a_file_over_one_chunk(tmp_path):
    import hashlib
    data = os.urandom((1 << 20) + 17)
    f = tmp_path / "big.step"
    f.write_bytes(data)
    assert cad._sha1(str(f)) == hashlib.sha1(data).hexdigest()


def test_the_glb_and_its_meta_live_in_the_cache_named_by_the_key():
    assert cad._glb(K1) == os.path.join(cad.CACHE, K1 + ".glb")
    assert cad._meta(K1) == os.path.join(cad.CACHE, K1 + ".json")


# ---- _ready


def test_a_key_without_a_glb_is_not_ready():
    assert cad._ready(K1) is None


def test_a_ready_glb_reports_its_size_and_the_conversions_numbers():
    put(K1, b"x" * 120, {"seconds": 2.5, "mode": "gui", "version": "1.0.2", "parts": 3, "faces": 40, "diagonal_mm": 64.0, "deviation_percent": 0.05, "secret": 1})
    assert cad._ready(K1) == {"state": "ready", "key": K1, "bytes": 120, "seconds": 2.5, "mode": "gui", "version": "1.0.2", "parts": 3, "faces": 40, "diagonal_mm": 64.0,
                              "compute": "local · FreeCAD 1.0.2 · gui"}   # where it ran, in Hyimg's words (owner 2026-10-11)


def test_a_ready_glb_with_an_unreadable_meta_is_still_ready():
    put(K1, b"x" * 7)
    with open(cad._meta(K1), "w") as f:
        f.write("{not json")
    assert cad._ready(K1) == {"state": "ready", "key": K1, "bytes": 7}


def test_reading_a_ready_glb_marks_it_as_used_now():
    put(K1)
    os.utime(cad._glb(K1), (1000, 1000))
    cad._ready(K1)
    assert os.path.getmtime(cad._glb(K1)) > 1000


# ---- prune


def test_the_cache_under_its_limit_keeps_everything(monkeypatch):
    monkeypatch.setattr(cad, "CACHE_MAX", 1000)
    put(K1, b"x" * 100, {})
    put(K2, b"x" * 100, {})
    cad.prune()
    assert sorted(os.listdir(cad.CACHE)) == sorted([K1 + ".glb", K1 + ".json", K2 + ".glb", K2 + ".json"])


def test_over_the_limit_the_glb_used_longest_ago_goes_first_with_its_meta(monkeypatch):
    monkeypatch.setattr(cad, "CACHE_MAX", 250)
    for i, k in enumerate((K1, K2, K3)):
        put(k, b"x" * 100, {})
        os.utime(cad._glb(k), (1000 + i, 1000 + i))
    cad.prune()
    assert not os.path.exists(cad._glb(K1)) and not os.path.exists(cad._meta(K1))
    assert os.path.exists(cad._glb(K2)) and os.path.exists(cad._glb(K3))


def test_the_glb_just_made_is_kept_even_when_it_is_the_oldest(monkeypatch):
    monkeypatch.setattr(cad, "CACHE_MAX", 150)
    for i, k in enumerate((K1, K2, K3)):
        put(k, b"x" * 100)
        os.utime(cad._glb(k), (1000 + i, 1000 + i))
    cad.prune(keep=K1)
    assert os.path.exists(cad._glb(K1))
    assert not os.path.exists(cad._glb(K2)) and not os.path.exists(cad._glb(K3))


def test_pruning_a_cache_that_does_not_exist_yet_is_quiet():
    assert not os.path.exists(cad.CACHE)
    cad.prune()


# ---- dress


def test_a_part_without_a_material_gets_one_neutral_grey_matte_material():
    doc = {"asset": {"version": "2.0"}, "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}, {"attributes": {"POSITION": 1}}]}, {"primitives": [{"attributes": {}}]}]}
    out, rest = unpack(cad.dress(glb(doc)))
    assert len(out["materials"]) == 1
    grey = out["materials"][0]
    assert grey["pbrMetallicRoughness"]["metallicFactor"] == 0.1 and grey["pbrMetallicRoughness"]["roughnessFactor"] == 0.5
    assert grey["pbrMetallicRoughness"]["baseColorFactor"][:3] == [0.47, 0.47, 0.46]
    assert [p["material"] for m in out["meshes"] for p in m["primitives"]] == [0, 0, 0]
    assert rest == b""


def test_a_cad_colour_keeps_its_colour_and_becomes_mostly_matte():
    doc = {"materials": [{"name": "red", "pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1]}}], "meshes": [{"primitives": [{"material": 0}]}]}
    out, _ = unpack(cad.dress(glb(doc)))
    assert out["materials"] == [{"name": "red", "pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1], "metallicFactor": 0.1, "roughnessFactor": 0.5}}]


def test_a_material_that_already_says_metal_and_gloss_is_left_as_it_is():
    doc = {"materials": [{"pbrMetallicRoughness": {"metallicFactor": 1.0, "roughnessFactor": 0.05}}], "meshes": [{"primitives": [{"material": 0}, {}]}]}
    out, _ = unpack(cad.dress(glb(doc)))
    assert out["materials"][0]["pbrMetallicRoughness"] == {"metallicFactor": 1.0, "roughnessFactor": 0.05}
    assert out["meshes"][0]["primitives"][1]["material"] == 1


def test_the_binary_chunk_comes_through_unchanged_and_the_lengths_add_up():
    payload = bytes(range(256)) * 3 + b"\x01\x02"
    src = glb({"meshes": [{"primitives": [{}]}], "buffers": [{"byteLength": len(payload)}]}, payload)
    _, old_rest = unpack(src)
    out = cad.dress(src)
    _, rest = unpack(out)
    assert rest == old_rest
    assert struct.unpack("<II", rest[:8]) == (len(payload) + (-len(payload) % 4), BIN)


@pytest.mark.parametrize("data", [b"", b"glTF", b"PK\x03\x04" + b"\0" * 40, b"glTF" + b"\0" * 23])
def test_bytes_that_are_not_a_glb_are_refused(data):
    with pytest.raises(ValueError):
        cad.dress(data)


def test_a_glb_whose_first_chunk_is_not_json_is_refused():
    bad = b"glTF" + struct.pack("<II", 2, 28) + struct.pack("<II", 8, BIN) + b"\0" * 8
    with pytest.raises(ValueError, match="no json chunk"):
        cad.dress(bad)


def test_a_glb_whose_json_is_broken_is_refused():
    j = b"{nope    "[:8]
    bad = b"glTF" + struct.pack("<II", 2, 28) + struct.pack("<II", 8, JSON) + j
    with pytest.raises(ValueError):
        cad.dress(bad)
