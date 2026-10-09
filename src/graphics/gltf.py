"""Binary glTF (.glb), just enough for the control room's models: write what graphics/models.py builds, read that or a
CC0 model dropped into assets/. Triangles only; positions and normals required; uv, COLOR_0, one base-colour texture,
metallic/roughness, emissive and node transforms honoured. Anything else is refused by name rather than half-drawn."""
import io
import json
import struct
from pathlib import Path

import numpy as np
import pygame

GLB, JSON_CHUNK, BIN_CHUNK = 0x46546C67, 0x4E4F534A, 0x004E4942
COMPONENTS = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
MOVING = ("arms_", "wheel_")  # parts the game moves besides the head: a crewman's arm poses, a helm's wheels


# ---------- writing ----------
def write(path, parts, materials, generator="Silent Solution"):
    """parts: {name: (pivot or None, [(material name, verts N x 11 f4: pos, normal, uv, colour; indices)])}.
    A part with a pivot becomes a node placed at it (a head turns about its neck); its vertices are model space.
    materials: {name: dict(color=(r, g, b, a), rough, metal, emissive=(r, g, b), png=bytes or None, wear)}."""
    blob, views, accessors = bytearray(), [], []

    def view(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        views.append(dict(buffer=0, byteOffset=len(blob), byteLength=len(data), **({"target": target} if target
                                                                                      else {})))
        blob.extend(data)
        return len(views) - 1

    def accessor(arr, kind, target):
        arr = np.ascontiguousarray(arr)
        ctype = {np.dtype("f4"): 5126, np.dtype("u2"): 5123, np.dtype("u4"): 5125}[arr.dtype]
        a = dict(bufferView=view(arr.tobytes(), target), componentType=ctype, count=len(arr), type=kind)
        if kind == "VEC3" and ctype == 5126:
            a.update(min=arr.min(0).tolist(), max=arr.max(0).tolist())
        accessors.append(a)
        return len(accessors) - 1

    names = list(materials)
    images, textures, mats = [], [], []
    for name in names:
        m = materials[name]
        pbr = dict(baseColorFactor=list(m.get("color", (1, 1, 1, 1))), metallicFactor=m.get("metal", 0.0),
                   roughnessFactor=m.get("rough", 0.8))
        if m.get("png"):
            images.append(dict(bufferView=view(m["png"]), mimeType="image/png"))
            textures.append(dict(source=len(images) - 1))
            pbr["baseColorTexture"] = dict(index=len(textures) - 1)
        mats.append(dict(name=name, pbrMetallicRoughness=pbr, emissiveFactor=list(m.get("emissive", (0, 0, 0))),
                         extras=dict(wear=m.get("wear", 0.0))))
    meshes, nodes = [], []
    for part, (pivot, prims) in parts.items():
        shift = np.zeros(3, "f4") if pivot is None else np.asarray(pivot, "f4")
        out = []
        for mat, verts, idx in prims:
            v = verts.astype("f4").copy()
            v[:, :3] -= shift
            attrs = dict(POSITION=accessor(v[:, 0:3], "VEC3", 34962), NORMAL=accessor(v[:, 3:6], "VEC3", 34962),
                         TEXCOORD_0=accessor(v[:, 6:8], "VEC2", 34962), COLOR_0=accessor(v[:, 8:11], "VEC3", 34962))
            ind = idx.astype("u2" if len(v) < 65536 else "u4")
            out.append(dict(attributes=attrs, indices=accessor(ind, "SCALAR", 34963), material=names.index(mat)))
        meshes.append(dict(name=part, primitives=out))
        nodes.append(dict(name=part, mesh=len(meshes) - 1, **({} if pivot is None else
                                                              {"translation": [float(x) for x in shift]})))
    doc = dict(asset=dict(version="2.0", generator=generator), scene=0,
               scenes=[dict(nodes=list(range(len(nodes))))], nodes=nodes, meshes=meshes, materials=mats,
               accessors=accessors, bufferViews=views, buffers=[dict(byteLength=len(blob))])
    if images:
        doc.update(images=images, textures=textures)
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob.extend(b"\0" * (-len(blob) % 4))
    total = 12 + 8 + len(js) + 8 + len(blob)
    data = struct.pack("<III", GLB, 2, total) + struct.pack("<II", len(js), JSON_CHUNK) + js + \
        struct.pack("<II", len(blob), BIN_CHUNK) + bytes(blob)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)


# ---------- reading ----------
def generator(path):
    """The asset.generator a .glb names: who made it."""
    data = Path(path).read_bytes()
    jlen = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + jlen]).get("asset", {}).get("generator", "")


def _matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T  # glTF stores column-major
    t = np.array(node.get("translation", (0, 0, 0)), float)
    x, y, z, w = node.get("rotation", (0, 0, 0, 1))
    s = np.array(node.get("scale", (1, 1, 1)), float)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.identity(4)
    m[:3, :3], m[:3, 3] = r * s, t
    return m


