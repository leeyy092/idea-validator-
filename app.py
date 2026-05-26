import html
import os
import re
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# (provider, env 变量名列表, 默认模型, 显示名)
LLM_OPTIONS = (
    ("moonshot", ("MOONSHOT_API_KEY", "KIMI_API_KEY"), "moonshot-v1-32k", "Kimi"),
    ("deepseek", ("DEEPSEEK_API_KEY",), "deepseek-chat", "DeepSeek"),
    ("openrouter", ("OPENROUTER_API_KEY",), "anthropic/claude-3.5-sonnet", "OpenRouter"),
    ("anthropic", ("ANTHROPIC_API_KEY",), "claude-sonnet-4-6", "Claude"),
)


def get_secret(name):
    val = (os.getenv(name) or "").strip()
    if not val:
        try:
            val = (st.secrets.get(name) or "").strip()
        except Exception:
            pass
    return val


def get_provider_key(env_names):
    for name in env_names:
        key = get_secret(name)
        if key:
            return key, name
    return None, None


def resolve_llm():
    preferred = get_secret("LLM_PROVIDER").lower()
    custom_model = get_secret("MOONSHOT_MODEL") or get_secret("LLM_MODEL")

    def pack(provider, key, model, label, env_name):
        if provider == "moonshot" and custom_model:
            model = custom_model
        return provider, key, model, label, env_name

    if preferred:
        for provider, env_names, model, label in LLM_OPTIONS:
            if provider == preferred:
                key, env_name = get_provider_key(env_names)
                if key:
                    return pack(provider, key, model, label, env_name)
    for provider, env_names, model, label in LLM_OPTIONS:
        key, env_name = get_provider_key(env_names)
        if key:
            return pack(provider, key, model, label, env_name)
    return None, None, None, None, None


def chat_completion_http(base_url, api_key, model, prompt, max_tokens, temperature, extra_headers=None):
    """用 Python 内置库调用 OpenAI 兼容接口，无需安装 openai 包。"""
    import json
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e

    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"API 返回格式异常: {data}") from e


def call_llm(prompt, max_tokens=600, temperature=0.6):
    provider, api_key, model, _, _ = resolve_llm()
    if not provider:
        raise RuntimeError("未配置 API Key")

    if provider == "anthropic":
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    base_urls = {
        "moonshot": get_secret("MOONSHOT_BASE_URL") or "https://api.moonshot.cn/v1",
        "deepseek": "https://api.deepseek.com",
        "openrouter": "https://openrouter.ai/api/v1",
    }
    extra = None
    if provider == "openrouter":
        extra = {"HTTP-Referer": "https://jucaiyy.com", "X-Title": "聚才想法验真"}

    return chat_completion_http(
        base_urls[provider],
        api_key,
        model,
        prompt,
        max_tokens,
        temperature,
        extra_headers=extra,
    )


def friendly_api_error(exc):
    msg = str(exc).lower()
    if "401" in msg or "authentication" in msg or ("invalid" in msg and "key" in msg):
        return (
            "**API Key 无效或已过期。**\n\n"
            "**若用 Kimi：** 到 https://platform.moonshot.cn/ 创建 **API Key**"
            "（App 会员 ≠ API Key）。Secrets 里写：\n"
            '`MOONSHOT_API_KEY = "sk-..."`\n\n'
            "并**删除**旧的 `ANTHROPIC_API_KEY`，然后 Save → Reboot app。"
        )
    if "credit" in msg or "balance" in msg or "billing" in msg or "insufficient" in msg:
        return "**余额或额度不足**，请到对应平台充值后再试。"
    return f"调用 AI 时出错：{exc}"


PRODUCT_NAME = "聚才 · 想法验真"
PRODUCT_TAGLINE = "10 分钟理清一个想法值不值得做，并拿到一份贴合你情况的 7 天行动建议"

