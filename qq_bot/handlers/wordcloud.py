"""词云生成 — 从数据库查询群聊消息，清洗后生成词云图片"""
import collections
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..config import HOME, QQ_ACCOUNT
from ..db import query_messages
from ..send import send_group_msg

# 输出目录
WORDCLOUD_DIR = HOME / "qq-bot" / "wordclouds"

# 中文停用词（无意义高频词 + QQ 聊天噪音）
CN_STOPWORDS = {
    "的", "了", "我", "你", "是", "就", "不", "吧", "也", "都", "在", "和",
    "这", "那", "它", "他", "她", "们", "啊", "呢", "吗", "哦", "嗯", "呀",
    "什么", "怎么", "一个", "这个", "那个", "哪个", "可以", "还是", "没有",
    "但是", "因为", "所以", "如果", "虽然", "然后", "已经", "知道", "觉得",
    "应该", "可能", "不会", "不是", "真的", "哈哈", "哈哈哈", "就是", "有点",
    "一下", "一点", "一些", "很多", "挺", "很", "太", "好", "对", "会", "有",
    "说", "想", "看", "要", "去", "来", "做", "能", "没", "人", "事", "里",
    "上", "下", "中", "大", "小", "多", "少", "过", "着", "得", "让", "把",
    "被", "给", "到", "等", "从", "以", "与", "件", "个", "前", "后",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
}


async def handle_wordcloud(ws, group_id: int, cmd: str):
    """@bot 词云 [天数]"""
    # ── 解析天数 ──
    days = 7
    m = re.search(r"(\d+)\s*天", cmd)
    if m:
        days = int(m.group(1))
    days = max(1, min(days, 30))  # 限制 1-30 天

    await send_group_msg(ws, group_id, f"☁️ 正在生成{days}天词云...")

    t_start = time.time()

    # ── 查询数据库 ──
    since_str = (datetime.now() - timedelta(days=days)).isoformat()
    rows = query_messages(group_id, limit=5000, since=since_str, exclude_user_id=int(QQ_ACCOUNT))

    if not rows:
        await send_group_msg(ws, group_id, f"近{days}天暂无群聊记录~")
        return

    print(f"[词云] 群{group_id} 查询到{len(rows)}条消息 ({time.time()-t_start:.1f}s)")

    # ── 文本清洗 ──
    t_clean_start = time.time()
    all_text = _clean_chat_logs(rows)
    if not all_text or len(all_text) < 20:
        await send_group_msg(ws, group_id, f"近{days}天有效文本太少，无法生成词云~")
        return
    print(f"[词云] 清洗后文本{len(all_text)}字 ({time.time()-t_clean_start:.1f}s)")

    # ── 分词 + 词频统计 ──
    t_cut_start = time.time()
    try:
        import jieba
    except ImportError:
        await send_group_msg(ws, group_id, "词云功能未安装 (jieba)，请联系管理员。")
        return

    word_counts = collections.Counter()
    for word in jieba.cut(all_text, cut_all=False):
        word = word.strip()
        if len(word) < 2:       # 单字跳过
            continue
        if word in CN_STOPWORDS:
            continue
        if re.match(r"^\d+$", word):  # 纯数字跳过
            continue
        word_counts[word] += 1

    if not word_counts:
        await send_group_msg(ws, group_id, "分词后无有效词汇~")
        return

    top_n = word_counts.most_common(200)
    print(f"[词云] 分词完成, 词汇量{len(word_counts)}, top5: {top_n[:5]} ({time.time()-t_cut_start:.1f}s)")

    # ── 生成词云图片 ──
    t_wc_start = time.time()
    try:
        from wordcloud import WordCloud
    except ImportError:
        await send_group_msg(ws, group_id, "词云功能未安装 (wordcloud)，请联系管理员。")
        return

    WORDCLOUD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WORDCLOUD_DIR / f"wc_{group_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    # 找中文字体
    font_path = _find_font()
    if not font_path:
        await send_group_msg(ws, group_id, "未找到中文字体，请联系管理员安装。")
        return

    wc = WordCloud(
        font_path=font_path,
        width=800,
        height=600,
        background_color="white",
        max_words=200,
        max_font_size=120,
        min_font_size=12,
        colormap="viridis",
        random_state=42,
    )
    wc.generate_from_frequencies(dict(top_n))
    wc.to_file(str(out_path))
    wc_size = out_path.stat().st_size
    print(f"[词云] 图片已保存: {out_path} ({wc_size}bytes, {time.time()-t_wc_start:.1f}s)")

    # ── 发送 ──
    from ..send import send_group_msg as sgm
    # NapCat 支持 file:/// 绝对路径
    image_cq = f"[CQ:image,file=file:///{out_path.as_posix()}]"
    await sgm(ws, group_id, image_cq)

    # ── 顺便发词频 TOP10 ──
    top10_lines = ["📊 词频 TOP10："]
    medals = ["🥇", "🥈", "🥉"]
    for i, (word, cnt) in enumerate(top_n[:10]):
        prefix = medals[i] if i < 3 else f"{i+1}."
        top10_lines.append(f"  {prefix} {word}: {cnt}次")
    await sgm(ws, group_id, "\n".join(top10_lines))

    print(f"[词云] 群{group_id} 完成, 总耗时{time.time()-t_start:.1f}s")


def _clean_chat_logs(rows: list[str]) -> str:
    """清洗聊天记录：去时间戳、昵称、CQ码、系统消息"""
    cleaned = []
    for line in rows:
        # 去除 [MM/DD HH:MM] Name: 前缀
        line = re.sub(r"^\[\d\d?/\d\d?\s+\d\d:\d\d\]\s*\S+?\s*:\s*", "", line)
        # 去除 CQ 码（图片、表情、at、回复等）
        line = re.sub(r"\[CQ:[^\]]+\]", "", line)
        # 去除纯符号/空格行
        line = line.strip()
        if not line:
            continue
        # 跳过长度<2或纯数字的行
        if len(line) < 2:
            continue
        if re.match(r"^\d+$", line):
            continue
        # 跳过系统消息
        if any(kw in line for kw in ["撤回了一条消息", "被禁言", "加入群聊", "退出群聊",
                                       "修改群名为", "开启了全员禁言", "投票", "签到"]):
            continue
        cleaned.append(line)
    return " ".join(cleaned)


def _find_font() -> str | None:
    """查找可用的中文字体"""
    candidates = [
        # Ubuntu — Pillow ≥12 支持 .ttc，文泉驿中文覆盖最全
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        # Windows fallback (for local testing)
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None