def load(path):
    """{part: (pivot (3,), [(verts N x 11 f4 in model space, indices u4, material dict, image Surface or None)])}.
    The subtree under a node named "head" (or "arms_N", "wheel_N") is that part, pivoting on the node's origin;
    all else is "body"."""
    path = Path(path)
    data = path.read_bytes()
    magic, version, _ = struct.unpack_from("<III", data)
    if magic != GLB or version != 2:
        raise ValueError(f"{path.name}: not a glTF 2.0 .glb")
    jlen, _ = struct.unpack_from("<II", data, 12)
    doc = json.loads(data[20:20 + jlen])
    blen = struct.unpack_from("<I", data, 20 + jlen)[0] if len(data) > 20 + jlen else 0
    blob = data[28 + jlen:28 + jlen + blen]

    def view_bytes(i):
        v = doc["bufferViews"][i]
        if v.get("buffer", 0) != 0 or "uri" in doc["buffers"][v.get("buffer", 0)]:
            raise ValueError(f"{path.name}: external buffers aren't supported; export as a single .glb")
        return blob[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]], v.get("byteStride")

    def read(i):
        a = doc["accessors"][i]
        if "sparse" in a or "bufferView" not in a:
            raise ValueError(f"{path.name}: sparse accessors aren't supported")
        raw, stride = view_bytes(a["bufferView"])
        dtype, width = np.dtype(COMPONENTS[a["componentType"]]), WIDTH[a["type"]]
        stride = stride or dtype.itemsize * width
        arr = np.ndarray((a["count"], width), dtype, raw, a.get("byteOffset", 0), (stride, dtype.itemsize))
        out = arr.astype("f4")
        if a.get("normalized"):
            out /= float(np.iinfo(dtype).max)
        return out

    images = {}

    def image(tex_index):
        src = doc["textures"][tex_index]["source"]
        if src not in images:
            img = doc["images"][src]
            if "bufferView" in img:
                raw = view_bytes(img["bufferView"])[0]
                images[src] = pygame.image.load(io.BytesIO(raw), "texture.png" if "png" in img["mimeType"]
                                                else "texture.jpg")
            else:
                images[src] = pygame.image.load(path.parent / img["uri"])
        return images[src]

    parts = {"body": [np.zeros(3), []]}

    def walk(n, parent, part):
        node = doc["nodes"][n]
        world = parent @ _matrix(node)
        name = node.get("name", "")
        if name == "head" or name.startswith(MOVING):
            part = name
            parts[name] = [world[:3, 3].copy(), []]
        if "mesh" in node:
            normal_m = np.linalg.inv(world[:3, :3]).T
            for prim in doc["meshes"][node["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4:
                    raise ValueError(f"{path.name}: only triangle primitives are supported")
                at = prim["attributes"]
                if "NORMAL" not in at:
                    raise ValueError(f"{path.name}: a mesh has no normals; export with normals")
                pos, nrm = read(at["POSITION"]), read(at["NORMAL"])
                count = len(pos)
                uv = read(at["TEXCOORD_0"]) if "TEXCOORD_0" in at else np.zeros((count, 2), "f4")
                col = read(at["COLOR_0"])[:, :3] if "COLOR_0" in at else np.ones((count, 3), "f4")
                pos = pos @ world[:3, :3].T + world[:3, 3]
                nrm = nrm @ normal_m.T
                nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
                idx = read(prim["indices"])[:, 0].astype("u4") if "indices" in prim else np.arange(count, dtype="u4")
                m = doc["materials"][prim["material"]] if "material" in prim else {}
                pbr = m.get("pbrMetallicRoughness", {})
                mat = dict(color=tuple(pbr.get("baseColorFactor", (1, 1, 1, 1))), rough=pbr.get("roughnessFactor", 1.0),
                           metal=pbr.get("metallicFactor", 1.0), emissive=tuple(m.get("emissiveFactor", (0, 0, 0))),
                           wear=m.get("extras", {}).get("wear", 0.0), name=m.get("name", ""))
                tex = image(pbr["baseColorTexture"]["index"]) if "baseColorTexture" in pbr else None
                verts = np.column_stack([pos, nrm, uv, col]).astype("f4")
                parts[part][1].append((verts, idx, mat, tex))
        for c in node.get("children", ()):
            walk(c, world, part)

    for n in doc["scenes"][doc.get("scene", 0)]["nodes"]:
        walk(n, np.identity(4), "body")
    return {k: (np.asarray(p, "f4"), prims) for k, (p, prims) in parts.items() if prims}


if __name__ == "__main__":  # self-check: what's written reads back, a head about its pivot
    import os
    import tempfile
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    surf = pygame.Surface((4, 4))
    surf.fill((200, 10, 10))
    png = io.BytesIO()
    pygame.image.save(surf, png, "t.png")
    tri = np.array([[0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 1], [1, 0, 0, 0, 0, 1, 1, 0, 1, 0, 0],
                    [0, 1, 0, 0, 0, 1, 0, 1, 0, 1, 0]], "f4")
    head = tri.copy()
    head[:, 1] += 1.5
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.glb"
        write(p, {"body": (None, [("paint", tri, np.array([0, 1, 2]))]),
                  "head": ((0.0, 1.5, 0.0), [("skin", head, np.array([0, 1, 2]))])},
              {"paint": dict(color=(1, 1, 1, 1), rough=0.9, wear=1.0, png=png.getvalue()),
               "skin": dict(color=(0.8, 0.6, 0.5, 1), rough=0.6)})
        got = load(p)
    assert set(got) == {"body", "head"}
    assert np.allclose(got["head"][0], (0, 1.5, 0)) and np.allclose(got["head"][1][0][0], head), "head in model space"
    v, i, mat, tex = got["body"][1][0]
    assert np.allclose(v, tri) and list(i) == [0, 1, 2] and mat["wear"] == 1.0
    assert tex.get_at((1, 1))[:3] == (200, 10, 10)
    print("gltf ok")