st.set_page_config(
    page_title=PRODUCT_NAME,
    page_icon="🧭",
    layout="centered",
    initial_sidebar_state="collapsed",
)

_llm_provider, _, _, _, _ = resolve_llm()
if not _llm_provider:
    st.error("⚠️ 未检测到 AI 接口密钥")
    st.markdown(
        "**用 Kimi（月之暗面）—— 你有会员也要单独拿 API Key：**\n\n"
        "1. 打开 https://platform.moonshot.cn/ （用 Kimi 同一手机号登录）\n"
        "2. 左侧 **API Key 管理** → 新建 Key（以 `sk-` 开头）\n"
        "3. 确认账户有 **API 余额**（会员费通常不含 API 调用，需充值一点）\n"
        "4. Streamlit → Settings → **Secrets**，粘贴后 **Save** → **Reboot app**"
    )
    st.code(
        'MOONSHOT_API_KEY = "sk-你的Kimi开放平台密钥"\n'
        '# 可选：MOONSHOT_MODEL = "moonshot-v1-128k"  # 报告更长时用',
        language="toml",
    )
    with st.expander("其他可选方式"):
        st.code(
            'DEEPSEEK_API_KEY = "sk-..."       # platform.deepseek.com\n'
            'OPENROUTER_API_KEY = "sk-or-..."  # openrouter.ai',
            language="toml",
        )
    st.stop()

EXAMPLE_IDEAS = [
    "帮本地餐饮老板做抖音团购引流，按效果抽成",
    "给跨境电商卖家做产品详情页 + 投放素材，按件收费",
    "面向程序员的一对一副业转型咨询，按小时收费",
]


