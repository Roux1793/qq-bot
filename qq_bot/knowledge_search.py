"""知识库检索 — 加载 MyGO/Ave Mujica 知识库，提供实时查询"""
import re
from pathlib import Path

# 知识库路径（Syncthing 同步目录）
KB_DIR = Path("/home/roux/Mediation/bot-knowledge")

# 预加载索引
_sections: list[dict] = []  # [{title, content, file}]
_loaded = False


def _init():
    """加载并索引知识库"""
    global _sections, _loaded
    if _loaded:
        return
    _loaded = True

    if not KB_DIR.exists():
        print(f"[知识库] 目录不存在: {KB_DIR}")
        return

    for fpath in sorted(KB_DIR.glob("*.md")):
        try:
            text = fpath.read_text(encoding="utf-8")
        except Exception:
            continue

        fname = fpath.name
        # 按 ## 或 ### 分割为节
        sections = re.split(r'\n(?=## )', text)
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            # 提取标题（第一行）
            lines = sec.split('\n')
            title = lines[0].lstrip('#').strip() if lines else ""
            if not title or len(title) < 2:
                continue
            # 跳过目录/导航性质的节
            if title in ("目录", "使用指南", "知识库版本说明", "收录范围说明"):
                continue
            content = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
            if len(content) < 50:
                continue
            _sections.append({
                "title": title,
                "content": content[:3000],  # 每节最多3000字
                "file": fname,
            })

    print(f"[知识库] 已索引 {len(_sections)} 节 (来自 {KB_DIR})")


