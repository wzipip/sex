import concurrent.futures
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# 🎯 已彻底更新为新采集源接口
BASE_URL = "https://apiyutu.com/api.php/providedao/vod/?ac=detail"
LIST_URL = "https://apiyutu.com/api.php/providedao/vod/?ac=list"

MAX_WORKERS = 10
CHUNK_SIZE = 100  # 严格控制分片大小

# 中文采集分类到极简英文分类的严格映射
CATEGORY_MAP_EN = {
    "精品推荐": "Featured",
    "主播秀色": "Cam Girls",
    "日本有码": "JP Censored",
    "日本无码": "JP Uncensored",
    "中文字幕": "CN Subtitles",
    "童颜巨乳": "Busty Petite",
    "性感人妻": "Sexy Wives",
    "强奸乱伦": "Taboo / Incest",
    "欧美情色": "Western",
    "三级伦理": "Cat III",
    "卡通动漫": "Anime",
    "丝袜OL": "Stockings OL",
    "自拍偷拍": "Amateur",
    "日本片商": "JP Studios",
    "剧情介绍": "Plot",
    "网曝系列": "Leaked",
    "同性恋": "LGBT",
    "探花嫖娼": "Escort",
    "国产人妻": "CN Wives",
    "国产SM": "CN BDSM",
    "国产丝袜": "CN Stockings",
    "麻豆传媒": "Madou",
    "国产乱伦": "CN Taboo",
    "明星换脸": "Deepfake",
    "主奴调教": "Dominance",
    "凌辱快感": "Humiliation",
    "多人群交": "Orgy",
    "角色剧情": "Roleplay",
    "港台辣妹": "HK & TW",
    "重口性癖": "Hardcore",
    "变性伪娘": "Trans / Femboy",
    "VR视角": "VR",
}

ORDERED_ENGLISH_CATEGORIES = [
    "Featured", "Cam Girls", "JP Censored", "JP Uncensored",
    "CN Subtitles", "Busty Petite", "Sexy Wives", "Taboo / Incest",
    "Western", "Cat III", "Anime", "Stockings OL",
    "Amateur", "JP Studios", "Plot", "Leaked",
    "LGBT", "Escort", "CN Wives", "CN BDSM",
    "CN Stockings", "Madou", "CN Taboo", "Deepfake",
    "Dominance", "Humiliation", "Orgy", "Roleplay",
    "HK & TW", "Hardcore", "Trans / Femboy", "VR"
]


def fetch_page(page, retries=5):
  url = f"{BASE_URL}&pg={page}"
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }
  for attempt in range(retries):
    try:
      req = urllib.request.Request(url, headers=headers)
      with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
        print(f"-> 成功下载第 {page} 页")
        return data.get("list", [])
    except Exception as e:
      print(
          f"⚠️ 第 {page} 页请求异常，正在进行第 {attempt + 1} 次重试..."
      )
      time.sleep((attempt + 1) * 3)
  print(f"❌ 第 {page} 页连续重试失败，已跳过")
  return []