def init_session():
    defaults = {
        "step": 1,
        "idea": "",
        "monthly_target": "",
        "followup_qs": [],
        "followup_answers": {},
        "context": {},
        "report": None,
        "tasks": {},
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get_pending_tasks():
    today = datetime.now().strftime("%Y-%m-%d")
    pending = []
    for task in st.session_state.tasks.values():
        due = task.get("due_date", "")
        if not task.get("done", False) and due and due <= today:
            pending.append(task)
    return pending


def generate_followup_questions(idea, monthly_target, time_status, capital_level):
    target_hint = monthly_target.strip() or "未填写"
    prompt = f"""你是一位温和但专业的创业验证顾问。用户想验证一个新方向是否值得投入，请用 3 个问题帮他补全关键信息。

【用户方向】{idea}
【月入目标】{target_hint}
【时间状态】{time_status}
【资金量级】{capital_level}

出题规则：
1. 三个问题分别聚焦：①目标用户与获客渠道 ②竞争与市场空间 ③时间与风险承受
2. 问题应具体、可回答，但**不要**要求真实姓名、微信号、电话等隐私信息；用「哪类客户」「什么渠道」「大概预算」即可
3. 禁止空泛问题（优势、热情、大趋势）
4. 语气：尊重、务实、像愿意帮朋友把关的顾问，不要训斥或嘲讽

只输出三行，格式严格为：
Q1: ...
Q2: ...
Q3: ...
"""
    try:
        text = call_llm(prompt, max_tokens=600, temperature=0.6)
        questions = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if re.match(r"Q\d+\s*[:：]", line):
                questions.append(re.split(r"[:：]", line, 1)[1].strip())
        return questions[:3] if len(questions) >= 3 else default_questions()
    except Exception as e:
        st.session_state.api_error = friendly_api_error(e)
        return default_questions()


def default_questions():
    return [
        "你的理想客户是哪一类人（行业/场景）？你打算通过什么渠道接触到他们？",
        "市面上类似服务大概怎么收费？你觉得自己的差异点在哪里？",
        "在现有时间与资金下，如果 2–3 个月没有明显收入，你会怎么调整？",
    ]


def generate_report(idea, followup_answers, time_status, capital_level, monthly_target):
    answers_text = "\n".join([f"- {k}: {v}" for k, v in followup_answers.items()])
    target = monthly_target.strip() or "未说明"

    prompt = f"""你是一位创业验证顾问。用户希望知道：这个想法是否值得继续投入，以及若继续，接下来 7 天可以做什么。请给出客观、可执行、尊重用户现实条件的建议。

【输入】
方向：{idea}
月入目标：{target}
补充回答：
{answers_text}
时间：{time_status}
资金：{capital_level}

【原则】
- 站在用户利益出发：不夸大机会，也不轻易否定；结合其时间与资金给可退可进的建议
- **禁止**要求、推断或输出任何真实姓名、微信号、电话、住址
- 数字可合理估算，信息不足写「待验证」，不要编造
- 若方向风险较高，说明原因并给出替代路径（缩小范围、换验证方式等），而非简单一句「别做」

【输出要求】
- Markdown，严格按下列 6 个一级标题输出（标题文字必须完全一致，带 # 号）
- 总字数 900–1200 字
- 禁止空话套话

# 综合建议
一行标签，必须是以下四者之一：【值得尝试 / 建议小步试水 / 建议先补信息 / 建议暂缓】
下一行：2–3 句理由，说明为何给出该建议，并点明用户当前最大的机会或风险。
若标签为「建议暂缓」，可简要说明更适合先做什么（调研、兼职验证、缩小范围等），语气保持尊重。

# 盈亏快算
用 4–6 行 bullet 估算（可标注假设）：
- 合理客单价区间：___ 元
- 7 天内 realistic 验证成果（不一定是收入）：___
- 7 天必要现金支出：___ 元
- 达到月入目标大约需要：___ 单/客户（量级即可）
- 与当前时间/资金的匹配度：高/中/低 + 一句原因

# 7天行动清单
只列 3 条，每条含「做什么」「面向谁/什么渠道」「建议完成日（Day1–Day7）」「怎样算完成」：
1. 【动作】...
2. 【动作】...
3. 【动作】...
动作应低门槛、可验证，适合副业/小成本场景。

# 优先验证对象
- 目标用户画像：（类型、场景，不要具体人名）
- 建议验证方式：（如访谈、发样本、小范围试用等）
- 合理付费预期：___ 元
- 沟通思路示例：（1–2 句通用话术，不针对具体个人）

# 7天止损线
- 时间止损：
- 金钱止损：
- 信号止损：（出现什么现象应暂停或调整方向）

# 下一步
若 7 天行动清单完成，接下来最该做的一件事（一句话）。
"""

    try:
        return call_llm(prompt, max_tokens=2800, temperature=0.55)
    except Exception as e:
        return f"<!--API_ERROR-->\n{friendly_api_error(e)}"


SECTION_HEADERS = {
    "综合建议": ("综合建议", "# 综合建议", "## 综合建议", "教练判定", "# 教练判定", "## 教练判定"),
    "盈亏快算": ("盈亏快算", "# 盈亏快算", "## 盈亏快算"),
    "7天行动清单": (
        "7天行动清单",
        "# 7天行动清单",
        "## 7天行动清单",
        "7天三件事",
        "# 7天三件事",
        "## 7天三件事",
        "# 本周3件事",
        "## 本周3件事",
    ),
    "优先验证对象": (
        "优先验证对象",
        "# 优先验证对象",
        "## 优先验证对象",
        "第一个客户",
        "# 第一个客户",
        "## 第一个客户",
    ),
    "7天止损线": (
        "7天止损线",
        "# 7天止损线",
        "## 7天止损线",
        "# 止损线",
        "## 止损线",
    ),
    "下一步": ("下一步", "# 下一步", "## 下一步", "第8天", "# 第8天", "## 第8天"),
}


def parse_report(report):
    sections = {}
    current_section = None
    current_content = []

    header_map = {}
    for key, variants in SECTION_HEADERS.items():
        for v in variants:
            header_map[v] = key
            if v.startswith("#"):
                header_map[v.lstrip("# ").strip() + "："] = key
                header_map["【" + v.lstrip("# ").strip() + "】"] = key

    for line in report.split("\n"):
        stripped = line.strip()
        matched = None
        for prefix, key in header_map.items():
            if stripped == prefix or stripped.startswith(prefix):
                matched = key
                break
        if not matched:
            for key, variants in SECTION_HEADERS.items():
                for v in variants:
                    bare = v.lstrip("#").strip()
                    if stripped.startswith(bare) and stripped[len(bare) :].strip() in ("", "：", ":"):
                        matched = key
                        break
                if matched:
                    break

        if matched:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = matched
            current_content = []
        elif current_section:
            current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


def verdict_style(verdict_text):
    text = verdict_text or ""
    if "暂缓" in text or "换方向" in text or "不建议" in text:
        return "red", "建议暂缓"
    if "补信息" in text or "小步" in text or "试水" in text or "谨慎" in text:
        return "yellow", "建议小步试水"
    return "green", "值得尝试"


def render_progress(step):
    labels = ["描述想法", "补充信息", "查看方案"]
    parts = []
    for i, label in enumerate(labels, start=1):
        if i < step:
            parts.append(f'<span class="step done">✓ {label}</span>')
        elif i == step:
            parts.append(f'<span class="step active">{i}. {label}</span>')
        else:
            parts.append(f'<span class="step">{i}. {label}</span>')
    st.markdown(
        f'<div class="progress-bar">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def inject_css():
    st.markdown(
        """
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .stDeployButton { display: none !important; }
    .block-container { padding-top: 1.5rem; max-width: 680px; }
    .hero {
        text-align: center;
        padding: 2.25rem 1.25rem 1.75rem;
        background: linear-gradient(145deg, #0c1222 0%, #1a365d 55%, #1e40af 100%);
        border-radius: 20px;
        margin-bottom: 1.25rem;
        color: #f8fafc;
    }
    .hero .brand { font-size: 0.8rem; letter-spacing: 0.12em; opacity: 0.75; margin-bottom: 0.35rem; }
    .hero h1 { font-size: 1.85rem; font-weight: 700; margin: 0 0 0.5rem; letter-spacing: -0.02em; }
    .hero .tagline { font-size: 0.95rem; opacity: 0.88; line-height: 1.55; margin: 0 auto 1.25rem; max-width: 28rem; }
    .value-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0.5rem;
        text-align: left;
        font-size: 0.78rem;
        opacity: 0.92;
    }
    .value-item {
        background: rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 0.55rem 0.6rem;
        line-height: 1.35;
    }
    .value-item strong { display: block; font-size: 0.8rem; margin-bottom: 0.15rem; }
    .progress-bar {
        display: flex;
        justify-content: space-between;
        gap: 0.35rem;
        margin-bottom: 1.5rem;
        font-size: 0.78rem;
    }
    .step {
        flex: 1;
        text-align: center;
        padding: 0.45rem 0.25rem;
        border-radius: 8px;
        background: #f1f5f9;
        color: #94a3b8;
    }
    .step.active { background: #dbeafe; color: #1d4ed8; font-weight: 600; }
    .step.done { background: #dcfce7; color: #15803d; }
    .section-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #0f172a;
        margin-bottom: 0.85rem;
    }
    .hint-box {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.85rem 1rem;
        font-size: 0.88rem;
        color: #475569;
        line-height: 1.5;
        margin-bottom: 1rem;
    }
    .info-badge {
        display: inline-block;
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 999px;
        padding: 0.35rem 0.85rem;
        font-size: 0.82rem;
        color: #1e40af;
        margin-bottom: 0.75rem;
        max-width: 100%;
        word-break: break-word;
    }
    .question-block {
        background: #fff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1rem 1.1rem 0.25rem;
        margin-bottom: 0.85rem;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04);
    }
    .q-tag {
        font-size: 0.72rem;
        font-weight: 700;
        color: #2563eb;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }
    .q-text { font-size: 0.98rem; color: #1e293b; margin: 0.35rem 0 0.5rem; line-height: 1.5; }
    .verdict-green, .verdict-yellow, .verdict-red {
        border-radius: 14px;
        padding: 1.15rem 1.25rem;
        margin-bottom: 1rem;
        line-height: 1.55;
    }
    .verdict-green { background: linear-gradient(135deg,#dcfce7,#f0fdf4); border-left: 4px solid #22c55e; }
    .verdict-yellow { background: linear-gradient(135deg,#fef9c3,#fefce8); border-left: 4px solid #eab308; }
    .verdict-red { background: linear-gradient(135deg,#fee2e2,#fef2f2); border-left: 4px solid #ef4444; }
    .verdict-label { font-size: 0.75rem; font-weight: 700; opacity: 0.7; margin-bottom: 0.35rem; }
    .day8-card {
        background: linear-gradient(135deg,#eff6ff,#f8fafc);
        border: 1px dashed #93c5fd;
        border-radius: 12px;
        padding: 0.9rem 1rem;
        margin-top: 0.5rem;
        font-size: 0.95rem;
        color: #1e3a8a;
    }
    .stTextArea textarea, .stTextInput input {
        border-radius: 10px !important;
        font-size: 0.95rem !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg,#2563eb,#1d4ed8) !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }
    @media (max-width: 640px) {
        .value-grid { grid-template-columns: 1fr; }
        .progress-bar { flex-direction: column; }
    }
</style>
""",
        unsafe_allow_html=True,
    )


def render_hero():
    st.markdown(
        f"""
<div class="hero">
    <div class="brand">JU CAI · IDEA VALIDATOR</div>
    <h1>{html.escape(PRODUCT_NAME)}</h1>
    <p class="tagline">{html.escape(PRODUCT_TAGLINE)}</p>
    <div class="value-grid">
        <div class="value-item"><strong>不是计划书</strong>帮你看清机会与风险</div>
        <div class="value-item"><strong>不是空谈</strong>7 天行动清单 + 止损线</div>
        <div class="value-item"><strong>尊重隐私</strong>无需填写真实姓名联系方式</div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


def extract_action_lines(actions_text):
    lines = []
    for line in actions_text.split("\n"):
        s = line.strip()
        if re.match(r"^[123][\.、\)]", s):
            lines.append(s)
    return lines[:3]


init_session()
inject_css()
render_hero()
render_progress(st.session_state.step)

pending = get_pending_tasks()
if pending:
    with st.container(border=True):
        st.warning(f"⏰ 你有 {len(pending)} 项任务已到期")
        for t in pending:
            st.write(f"- {t['action']}（截止 {t['due_date']}）")
        if st.button("全部标为完成", key="mark_all_done"):
            for t in st.session_state.tasks.values():
                if not t.get("done") and t.get("due_date", "") <= datetime.now().strftime("%Y-%m-%d"):
                    t["done"] = True
            st.rerun()

# —— Step 1 ——
if st.session_state.step == 1:
    st.markdown('<div class="section-title">第一步：说清楚你想验证什么</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hint-box">'
        "写得越具体，建议越贴切。建议包含：<b>卖给谁</b>、<b>解决什么问题</b>、<b>怎么收费</b>。"
        "</div>"
        '<div class="hint-box" style="margin-top:0.5rem;">'
        "🔒 无需填写真实姓名、电话或微信号，用客户类型和场景描述即可。"
        "</div>",
        unsafe_allow_html=True,
    )

    idea = st.text_area(
        "商业想法",
        value=st.session_state.idea,
        placeholder="例：帮二三线制造业工厂做抖音短视频代运营，按月 8000 元 + 效果分成",
        height=110,
        label_visibility="visible",
    )

    st.caption("没灵感？点下面填入示例（可再改）")
    ex_cols = st.columns(len(EXAMPLE_IDEAS))
    for i, example in enumerate(EXAMPLE_IDEAS):
        with ex_cols[i]:
            if st.button(f"示例 {i + 1}", key=f"ex_{i}", use_container_width=True):
                st.session_state.idea = example
                st.rerun()

    monthly_target = st.text_input(
        "月入目标（选填，有助于盈亏测算）",
        value=st.session_state.get("monthly_target", ""),
        placeholder="例如：副业月入 8000 元",
    )

    col1, col2 = st.columns(2)
    with col1:
        time_status = st.selectbox(
            "可投入时间",
            [
                "失业，可全职投入",
                "自由职业，时间灵活",
                "在职，每天 2–3 小时",
                "在职，只能周末",
            ],
            key="time_status",
        )
    with col2:
        capital_level = st.selectbox(
            "启动资金",
            [
                "几乎为零（< 3000 元）",
                "少量（3千–1万）",
                "中等（1万–5万）",
                "充裕（5万–10万）",
                "充足（10 万以上）",
            ],
            key="capital_level",
        )

    if st.button("下一步：补充 3 个关键问题 →", use_container_width=True, type="primary"):
        if len(idea.strip()) < 12:
            st.warning("请再写具体一点（至少 12 个字），例如客户是谁、怎么收费。")
        else:
            st.session_state.idea = idea.strip()
            st.session_state.monthly_target = monthly_target.strip()
            st.session_state.context["time_status"] = time_status
            st.session_state.context["capital_level"] = capital_level
            for k in list(st.session_state.keys()):
                if k.startswith("fq_"):
                    del st.session_state[k]
            st.session_state.followup_answers = {}
            with st.spinner("正在根据你的情况准备问题…"):
                st.session_state.followup_qs = generate_followup_questions(
                    st.session_state.idea,
                    st.session_state.monthly_target,
                    time_status,
                    capital_level,
                )
            st.session_state.step = 2
            st.rerun()

# —— Step 2 ——
elif st.session_state.step == 2:
    st.markdown('<div class="section-title">第二步：补充 3 个关键信息</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="info-badge">💡 {html.escape(st.session_state.idea)}</div>',
        unsafe_allow_html=True,
    )
    st.caption("按你的真实情况回答即可，不必填写具体人名或联系方式。")

    if st.session_state.get("api_error"):
        st.warning(st.session_state.api_error)
        st.caption("当前使用默认 3 个问题；配置好 API Key 后可返回第一步重新生成。")

    tags = ["目标用户", "竞争与市场", "时间与风险"]
    for i, q in enumerate(st.session_state.followup_qs):
        st.markdown(
            f'<div class="question-block">'
            f'<div class="q-tag">{tags[i] if i < len(tags) else f"问题 {i+1}"}</div>'
            f'<div class="q-text">{html.escape(q)}</div></div>',
            unsafe_allow_html=True,
        )
        st.text_area(
            f"回答 {i + 1}",
            value=st.session_state.followup_answers.get(q, ""),
            key=f"fq_{i}",
            height=88,
            placeholder="例如：目标客户类型、渠道、预算范围、你的顾虑……",
            label_visibility="collapsed",
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 修改想法", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("生成 7 天行动方案 →", use_container_width=True, type="primary"):
            answers = {q: st.session_state.get(f"fq_{i}", "").strip() for i, q in enumerate(st.session_state.followup_qs)}
            short = [q for q, a in answers.items() if len(a) < 8]
            if short:
                st.warning("每个问题请至少写 8 个字，越具体报告越有用。")
            else:
                st.session_state.followup_answers = answers
                with st.spinner("正在生成你的验证方案（约 15–30 秒）…"):
                    st.session_state.report = generate_report(
                        st.session_state.idea,
                        st.session_state.followup_answers,
                        st.session_state.context["time_status"],
                        st.session_state.context["capital_level"],
                        st.session_state.monthly_target,
                    )
                st.session_state.step = 3
                st.rerun()

# —— Step 3 ——
elif st.session_state.step == 3 and st.session_state.report:
    report = st.session_state.report

    st.markdown('<div class="section-title">你的 7 天验证方案</div>', unsafe_allow_html=True)

    if report.startswith("<!--API_ERROR-->"):
        st.error(report.replace("<!--API_ERROR-->\n", "", 1))
        if st.button("← 返回修改回答", use_container_width=True):
            st.session_state.step = 2
            st.session_state.report = None
            st.rerun()
        st.stop()

    sections = parse_report(report)

    verdict = sections.get("综合建议", "") or sections.get("教练判定", "")
    pnl = sections.get("盈亏快算", "")
    actions = sections.get("7天行动清单", "") or sections.get("7天三件事", "")
    target_audience = sections.get("优先验证对象", "") or sections.get("第一个客户", "")
    stop_loss = sections.get("7天止损线", "")
    next_step = sections.get("下一步", "") or sections.get("第8天", "")

    if not sections:
        st.info("报告格式解析失败，以下为完整原文：")
        st.markdown(report)
    else:
        if verdict:
            style, label = verdict_style(verdict)
            safe = html.escape(verdict).replace("\n", "<br/>")
            st.markdown(
                f'<div class="verdict-{style}">'
                f'<div class="verdict-label">综合建议 · {label}</div>{safe}</div>',
                unsafe_allow_html=True,
            )

        if pnl:
            with st.container(border=True):
                st.subheader("📊 盈亏快算")
                st.markdown(pnl)

        if actions:
            with st.container(border=True):
                st.subheader("⚡ 7 天行动清单")
                st.markdown(actions)

        if target_audience:
            with st.container(border=True):
                st.subheader("🎯 优先验证对象")
                st.markdown(target_audience)

        if stop_loss:
            with st.container(border=True):
                st.subheader("🛑 止损线")
                st.markdown(stop_loss)

        if next_step:
            st.markdown(
                f'<div class="day8-card"><strong>下一步</strong><br/>{html.escape(next_step)}</div>',
                unsafe_allow_html=True,
            )

    st.download_button(
        "📥 下载报告（Markdown）",
        data=report,
        file_name=f"想法验真_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
        mime="text/markdown",
        use_container_width=True,
    )

    with st.expander("查看完整原文"):
        st.markdown(report)

    st.divider()
    st.markdown('<div class="section-title">📅 把 3 件事写进你的日历</div>', unsafe_allow_html=True)
    st.caption("任务只保存在本次浏览器会话，关闭页面后需重新设定。")

    action_lines = extract_action_lines(actions)
    if not action_lines:
        st.info("未能从报告中解析出任务条目，请手动从上方复制。")
    else:
        tasks_to_save = {}
        for i, line in enumerate(action_lines):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{line}**")
            with c2:
                due = st.date_input(
                    "截止",
                    value=datetime.now().date() + timedelta(days=i + 2),
                    key=f"due_{i}",
                    label_visibility="collapsed",
                )
            task_id = f"task_{i}"
            tasks_to_save[task_id] = {
                "action": line,
                "due_date": due.strftime("%Y-%m-%d"),
                "done": False,
            }

        if st.button("保存到本次会话", use_container_width=True):
            st.session_state.tasks.update(tasks_to_save)
            st.success("已保存。下次在本页打开会看到到期提醒。")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← 修改回答", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with c2:
        if st.button("🔄 验证新想法", use_container_width=True):
            st.session_state.step = 1
            st.session_state.idea = ""
            st.session_state.monthly_target = ""
            st.session_state.followup_qs = []
            st.session_state.followup_answers = {}
            st.session_state.report = None
            st.session_state.tasks = {}
            st.rerun()

    st.caption("报告由 AI 根据你填写的内容生成，仅供参考。无需也请勿填写他人真实姓名或联系方式。")
