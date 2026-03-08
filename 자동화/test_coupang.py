import json
import io
import sys
from coupang_api import search_coupang_product

sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

res = search_coupang_product("로봇청소기", limit=3)
print(json.dumps(res, ensure_ascii=False, indent=2))
