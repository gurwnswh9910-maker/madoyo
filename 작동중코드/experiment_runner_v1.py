
import sys
import os
from pathlib import Path
from google import genai
import json

# Add directories to sys.path
base_path = os.getcwd()
sys.path.insert(0, str(Path(base_path) / '작동중코드'))
sys.path.insert(0, str(Path(base_path) / '자동화'))

from scraper import init_driver, scrape_thread_content, fetch_and_rehost
# We'll monkeypatch generator to see the prompt
import copy_generator_v2

original_gen_prompt = copy_generator_v2.DynamicCopyGenerator.generate_prompt
def mocked_generate_prompt(self, *args, **kwargs):
    p = original_gen_prompt(self, *args, **kwargs)
    if not hasattr(self, '_printed_prompt'):
        print("\n--- DEBUG: FIRST PROMPT SENT TO LLM ---")
        print(p[:2000]) # Print first 2000 chars
        print("--- END DEBUG ---\n")
        self._printed_prompt = True
    return p
copy_generator_v2.DynamicCopyGenerator.generate_prompt = mocked_generate_prompt

from optimize_copy_v2 import run_optimization
from marketing_focus_extractor import extract_marketing_focus
from app_config import GlobalConfig

def run_experiment(url, product_name="상품"):
    print(f"\n🚀 Running experiment for: {url}")
    print(f"📦 Product Name: {product_name}")
    
    driver = init_driver()
    client = genai.Client(api_key=GlobalConfig.GEMINI_API_KEY)
    model_name = "gemini-3-flash-preview"
    
    try:
        print("--- Scraping ---")
        post_data = scrape_thread_content(url, driver=driver)
        if not post_data or not post_data.get('text'): return
            
        original_text = post_data['text']
        all_media = post_data['all_media'] if 'all_media' in post_data else post_data['images']
        video_urls_list = post_data.get('video_urls', [])

        print("--- Rehosting ---")
        image_urls = fetch_and_rehost(post_data['images'], driver=driver, video_urls=video_urls_list)
        post_data['image_urls'] = image_urls 

        print("--- Extracting Focus ---")
        marketing_focus = extract_marketing_focus(client, model_name, product_name, original_text, all_media, [])
        print(f"Focus Data: {json.dumps(marketing_focus, ensure_ascii=False)}")

        print("\n--- Optimizing ---")
        shared_resources = {}
        res = run_optimization(original_text, marketing_focus, input_image_urls=all_media, shared_resources=shared_resources)

        if isinstance(res, list):
            print("\n--- RESULTS ---")
            for i, item in enumerate(res[:3]):
                print(f"Rank {i+1}: {item.get('copy', '')[:100]}...")
    finally:
        driver.quit()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        url = sys.argv[1]
        pname = sys.argv[2]
    else:
        url = "https://www.threads.com/@sosopick88/post/DVpeJRRiZDy"
        pname = "일본 파인애플 소화 사탕"
    run_experiment(url, pname)
