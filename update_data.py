import requests
import json
import os

# 采集配置 (JSON倒序采集接口)
API_URL = "https://apiyutu.com/api.php/providedao/vod/?ac=list"
PLAYER_URL = "https://yutujx.com/?url="
CHUNK_SIZE = 200

def fetch_data():
    try:
        response = requests.get(API_URL, timeout=15)
        data = response.json()
        return data.get('list', [])
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

def main():
    videos = fetch_data()
    if not videos:
        print("No videos fetched.")
        return

    os.makedirs('data', exist_ok=True)
    
    total_videos = len(videos)
    chunks = [videos[i:i + CHUNK_SIZE] for i in range(0, total_videos, CHUNK_SIZE)]
    
    for idx, chunk in enumerate(chunks):
        with open(f'data/list_{idx+1}.json', 'w', encoding='utf-8') as f:
            json.dump(chunk, f, ensure_ascii=False)
            
    meta = {
        "total": total_videos,
        "chunks": len(chunks),
        "player_prefix": PLAYER_URL
    }
    with open('data/meta.json', 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
        
    print(f"Successfully updated {total_videos} videos into {len(chunks)} chunks.")

if __name__ == '__main__':
    main()
