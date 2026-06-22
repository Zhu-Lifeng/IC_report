"""
Hampton Tower 物业管理 · IC 报告系统
Flask 后端 — 所有数据存在 data/*.json，照片存在 uploads/

启动：
    pip install flask
    python app.py
访问：http://localhost:5000
"""
import json, os, uuid, re, base64
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory, Response

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024   # 300 MB（base64 照片可能较大）

BASE   = os.path.dirname(__file__)
DATA   = os.path.join(BASE, "data")
UPLOAD = os.path.join(BASE, "uploads")
SEED   = os.path.join(BASE, "seed.json")

os.makedirs(DATA,   exist_ok=True)
os.makedirs(UPLOAD, exist_ok=True)


# ── 工具函数 ──────────────────────────────────────────────

def uid(prefix="id"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def df(name):
    return os.path.join(DATA, f"{name}.json")

def load(name):
    try:
        with open(df(name), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save(name, data):
    with open(df(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_photo(data_url: str) -> str:
    """base64 dataURL → 文件，返回 /uploads/xxx.jpg 路径。"""
    m = re.match(r"data:image/(\w+);base64,(.+)", data_url, re.DOTALL)
    if not m:
        return data_url   # 非标准格式原样返回
    ext = "jpg" if m.group(1).lower() in ("jpeg", "jpg") else m.group(1).lower()
    fname = uid("photo") + "." + ext
    with open(os.path.join(UPLOAD, fname), "wb") as f:
        f.write(base64.b64decode(m.group(2)))
    return f"/uploads/{fname}"

def delete_photo(url: str):
    if url and url.startswith("/uploads/"):
        path = os.path.join(UPLOAD, url[len("/uploads/"):])
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

def purge_report_photos(report: dict):
    for urls in report.get("photos", {}).values():
        for u in (urls or []):
            delete_photo(u)


# ── 初始化（从 seed.json 生成 data/*.json） ──────────────

def init_from_seed():
    """首次运行时从 seed.json 构建初始数据文件。"""
    if os.path.exists(df("houseTypes")):
        return
    try:
        with open(SEED, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        save("houseTypes", [])
        save("properties", [])
        save("reports",    [])
        return

    house_types = []
    for ht in raw.get("houseTypes", []):
        rooms = []
        for r in ht.get("rooms", []):
            items = (
                [{"id": f"{r['id']}_f{i}",   "name": n, "type": "facility"}
                 for i, n in enumerate(r.get("facilities", []))] +
                [{"id": f"{r['id']}_fur{i}", "name": n, "type": "furniture"}
                 for i, n in enumerate(r.get("furniture", []))]
            )
            rooms.append({"id": r["id"], "name": r["name"], "items": items})
        house_types.append({"id": ht["id"], "name": ht["name"], "rooms": rooms})
    save("houseTypes", house_types)

    ht_map = {h["id"]: h for h in house_types}
    properties = []
    for p in raw.get("properties", []):
        ht = ht_map.get(p["houseTypeId"])
        if not ht:
            continue
        rooms = [
            {
                "id":    f"{p['id']}_{r['id']}",
                "name":  r["name"],
                "items": [{"id": f"{p['id']}_{it['id']}", "name": it["name"], "type": it["type"]}
                          for it in r["items"]],
            }
            for r in ht["rooms"]
        ]
        properties.append({
            "id":          p["id"],
            "name":        p["name"],
            "address":     p.get("address", ""),
            "houseTypeId": p["houseTypeId"],
            "status":      "idle",
            "createdAt":   p.get("createdAt", datetime.now().date().isoformat()),
            "rooms":       rooms,
        })
    save("properties", properties)
    save("reports",    [])


init_from_seed()


# ── 页面路由 ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD, filename)


# ── 户型模板 API ──────────────────────────────────────────

@app.route("/api/housetypes", methods=["GET"])
def get_hts():
    return jsonify(load("houseTypes"))

@app.route("/api/housetypes", methods=["POST"])
def create_ht():
    d = request.json
    ht = {"id": uid("ht"), "name": d["name"], "rooms": []}
    hts = load("houseTypes")
    hts.append(ht)
    save("houseTypes", hts)
    return jsonify(ht), 201

@app.route("/api/housetypes/<htid>", methods=["PUT"])
def update_ht(htid):
    hts = load("houseTypes")
    ht = next((h for h in hts if h["id"] == htid), None)
    if not ht:
        return jsonify({"error": "not found"}), 404
    ht["name"] = request.json["name"]
    save("houseTypes", hts)
    return jsonify(ht)

@app.route("/api/housetypes/<htid>", methods=["DELETE"])
def delete_ht(htid):
    save("houseTypes", [h for h in load("houseTypes") if h["id"] != htid])
    return "", 204

# 户型 → 房间
@app.route("/api/housetypes/<htid>/rooms", methods=["POST"])
def add_ht_room(htid):
    hts = load("houseTypes")
    ht = next((h for h in hts if h["id"] == htid), None)
    if not ht:
        return jsonify({"error": "not found"}), 404
    room = {"id": uid("r"), "name": request.json["name"], "items": []}
    ht["rooms"].append(room)
    save("houseTypes", hts)
    return jsonify(room), 201

@app.route("/api/housetypes/<htid>/rooms/<rid>", methods=["PUT"])
def update_ht_room(htid, rid):
    hts = load("houseTypes")
    ht   = next((h for h in hts if h["id"] == htid), None)
    room = next((r for r in (ht or {}).get("rooms", []) if r["id"] == rid), None)
    if not room:
        return jsonify({"error": "not found"}), 404
    room["name"] = request.json["name"]
    save("houseTypes", hts)
    return jsonify(room)

@app.route("/api/housetypes/<htid>/rooms/<rid>", methods=["DELETE"])
def delete_ht_room(htid, rid):
    hts = load("houseTypes")
    ht  = next((h for h in hts if h["id"] == htid), None)
    if not ht:
        return jsonify({"error": "not found"}), 404
    ht["rooms"] = [r for r in ht["rooms"] if r["id"] != rid]
    save("houseTypes", hts)
    return "", 204

# 户型 → 条目
@app.route("/api/housetypes/<htid>/rooms/<rid>/items", methods=["POST"])
def add_ht_item(htid, rid):
    hts  = load("houseTypes")
    ht   = next((h for h in hts if h["id"] == htid), None)
    room = next((r for r in (ht or {}).get("rooms", []) if r["id"] == rid), None)
    if not room:
        return jsonify({"error": "not found"}), 404
    d    = request.json
    item = {"id": uid("i"), "name": d["name"], "type": d["type"]}
    room["items"].append(item)
    save("houseTypes", hts)
    return jsonify(item), 201

@app.route("/api/housetypes/<htid>/rooms/<rid>/items/<iid>", methods=["PUT"])
def update_ht_item(htid, rid, iid):
    hts  = load("houseTypes")
    ht   = next((h for h in hts if h["id"] == htid), None)
    room = next((r for r in (ht or {}).get("rooms", []) if r["id"] == rid), None)
    item = next((i for i in (room or {}).get("items", []) if i["id"] == iid), None)
    if not item:
        return jsonify({"error": "not found"}), 404
    d = request.json
    item.update({"name": d["name"], "type": d["type"]})
    save("houseTypes", hts)
    return jsonify(item)

@app.route("/api/housetypes/<htid>/rooms/<rid>/items/<iid>", methods=["DELETE"])
def delete_ht_item(htid, rid, iid):
    hts  = load("houseTypes")
    ht   = next((h for h in hts if h["id"] == htid), None)
    room = next((r for r in (ht or {}).get("rooms", []) if r["id"] == rid), None)
    if not room:
        return jsonify({"error": "not found"}), 404
    room["items"] = [i for i in room["items"] if i["id"] != iid]
    save("houseTypes", hts)
    return "", 204


# ── 物业 API ──────────────────────────────────────────────

@app.route("/api/properties", methods=["GET"])
def get_props():
    return jsonify(load("properties"))

@app.route("/api/properties", methods=["POST"])
def create_prop():
    d  = request.json
    ht = next((h for h in load("houseTypes") if h["id"] == d["houseTypeId"]), None)
    if not ht:
        return jsonify({"error": "户型不存在"}), 404
    pid   = uid("p")
    rooms = [
        {
            "id":    uid("pr"),
            "name":  r["name"],
            "items": [{"id": uid("pi"), "name": it["name"], "type": it["type"]}
                      for it in r["items"]],
        }
        for r in ht["rooms"]
    ]
    prop = {
        "id":          pid,
        "name":        d["name"],
        "address":     d.get("address", ""),
        "houseTypeId": d["houseTypeId"],
        "status":      "idle",
        "createdAt":   datetime.now().isoformat(),
        "rooms":       rooms,
    }
    props = load("properties")
    props.append(prop)
    save("properties", props)
    return jsonify(prop), 201

@app.route("/api/properties/<pid>", methods=["PUT"])
def update_prop(pid):
    """更新物业名称、地址、房间结构（编辑器保存时调用）。"""
    d     = request.json
    props = load("properties")
    prop  = next((p for p in props if p["id"] == pid), None)
    if not prop:
        return jsonify({"error": "not found"}), 404
    for k in ("name", "address", "rooms"):
        if k in d:
            prop[k] = d[k]
    save("properties", props)
    return jsonify(prop)

@app.route("/api/properties/<pid>", methods=["DELETE"])
def delete_prop(pid):
    save("properties", [p for p in load("properties") if p["id"] != pid])
    reports = load("reports")
    keep, remove = [], []
    for r in reports:
        (remove if r["propertyId"] == pid else keep).append(r)
    for r in remove:
        purge_report_photos(r)
    save("reports", keep)
    return "", 204

# 物业状态操作
@app.route("/api/properties/<pid>/checkin", methods=["POST"])
def checkin(pid):
    d     = request.json   # {photos: {itemId: [base64, ...]}}
    props = load("properties")
    prop  = next((p for p in props if p["id"] == pid), None)
    if not prop:
        return jsonify({"error": "not found"}), 404
    if prop["status"] != "idle":
        return jsonify({"error": f"当前状态 {prop['status']}，无法 check-in"}), 400

    photos = {}
    for iid, urls in d.get("photos", {}).items():
        photos[iid] = [save_photo(u) for u in (urls or []) if u]

    report = {
        "id":         uid("rep"),
        "propertyId": pid,
        "type":       "check-in",
        "createdAt":  datetime.now().isoformat(),
        "photos":     photos,
    }
    reports = load("reports")
    reports.append(report)
    save("reports", reports)
    prop["status"] = "renting"
    save("properties", props)
    return jsonify(report), 201

@app.route("/api/properties/<pid>/checkout", methods=["POST"])
def checkout(pid):
    d     = request.json   # {baselineReportId, photos: {itemId: [base64|null, ...]}}
    props = load("properties")
    prop  = next((p for p in props if p["id"] == pid), None)
    if not prop:
        return jsonify({"error": "not found"}), 404
    if prop["status"] != "renting":
        return jsonify({"error": f"当前状态 {prop['status']}，无法 check-out"}), 400

    reports  = load("reports")
    baseline = next((r for r in reports if r["id"] == d.get("baselineReportId")), None)
    if not baseline:
        return jsonify({"error": "找不到对应的 check-in 报告"}), 400

    photos = {}
    for iid, urls in d.get("photos", {}).items():
        photos[iid] = [(save_photo(u) if u else None) for u in (urls or [])]

    report = {
        "id":               uid("rep"),
        "propertyId":       pid,
        "type":             "check-out",
        "createdAt":        datetime.now().isoformat(),
        "baselineReportId": d["baselineReportId"],
        "photos":           photos,
    }
    reports.append(report)
    save("reports", reports)
    prop["status"] = "preparing"
    save("properties", props)
    return jsonify(report), 201

@app.route("/api/properties/<pid>/finishprep", methods=["POST"])
def finish_prep(pid):
    props = load("properties")
    prop  = next((p for p in props if p["id"] == pid), None)
    if not prop:
        return jsonify({"error": "not found"}), 404
    prop["status"] = "idle"
    save("properties", props)
    return jsonify(prop)


# ── 报告 API ──────────────────────────────────────────────

@app.route("/api/reports", methods=["GET"])
def get_reports():
    return jsonify(load("reports"))

@app.route("/api/reports/<rid>", methods=["DELETE"])
def delete_report(rid):
    reports = load("reports")
    target  = next((r for r in reports if r["id"] == rid), None)
    if target:
        purge_report_photos(target)
    save("reports", [r for r in reports if r["id"] != rid])
    return "", 204


# ── 数据管理 API ──────────────────────────────────────────

@app.route("/api/export")
def export_data():
    data  = {"houseTypes": load("houseTypes"), "properties": load("properties"), "reports": load("reports")}
    fname = f"backup-{datetime.now().strftime('%Y-%m-%d')}.json"
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )

@app.route("/api/import", methods=["POST"])
def import_data():
    d = request.json
    if not all(k in d for k in ("houseTypes", "properties", "reports")):
        return jsonify({"error": "数据结构不完整（需含 houseTypes/properties/reports）"}), 400
    save("houseTypes", d["houseTypes"])
    save("properties", d["properties"])
    save("reports",    d["reports"])
    return jsonify({"ok": True})

@app.route("/api/reset", methods=["POST"])
def reset_data():
    for r in load("reports"):
        purge_report_photos(r)
    for name in ("houseTypes", "properties", "reports"):
        path = df(name)
        if os.path.exists(path):
            os.remove(path)
    init_from_seed()
    return jsonify({"ok": True})


# ── 入口 ──────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
