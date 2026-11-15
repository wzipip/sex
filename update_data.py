import concurrent.futures
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://apiyutu.com/api.php/providedao/vod/?ac=detail"
LIST_URL = "https://apiyutu.com/api.php/providedao/vod/?ac=list"
MAX_WORKERS = 20
CHUNK_SIZE = 100

def fetch_page(page, retries=5):
    url = f"{BASE_URL}&pg={page}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
                print(f"-> 成功下载第 {page} 页")
                return data.get("list", [])
        except Exception as e:
            print(f"⚠️ 第 {page} 页请求异常，重试 {attempt + 1}...")
            time.sleep((attempt + 1) * 2)
    return []

def main():
    os.makedirs("data", exist_ok=True)

    print("1. 获取官方分类列表，确保与采集站完全一致...")
    official_classes = []
    try:
        req = urllib.request.Request(LIST_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            list_data = json.loads(resp.read().decode("utf-8"))
            official_classes = list_data.get("class", [])
    except Exception as e:
        print(f"⚠️ 获取官方分类列表失败: {e}")

    # 建立 type_id 到分类名的映射，并提取所有官方分类名称
    category_map = {str(c["type_id"]): c["type_name"] for c in official_classes}
    official_category_names = [c["type_name"] for c in official_classes]

    print(f"检测到官方分类: {official_category_names}")

    print("2. 检查采集站总页数...")
    try:
        req = urllib.request.Request(f"{BASE_URL}&pg=1", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            first_res = json.loads(resp.read().decode("utf-8"))
            total_pages = int(first_res.get("pagecount", 1))
    except Exception as e:
        print(f"❌ 无法连接采集站: {e}")
        return

    # 全量或增量抓取
    has_local_data = os.path.exists("data/categories.json")
    existing_videos_map = {}
    if has_local_data:
        try:
            with open("data/categories.json", "r", encoding="utf-8") as f:
                cat_index = json.load(f)
            for cat in cat_index:
                files = [cat.get("file")] if "file" in cat else cat.get("files", [])
                for fname in files:
                    fpath = os.path.join("data", fname)
                    if os.path.exists(fpath):
                        with open(fpath, "r", encoding="utf-8") as f:
                            for vod in json.load(f):
                                existing_videos_map[str(vod["id"])] = vod
            print(f"成功加载本地缓存: {len(existing_videos_map)} 条")
        except Exception:
            existing_videos_map = {}

    pages_to_fetch = list(range(1, total_pages + 1)) if not existing_videos_map else list(range(1, min(25, total_pages) + 1))
    
    print(f"开始抓取数据，共需请求 {len(pages_to_fetch)} 页...")
    fetched_videos = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = executor.map(fetch_page, pages_to_fetch)
        for page_list in results:
            if page_list:
                fetched_videos.extend(page_list)

    for vod in fetched_videos:
        vod_id = str(vod.get("vod_id"))
        type_id = str(vod.get("type_id", ""))
        category = vod.get("type_name", "")
        if not category and type_id in category_map:
            category = category_map[type_id]
        if not category:
            category = "Uncategorized"

        play_url_raw = vod.get("vod_play_url", "")
        episodes = []
        if play_url_raw:
            for p in play_url_raw.split("#"):
                if "$" in p:
                    sub = p.split("$")
                    if len(sub) >= 2:
                        episodes.append({"name": sub[-2], "url": sub[-1]})

        item = {
            "id": vod.get("vod_id"),
            "title": vod.get("vod_name", ""),
            "category": category,
            "pic": vod.get("vod_pic", ""),
            "year": vod.get("vod_year", ""),
            "area": vod.get("vod_area", ""),
            "actor": vod.get("vod_actor", ""),
            "director": vod.get("vod_director", ""),
            "content": vod.get("vod_content", "").strip(),
            "episodes": episodes,
        }
        existing_videos_map[vod_id] = item

    all_videos = list(existing_videos_map.values())
    all_videos.sort(key=lambda x: int(x.get("id", 0)), reverse=True)

    # 严格按官方分类归类，确保每个官方分类都有条目（即使为空也能正确生成索引）
    categories_dict = {c: [] for c in official_category_names}
    categories_dict["Uncategorized"] = []

    for vod in all_videos:
        cat = vod.get("category", "Uncategorized")
        if cat not in categories_dict:
            categories_dict[cat] = []
        categories_dict[cat].append(vod)

    cat_index = []
    
    # 最新发布
    latest_items = all_videos[:120]
    with open(os.path.join("data", "cat_latest.json"), "w", encoding="utf-8") as f:
        json.dump(latest_items, f, ensure_ascii=False)
    cat_index.append({"name": "🔥 Latest Releases", "count": len(latest_items), "file": "cat_latest.json"})

    vod_file_map = {}

    # 生成各分类分片
    for c_name, v_list in categories_dict.items():
        safe_hash = hashlib.md5(c_name.encode("utf-8")).hexdigest()[:10]
        if not v_list:
            # 即使分类暂无视频，也生成一个空文件，避免前端请求报错
            file_name = f"cat_{safe_hash}.json"
            with open(os.path.join("data", file_name), "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False)
            cat_index.append({"name": c_name, "count": 0, "file": file_name})
            continue

        if len(v_list) > CHUNK_SIZE:
            sub_files = []
            for i in range(0, len(v_list), CHUNK_SIZE):
                chunk = v_list[i : i + CHUNK_SIZE]
                chunk_file = f"cat_{safe_hash}_part{i // CHUNK_SIZE + 1}.json"
                for vod in chunk:
                    vod_file_map[str(vod.get("id"))] = chunk_file
                with open(os.path.join("data", chunk_file), "w", encoding="utf-8") as f:
                    json.dump(chunk, f, ensure_ascii=False)
                sub_files.append(chunk_file)
            cat_index.append({"name": c_name, "count": len(v_list), "files": sub_files})
        else:
            file_name = f"cat_{safe_hash}.json"
            for vod in v_list:
                vod_file_map[str(vod.get("id"))] = file_name
            with open(os.path.join("data", file_name), "w", encoding="utf-8") as f:
                json.dump(v_list, f, ensure_ascii=False)
            cat_index.append({"name": c_name, "count": len(v_list), "file": file_name})

    with open("data/categories.json", "w", encoding="utf-8",) as f:
        json.dump(cat_index, f, ensure_ascii=False, indent=2)

    with open("data/vod_lookup.json", "w", encoding="utf-8") as f:
        json.dump(vod_file_map, f, ensure_ascii=False, separators=(",", ":"))

    print(f"✅ 数据同步完成！总收录: {len(all_videos)} 个视频，分类数: {len(cat_index)}")

if __name__ == "__main__":
    main()
