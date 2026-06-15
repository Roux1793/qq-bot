"""联网搜索 — 用 DuckDuckGo 获取搜索结果，供 LLM 参考"""
import os
import re
from urllib.parse import quote, unquote

import httpx

# Clash 代理（DuckDuckGo 在国内需代理）
_SEARCH_PROXY = os.environ.get("SEARCH_PROXY", "http://127.0.0.1:7897")


def _decode_ddg_url(raw: str) -> str:
    """解码 DuckDuckGo 重定向 URL，提取真实目标 URL"""
    m = re.search(r'uddg=([^&]+)', raw)
    if m:
        return unquote(m.group(1))
    return raw


async def search_web(query: str, num: int = 5) -> list[dict]:
    """搜索网页，返回 [{title, snippet, url}, ...]"""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=12, proxy=_SEARCH_PROXY) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                print(f"[搜索] HTTP {resp.status_code}")
                return []
            html = resp.text
    except Exception as e:
        print(f"[搜索] 请求失败: {e}")
        return []

    # 解析 DuckDuckGo HTML 结果
    results = []
    blocks = re.split(r'<div class="[^"]*result__body[^"]*"', html)[1:]
    for block in blocks:
        # 标题 + 原始 URL（DDG 重定向链接）
        title_m = re.search(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.+?)</a>', block)
        # 摘要（可能包含 <b> 等标签）
        snippet_m = re.search(r'class="result__snippet"[^>]*>(.+?)</a>', block)
        if title_m:
            raw_url = title_m.group(1).strip()
            # 解码 DDG 重定向 URL（uddg= 参数）
            real_url = _decode_ddg_url(raw_url)
            results.append({
                "title": re.sub(r'<[^>]+>', '', title_m.group(2)).strip(),
                "url": real_url,
                "snippet": re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip() if snippet_m else ""
            })
            if len(results) >= num:
                break

    if results:
        print(f"[搜索] 「{query}」→ {len(results)} 条结果")
    return results


def should_search(text: str) -> str | None:
    """判断是否需要联网搜索，返回搜索词或 None"""
    text = text.strip()

    # 明确要求搜索
    if re.search(r"搜索|查一下|帮我查|搜一下|上网搜|查查", text):
        # 提取搜索目标
        for pat in [r"搜索[：:\s]*(.+?)(?:[。！？]|$)", r"查一下[：:\s]*(.+?)(?:[。！？]|$)",
                     r"帮我查[：:\s]*(.+?)(?:[。！？]|$)", r"搜一下[：:\s]*(.+?)(?:[。！？]|$)"]:
            m = re.search(pat, text)
            if m and len(m.group(1).strip()) >= 2:
                return m.group(1).strip()
        # 去掉指令词本身
        cleaned = re.sub(r"(搜索|查一下|帮我查|搜一下|上网搜|查查)[：:\s]*", "", text).strip()
        return cleaned if len(cleaned) >= 2 else text

    # 事实性/知识性问题
    factual_patterns = [
        r"(什么是|什么叫|啥是|定义一下|解释一下)[：:\s]*(.+?)(?:[？?]|$)",
        r"(怎么|如何|怎样)(做|办|处理|解决|实现|配置|安装|部署|使用|写|弄|搞)[：:\s]*(.+?)(?:[？?]|$)",
        r"为什么[：:\s]*(.+?)(?:[？?]|$)",
        r"(.+?)(?:是谁|是什么|是哪|在哪|什么时候|多少钱|怎么样|好不好|行不行|对不对)(?:[？?]|$)",
        r"(最近|今天|昨天|本周|今年).*(?:新闻|事件|发生了|有什么|怎么样)(?:[？?]|$)",
        r"最新.*(?:版本|消息|新闻|进展|情况)(?:[？?]|$)",
        r"(.+?)是(?:谁|什么|什么意思)(?:[？?]|$)",
    ]
    for pat in factual_patterns:
        m = re.search(pat, text)
        if m:
            # 提取完整搜索词
            groups = [g for g in m.groups() if g]
            query = " ".join(groups) if groups else text
            if len(query) >= 3:
                return query

    # 含问号的长句子（更可能是在问问题）
    if "?" in text or "？" in text:
        if len(text) >= 8:
            return re.sub(r"[？?]", "", text).strip()

    return None


def format_search_results(results: list[dict]) -> str:
    """将搜索结果格式化为 LLM 可读的文本"""
    if not results:
        return ""
    lines = ["## 联网搜索结果（仅供参考，请结合你的知识回答）"]
    for i, r in enumerate(results[:5], 1):
        lines.append(f"{i}. **{r['title']}**\n   {r['snippet']}\n   来源: {r['url']}")
    return "\n\n".join(lines)