def main():
  os.makedirs("data", exist_ok=True)

  print("1. 获取官方分类列表...")
  try:
    req = urllib.request.Request(
        LIST_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
      list_data = json.loads(resp.read().decode("utf-8"))
      official_classes = list_data.get("class", [])
  except Exception:
    official_classes = []

  category_map = {str(c["type_id"]): c["type_name"] for c in official_classes}

  has_local_data = os.path.exists("data/categories.json")

  print("2. 检查采集站状态...")
  try:
    req = urllib.request.Request(
        f"{BASE_URL}&pg=1", headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
      first_res = json.loads(resp.read().decode("utf-8"))
  except Exception as e:
    print(f"Failed to fetch page 1: {e}")
    return

  total_pages = int(first_res.get("pagecount", 1))

  existing_videos_map = {}
  if has_local_data:
    print(
        "⚡ 检测到本地已有数据库，执行【增量更新模式】（只抓取最近更新的前几页）..."
    )
    try:
      with open("data/categories.json", "r", encoding="utf-8") as f:
        cat_index = json.load(f)
      for cat in cat_index:
        files = []
        if "file" in cat:
          files.append(cat["file"])
        if "files" in cat:
          files.extend(cat["files"])
        for fname in files:
          fpath = os.path.join("data", fname)
          if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
              chunk_data = json.load(f)
              for vod in chunk_data:
                existing_videos_map[str(vod["id"])] = vod
      print(f"成功加载本地现有影视数据: {len(existing_videos_map)} 条")
    except Exception as e:
      print(f"读取本地缓存出错，将转为全量采集: {e}")
      existing_videos_map = {}

  if not existing_videos_map:
    print(f"🔥 本地无数据，执行【首次全量采集】共 {total_pages} 页...")
    pages_to_fetch = list(range(1, total_pages + 1))
  else:
    fetch_pages_count = min(20, total_pages)
    print(f"⚡ 开始增量拉取最新更新的前 {fetch_pages_count} 页...")
    pages_to_fetch = list(range(1, fetch_pages_count + 1))

  fetched_videos = []
  with concurrent.futures.ThreadPoolExecutor(
      max_workers=MAX_WORKERS
  ) as executor:
    results = executor.map(fetch_page, pages_to_fetch)
    for page_list in results:
      if page_list:
        fetched_videos.extend(page_list)

  print(f"本次抓取到数据: {len(fetched_videos)} 条")

  for vod in fetched_videos:
    vod_id = str(vod.get("vod_id"))
    title = vod.get("vod_name", "")

    type_id = str(vod.get("type_id", ""))
    raw_category = vod.get("type_name", "")
    if not raw_category and type_id in category_map:
      raw_category = category_map[type_id]
    
    category = CATEGORY_MAP_EN.get(raw_category, raw_category if raw_category else "Uncategorized")

    pic = vod.get("vod_pic", "")
    year = vod.get("vod_year", "")
    area = vod.get("vod_area", "")
    actor = vod.get("vod_actor", "")
    director = vod.get("vod_director", "")
    content = vod.get("vod_content", "").strip()
    play_url_raw = vod.get("vod_play_url", "")

    episodes = []
    if play_url_raw:
      parts = play_url_raw.split("#")
      for p in parts:
        if "$" in p:
          sub_parts = p.split("$")
          if len(sub_parts) >= 2:
            ep_name = sub_parts[-2]
            ep_link = sub_parts[-1]
            if ".m3u8" in ep_link or ".mp4" in ep_link or "http" in ep_link:
              episodes.append({"name": ep_name, "url": ep_link})

    item = {
        "id": vod.get("vod_id"),
        "title": title,
        "category": category,
        "pic": pic,
        "year": year,
        "area": area,
        "actor": actor,
        "director": director,
        "content": content,
        "episodes": episodes,
    }
    existing_videos_map[vod_id] = item

  all_videos = list(existing_videos_map.values())
  all_videos.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
  print(f"合并并排序后总影视库数据: {len(all_videos)} 条")

  processed_videos = all_videos
  categories = {c_name: [] for c_name in ORDERED_ENGLISH_CATEGORIES}
  categories["Uncategorized"] = []

  for vod in processed_videos:
    cat = vod.get("category", "Uncategorized")
    if cat not in categories:
      categories[cat] = []
    categories[cat].append(vod)

  cat_index = []

  latest_items = processed_videos[:100]
  with open(os.path.join("data", "cat_latest.json"), "w", encoding="utf-8") as f:
    json.dump(latest_items, f, ensure_ascii=False, indent=2)
  cat_index.append(
      {"name": "🔥 Latest Releases", "count": len(latest_items), "file": "cat_latest.json"}
  )

  all_cats = list(ORDERED_ENGLISH_CATEGORIES)
  for c_name in categories.keys():
    if c_name not in all_cats:
      all_cats.append(c_name)

  vod_file_map = {}

  for c_name in all_cats:
    v_list = categories.get(c_name, [])
    if not v_list:
      continue

    safe_hash = hashlib.md5(c_name.encode("utf-8")).hexdigest()[:10]

    if len(v_list) > CHUNK_SIZE:
      sub_files = []
      for i in range(0, len(v_list), CHUNK_SIZE):
        chunk = v_list[i : i + CHUNK_SIZE]
        chunk_file = f"cat_{safe_hash}_part{i // CHUNK_SIZE + 1}.json"

        for vod in chunk:
          vod["data_file"] = chunk_file
          vod_file_map[str(vod.get("id"))] = chunk_file

        with open(os.path.join("data", chunk_file), "w", encoding="utf-8") as f:
          json.dump(chunk, f, ensure_ascii=False)
        sub_files.append(chunk_file)
      cat_index.append(
          {"name": c_name, "count": len(v_list), "files": sub_files}
      )
    else:
      file_name = f"cat_{safe_hash}.json"
      for vod in v_list:
        vod["data_file"] = file_name
        vod_file_map[str(vod.get("id"))] = file_name

      with open(os.path.join("data", file_name), "w", encoding="utf-8") as f:
        json.dump(v_list, f, ensure_ascii=False)
      cat_index.append(
          {"name": c_name, "count": len(v_list), "file": file_name}
      )

  with open("data/categories.json", "w", encoding="utf-8") as f:
    json.dump(cat_index, f, ensure_ascii=False, indent=2)

  search_index = []
  for vod in processed_videos:
    search_index.append({
        "id": vod.get("id"),
        "title": vod.get("title"),
        "category": vod.get("category"),
        "pic": vod.get("pic"),
        "actor": vod.get("actor"),
        "year": vod.get("year"),
        "data_file": vod.get("data_file"),
    })
  with open(
      os.path.join("data", "search_index.json"), "w", encoding="utf-8"
  ) as f:
    json.dump(search_index, f, ensure_ascii=False)

  with open(
      os.path.join("data", "vod_lookup.json"), "w", encoding="utf-8"
  ) as f:
    json.dump(vod_file_map, f, ensure_ascii=False, separators=(",", ":"))

  print("3. 正在清理过期的旧分片文件...")
  active_files = set()
  for cat in cat_index:
    if "file" in cat:
      active_files.add(cat["file"])
    if "files" in cat:
      active_files.update(cat["files"])
  active_files.add("categories.json")
  active_files.add("search_index.json")
  active_files.add("vod_lookup.json")

  cleaned_count = 0
  for filename in os.listdir("data"):
    if filename.endswith(".json") and filename not in active_files:
      try:
        os.remove(os.path.join("data", filename))
        cleaned_count += 1
      except Exception:
        pass
  print(f"✅ 成功清理过期旧分片: {cleaned_count} 个")

  print("4. 生成 Sitemap 索引与分片...")
  DOMAIN = "https://x.ftp1.biz"  # 如果绑定了新域名，请在此处修改
  os.makedirs("sitemaps", exist_ok=True)

  base_sitemap_lines = [
      '<?xml version="1.0" encoding="UTF-8"?>',
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
      f"  <url><loc>{DOMAIN}/index.html</loc><changefreq>always</changefreq><priority>1.0</priority></url>",
  ]
  for c_name in ORDERED_ENGLISH_CATEGORIES:
    encoded_cat = urllib.parse.quote(c_name)
    base_sitemap_lines.extend([
        f"  <url><loc>{DOMAIN}/index.html?cat={encoded_cat}</loc><changefreq>hourly</changefreq><priority>0.8</priority></url>"
    ])
  base_sitemap_lines.append("</urlset>")
  with open("sitemaps/sitemap_base.xml", "w", encoding="utf-8") as f:
    f.write("\n".join(base_sitemap_lines))

  video_sitemap_files = ["sitemap_base.xml"]
  chunk_size_sitemap = 5000
  for i in range(0, len(processed_videos), chunk_size_sitemap):
    chunk = processed_videos[i : i + chunk_size_sitemap]
    part_num = (i // chunk_size_sitemap) + 1
    v_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for vod in chunk:
      vod_id = vod.get("id")
      vod_cat = urllib.parse.quote(vod.get("category", "Uncategorized"))
      v_lines.append(
          f"  <url><loc>{DOMAIN}/play.html?id={vod_id}&amp;cat={vod_cat}</loc><changefreq>daily</changefreq><priority>0.6</priority></url>"
      )
    v_lines.append("</urlset>")

    part_filename = f"sitemap_videos_{part_num}.xml"
    with open(os.path.join("sitemaps", part_filename), "w", encoding="utf-8") as f:
      f.write("\n".join(v_lines))
    video_sitemap_files.append(part_filename)

  index_lines = [
      '<?xml version="1.0" encoding="UTF-8"?>',
      '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ]
  for sm_file in video_sitemap_files:
    index_lines.extend([
        "  <sitemap>",
        f"    <loc>{DOMAIN}/sitemaps/{sm_file}</loc>",
        "  </sitemap>",
    ])
  index_lines.append("</sitemapindex>")

  with open("sitemap.xml", "w", encoding="utf-8") as f:
    f.write("\n".join(index_lines))

  print(
      f"✅ 同步完成，收录影视: {len(processed_videos)} 个，Sitemap 索引已成功生成！"
  )


if __name__ == "__main__":
  main()