def search(query: str, top_n: int = 3) -> list[dict]:
    """搜索知识库，返回最相关的节 [{title, content, file, score}, ...]"""
    _init()
    if not _sections:
        return []

    keywords = _tokenize(query)
    if not keywords:
        return []

    scored = []
    for sec in _sections:
        score = 0
        title_lower = sec["title"].lower()
        content_lower = sec["content"].lower()

        for kw in keywords:
            kw_lower = kw.lower()
            # 标题匹配权重高
            if kw_lower in title_lower:
                score += 5
            # 内容匹配
            count = content_lower.count(kw_lower)
            score += min(count, 10)

        if score > 0:
            scored.append({**sec, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def _tokenize(text: str) -> list[str]:
    """简单分词：提取有意义的词组"""
    # 去掉标点和CQ码
    text = re.sub(r'\[CQ:[^\]]+\]', '', text)
    text = re.sub(r'[，。！？、；：""''（）《》【】\s]+', ' ', text)

    words = text.split()
    # 过滤太短的词和停用词
    stopwords = {'的', '了', '是', '在', '我', '你', '他', '她', '它', '们', '这', '那',
                 '吗', '呢', '吧', '啊', '哦', '嗯', '什么', '怎么', '为什么', '哪', '谁',
                 '有', '不', '就', '都', '也', '还', '要', '会', '能', '可以', '说', '对',
                 '给', '让', '把', '和', '与', '或', '但', '如果', '因为', '所以', '然后',
                 '就是', '一个', '这个', '那个', '什么', '怎么', '多少', '请问', '可不可以'}
    keywords = [w for w in words if len(w) >= 2 and w.lower() not in stopwords]
    return keywords[:10]  # 最多10个关键词


def should_query_kb(text: str) -> str | None:
    """判断是否需要查询知识库，返回提取的查询词或None"""
    # 提到的角色或乐队
    names = [
        "丰川祥子", "祥子", "Oblivionis", "三角初华", "初华", "初音", "Doloris",
        "若叶睦", "睦", "Mortis", "墨缇丝", "八幡海铃", "海铃", "Timoris",
        "祐天寺若麦", "若麦", "喵梦", "Amoris", "高松灯", "灯",
        "千早爱音", "爱音", "长崎爽世", "爽世", "素世", "椎名立希", "立希",
        "要乐奈", "乐奈", "纯田真奈", "真奈", "丰川定治", "丰川清告", "丰川瑞穗",
        "CRYCHIC", "MyGO", "Ave Mujica", "Mujica", "sumimi",
        "BanG Dream", "邦邦", "春日影", "迷星叫",
    ]

    matched = []
    text_clean = text.lower()
    for name in names:
        if name.lower() in text_clean:
            matched.append(name)

    if matched:
        return " ".join(matched[:5])

    # 第一人称问题（"你的XX"——对方在问bot本人的信息）
    first_person = [
        r"你的(?:生日|年龄|身高|体重|名字|代号|声优|学校|班级|担当|乐器|代表色|父亲|母亲|爸爸|妈妈|家庭|成员|队友)",
        r"你(?:几岁|多大|多高|是谁|叫什么|是什么|生日是哪天|什么时候出生)",
        r"你(?:和|跟|认识|怎么称呼|怎么叫)(?:灯|爱音|睦|初华|海铃|若麦|爽世|立希|乐奈|祥子)",
        r"(?:灯|爱音|睦|初华|海铃|若麦|爽世|立希|乐奈)(?:和|跟|认识)你",
    ]
    for pat in first_person:
        if re.search(pat, text):
            return "丰川祥子 祥子 " + text.strip()[:30]

    # 问角色信息的问题
    info_patterns = [
        r"(?:生日|年龄|身高|声优|担当|乐器|学校|几岁|多大|谁配音|什么颜色|代表色).*?(?:祥子|灯|爱音|睦|初华|海铃|若麦|爽世|立希|乐奈)",
        r"(?:祥子|灯|爱音|睦|初华|海铃|若麦|爽世|立希|乐奈|CRYCHIC|MyGO|Mujica).*?(?:生日|年龄|身高|声优|担当|乐器|学校|成员|是什么|谁|几岁|多大)",
        r"(?:Ave Mujica|MyGO|CRYCHIC).*?(?:成员|是什么|谁|首演|成立|组建|什么时候)",
        r"(?:怎么称呼|叫什么|怎么叫|称呼是什么|叫.*?什么|关系|认识|和.*?什么关系|是谁|什么人).*?(?:祥子|灯|爱音|睦|初华|海铃|若麦|爽世|立希|乐奈|灯|爽世)",
        r"(?:祥子|灯|爱音|睦|初华|海铃|若麦|爽世|立希|乐奈).*?(?:怎么称呼|叫什么|关系|认识|称呼|喜欢|讨厌|朋友|青梅竹马)",
        r"(?:父亲|母亲|爸爸|妈妈|姐姐|妹妹|哥哥|弟弟|爷爷|奶奶|家族).*?(?:祥子|灯|爱音|睦|初华|海铃|若麦|爽世|立希|乐奈)",
        r"(?:谁).*?(?:祥子|灯|爱音|睦|初华|海铃|若麦|爽世|立希|乐奈).*?(?:的|是|和)",
    ]
    for pat in info_patterns:
        if re.search(pat, text):
            return text.strip()

    return None


def format_kb_results(results: list[dict]) -> str:
    """格式化知识库检索结果为LLM上下文（紧凑格式，优先事实）"""
    if not results:
        return ""
    lines = ["[知识库检索结果 - 以下事实必须严格参照，禁止编造]"]
    total_chars = 0
    for i, r in enumerate(results, 1):
        content = r['content'][:1500]  # 每节最多1500字
        lines.append(f"\n--- {r['title']} ---\n{content}")
        total_chars += len(content)
        if total_chars > 3000:  # 总上限3000字
            break
    return "\n".join(lines)


def build_grounding_prompt(kb_results: list[dict]) -> str:
    """构建grounding验证提示，强制LLM对照检索结果"""
    if not kb_results:
        return ""
    facts = []
    for r in kb_results[:3]:
        # 提取可能的事实性信息
        title = r['title']
        content = r['content'][:800]
        # 找日期、数字等硬事实
        date_matches = re.findall(r'(\d{4}年\d{1,2}月\d{1,2}日|\d{4}年|\d{1,2}月\d{1,2}日|\d+岁|\d+cm|#\w+)', content)
        if date_matches:
            facts.append(f"{title}: {' '.join(date_matches[:5])}")
    if facts:
        return "## 核实清单（回答前对照）\n" + "\n".join(f"- {f}" for f in facts[:8])
    return ""
