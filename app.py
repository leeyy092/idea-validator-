import html
import json
import os
import re
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

LLM_OPTIONS = (
    ("moonshot", ("MOONSHOT_API_KEY", "KIMI_API_KEY"), "moonshot-v1-32k", "Kimi"),
    ("deepseek", ("DEEPSEEK_API_KEY",), "deepseek-chat", "DeepSeek"),
    ("openrouter", ("OPENROUTER_API_KEY",), "anthropic/claude-3.5-sonnet", "OpenRouter"),
    ("anthropic", ("ANTHROPIC_API_KEY",), "claude-sonnet-4-6", "Claude"),
)

PRODUCT_NAME = "聚才 · 想法验真"
PRODUCT_TAGLINE = "10 分钟决策卡：做不做 · 赚多少才值得 · 7 天怎么验证"

COACHING_PRICE = "99"
COACHING_DAYS = "7"


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
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
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
        base_urls[provider], api_key, model, prompt, max_tokens, temperature, extra_headers=extra
    )


def friendly_api_error(exc):
    msg = str(exc).lower()
    if "401" in msg or "authentication" in msg or ("invalid" in msg and "key" in msg):
        return "API Key 无效。请到 Streamlit Secrets 更新 MOONSHOT_API_KEY 后 Reboot。"
    if "credit" in msg or "balance" in msg or "billing" in msg or "insufficient" in msg:
        return "API 余额不足，请到对应平台充值后再试。"
    return f"调用 AI 时出错：{exc}"


st.set_page_config(page_title=PRODUCT_NAME, page_icon="🧭", layout="centered", initial_sidebar_state="collapsed")

if not resolve_llm()[0]:
    st.error("未配置 AI 密钥")
    st.code('MOONSHOT_API_KEY = "sk-你的密钥"', language="toml")
    st.caption("Streamlit Cloud → Settings → Secrets → Save → Reboot app")
    st.stop()

EXAMPLE_IDEAS = [
    "帮本地餐饮做抖音团购引流，按效果抽成",
    "跨境电商产品详情页代写，按件收费",
    "程序员副业转型咨询，按小时收费",
]

TIME_OPTIONS = ["全职", "自由职业", "每天2-3h", "仅周末"]
CAPITAL_OPTIONS = ["<3千", "3千-1万", "1-5万", "5-10万", "10万+"]


CUSTOMER_CHANNELS = ["微信私域", "小红书/抖音", "转介绍", "线下陌拜", "平台接单", "其他"]
DEMAND_LEVELS = ["还不确定有没有需求", "有人咨询但未付费", "已有明确付费意愿"]
VALIDATION_STAGES = ["还在想法阶段", "和潜在用户聊过", "做过试用/样品", "已有付费或订单"]
RISK_OPTIONS = ["找不到客户", "定价卖不动", "竞争太激烈", "时间不够", "技能/资源不足", "其他"]
STALL_ACTIONS = ["缩小范围再试", "暂停换方向", "降低预期继续", "加大投入搏一把"]


def init_session():
    defaults = {
        "step": 1,
        "idea": "",
        "monthly_target": "",
        "survey": {},
        "context": {},
        "report": None,
        "tasks": {},
        "task_done": {},
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def format_survey_for_report(survey):
    lines = [
        f"【客户】类型/场景：{survey.get('customer_who', '')}",
        f"  获客渠道：{survey.get('reach_channel', '')}",
        f"  需求信号：{survey.get('demand_signal', '')}",
        f"【定价】计划收费：{survey.get('your_price', '')}",
        f"  市场参考价：{survey.get('market_price', '')}",
        f"  差异化：{survey.get('why_you', '')}",
        f"【验证】当前进度：{survey.get('stage', '')}",
        f"  最大顾虑：{survey.get('biggest_risk', '')}",
        f"  4周无进展时：{survey.get('if_stall', '')}",
    ]
    if survey.get("risk_note", "").strip():
        lines.append(f"  补充说明：{survey['risk_note'].strip()}")
    return "\n".join(lines)


def validate_survey(survey):
    required = ["customer_who", "your_price", "why_you"]
    missing = [k for k in required if len(survey.get(k, "").strip()) < 2]
    return missing


def get_pending_tasks():
    today = datetime.now().strftime("%Y-%m-%d")
    return [
        t
        for t in st.session_state.tasks.values()
        if not t.get("done") and t.get("due_date", "") and t["due_date"] <= today
    ]


def generate_report(idea, survey, time_status, capital_level, monthly_target):
    answers_text = format_survey_for_report(survey)
    target = monthly_target.strip() or "未说明"

    prompt = f"""你是创业决策顾问。根据用户填写的结构化信息，输出「决策计算器」结果。
必须引用用户给出的收费、渠道、验证进度等原话做推演；信息不足写「待验证」。禁止输出真实姓名、电话、微信号。

【输入】
方向：{idea}
月入目标：{target}
时间：{time_status}
资金：{capital_level}

{answers_text}

【输出】Markdown，严格按 5 个一级标题（文字完全一致）：

# 决策结论
结论：【值得做 / 小步试 / 先不做】（三选一）
置信度：XX%（60–85 整数；「已有付费/订单」偏高，「还在想法阶段」偏低）
一句话：不超过 30 字，点明最关键依据

# 数字推演
- 保本线（覆盖时间成本最低月入）：___ 元
- 合理客单价：___ 元（对照用户填的计划收费与市场参考价）
- 见到首单 realistic 周期：___ 周（结合可用时间与验证进度）
- 7 天可验证成果：___（具体、可衡量，匹配当前验证阶段）
- 7 天现金支出上限：___ 元

# 替代方向
若「先不做」或「小步试」：1–2 个更小验证版本（各一句话）。
若「值得做」：写「维持当前方向，优先完成下方 7 天清单」。

# 7天行动清单
3 条，格式：1. 【DayX】动作 — 完成标志（匹配用户渠道与验证阶段）

# 止损线
- 时间：___
- 金钱：___
- 信号：___（可呼应用户「4周无进展」的选择）
"""

    try:
        return call_llm(prompt, max_tokens=2400, temperature=0.5)
    except Exception as e:
        return f"<!--API_ERROR-->\n{friendly_api_error(e)}"


SECTION_HEADERS = {
    "决策结论": ("决策结论", "# 决策结论", "综合建议", "# 综合建议"),
    "数字推演": ("数字推演", "# 数字推演", "盈亏快算", "# 盈亏快算"),
    "替代方向": ("替代方向", "# 替代方向"),
    "7天行动清单": ("7天行动清单", "# 7天行动清单", "7天三件事", "# 7天三件事"),
    "止损线": ("止损线", "# 止损线", "7天止损线", "# 7天止损线"),
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
                bare = v.lstrip("# ").strip()
                header_map[bare + "："] = key

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


def parse_verdict(conclusion_text):
    text = conclusion_text or ""
    if "先不做" in text or "暂缓" in text or "不建议" in text:
        return "hold", "先不做", "red"
    if "小步" in text or "试水" in text or "补信息" in text:
        return "try", "小步试", "yellow"
    return "go", "值得做", "green"


def parse_confidence(text):
    m = re.search(r"置信度[：:\s]*(\d{1,3})\s*%?", text or "")
    return int(m.group(1)) if m else None


def parse_one_liner(conclusion_text):
    for line in (conclusion_text or "").split("\n"):
        line = line.strip()
        if line.startswith("一句话"):
            return re.sub(r"^一句话[：:]\s*", "", line)
    lines = [l.strip() for l in (conclusion_text or "").split("\n") if l.strip()]
    for line in lines:
        if not re.search(r"结论|置信度", line):
            return line.lstrip("- ").strip()
    return lines[-1] if lines else ""


def parse_metrics(numbers_text):
    metrics = []
    for line in (numbers_text or "").split("\n"):
        line = line.strip().lstrip("-• ").strip()
        if line and "___" not in line:
            metrics.append(line)
    return metrics[:5]


def extract_action_lines(actions_text):
    lines = []
    for line in (actions_text or "").split("\n"):
        s = line.strip()
        if re.match(r"^[123][\.、\)]", s):
            lines.append(s)
    return lines[:3]


def inject_css():
    st.markdown(
        """
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .stDeployButton { display: none !important; }
    .block-container { padding: 0.75rem 1rem 1.5rem; max-width: 640px; }
    .main .element-container { margin-bottom: 0.35rem; }
    div[data-testid="stVerticalBlock"] > div { gap: 0.4rem; }
    .hero {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        border-radius: 12px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.6rem;
        color: #fff;
    }
    .hero h1 { font-size: 1.45rem; font-weight: 700; margin: 0 0 0.25rem; }
    .hero p { font-size: 0.88rem; opacity: 0.9; margin: 0; line-height: 1.4; }
    .progress-bar { display: flex; gap: 0.3rem; margin-bottom: 0.65rem; font-size: 0.72rem; }
    .step { flex: 1; text-align: center; padding: 0.35rem 0.2rem; border-radius: 6px; background: #f1f5f9; color: #94a3b8; }
    .step.active { background: #2563eb; color: #fff; font-weight: 600; }
    .step.done { background: #dcfce7; color: #15803d; }
    .decision-card {
        border-radius: 12px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.5rem;
        color: #0f172a;
    }
    .decision-card.go { background: linear-gradient(135deg,#ecfdf5,#d1fae5); border: 2px solid #10b981; }
    .decision-card.try { background: linear-gradient(135deg,#fffbeb,#fef3c7); border: 2px solid #f59e0b; }
    .decision-card.hold { background: linear-gradient(135deg,#fef2f2,#fee2e2); border: 2px solid #ef4444; }
    .decision-verdict { font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; margin: 0; }
    .decision-meta { font-size: 0.8rem; color: #64748b; margin-top: 0.25rem; }
    .decision-oneliner { font-size: 0.95rem; margin-top: 0.5rem; line-height: 1.45; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; margin: 0.5rem 0; }
    .metric-cell {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.5rem 0.6rem;
        font-size: 0.78rem;
        line-height: 1.35;
        color: #334155;
    }
    .panel {
        background: #fff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.65rem 0.75rem;
        margin-bottom: 0.4rem;
        font-size: 0.88rem;
        line-height: 1.45;
    }
    .panel-title { font-size: 0.75rem; font-weight: 700; color: #64748b; margin-bottom: 0.35rem; text-transform: uppercase; letter-spacing: 0.04em; }
    .coach-box {
        background: linear-gradient(135deg,#1e3a8a,#2563eb);
        color: #fff;
        border-radius: 10px;
        padding: 0.75rem 0.85rem;
        margin: 0.5rem 0;
        font-size: 0.88rem;
        line-height: 1.45;
    }
    .coach-box strong { font-size: 1rem; }
    .q-block {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.6rem 0.75rem 0.2rem;
        margin-bottom: 0.45rem;
        background: #fafbfc;
    }
    .q-block-head { display: flex; align-items: baseline; gap: 0.4rem; margin-bottom: 0.15rem; }
    .q-block-num { font-size: 0.72rem; font-weight: 800; color: #2563eb; }
    .q-block-title { font-size: 0.92rem; font-weight: 700; color: #0f172a; }
    .q-block-hint { font-size: 0.72rem; color: #64748b; margin-bottom: 0.35rem; }
    .idea-pill {
        display: inline-block;
        background: #eff6ff;
        color: #1d4ed8;
        font-size: 0.82rem;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
        margin-bottom: 0.4rem;
    }
    .stTextArea textarea { min-height: 72px !important; font-size: 0.9rem !important; }
    .stButton > button[kind="primary"] {
        background: #2563eb !important;
        border: none !important;
        font-weight: 600 !important;
    }
    hr { margin: 0.5rem 0 !important; }
    .stCaption { font-size: 0.75rem !important; }
</style>
""",
        unsafe_allow_html=True,
    )


def render_hero():
    st.markdown(
        f'<div class="hero"><h1>{html.escape(PRODUCT_NAME)}</h1>'
        f'<p>{html.escape(PRODUCT_TAGLINE)}</p></div>',
        unsafe_allow_html=True,
    )


def render_progress(step):
    labels = ["想法", "3组信息", "决策卡"]
    parts = []
    for i, label in enumerate(labels, 1):
        if i < step:
            parts.append(f'<span class="step done">✓{label}</span>')
        elif i == step:
            parts.append(f'<span class="step active">{i}.{label}</span>')
        else:
            parts.append(f'<span class="step">{i}.{label}</span>')
    st.markdown(f'<div class="progress-bar">{"".join(parts)}</div>', unsafe_allow_html=True)


def render_decision_card(conclusion_text):
    kind, label, _ = parse_verdict(conclusion_text)
    conf = parse_confidence(conclusion_text)
    oneliner = parse_one_liner(conclusion_text)
    conf_html = f"置信度 {conf}%" if conf else "基于你填写的信息推演"
    st.markdown(
        f'<div class="decision-card {kind}">'
        f'<div class="decision-verdict">{html.escape(label)}</div>'
        f'<div class="decision-meta">{conf_html}</div>'
        f'<div class="decision-oneliner">{html.escape(oneliner)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_metrics_grid(numbers_text):
    metrics = parse_metrics(numbers_text)
    if not metrics:
        return
    cells = "".join(f'<div class="metric-cell">{html.escape(m)}</div>' for m in metrics)
    st.markdown(f'<div class="metric-grid">{cells}</div>', unsafe_allow_html=True)


def render_coaching_upsell():
    wechat = get_secret("COACHING_WECHAT") or get_secret("COACHING_CONTACT") or "添加微信咨询开通"
    st.markdown(
        f'<div class="coach-box">'
        f"<strong>{COACHING_DAYS} 天陪跑 · ¥{COACHING_PRICE}</strong><br>"
        f"免费决策卡容易看完就忘。陪跑含：每日 1 条检查、方案微调、完成复盘。<br>"
        f"👉 {html.escape(wechat)}"
        f"</div>",
        unsafe_allow_html=True,
    )


def reset_for_new_idea():
    st.session_state.step = 1
    st.session_state.idea = ""
    st.session_state.monthly_target = ""
    st.session_state.survey = {}
    st.session_state.report = None
    st.session_state.tasks = {}
    st.session_state.task_done = {}
    st.session_state.context = {}


init_session()
inject_css()
render_hero()
render_progress(st.session_state.step)

pending = get_pending_tasks()
if pending:
    st.warning(f"⏰ {len(pending)} 项任务到期")
    if st.button("全部完成", key="mark_all_done"):
        for t in st.session_state.tasks.values():
            if not t.get("done") and t.get("due_date", "") <= datetime.now().strftime("%Y-%m-%d"):
                t["done"] = True
        st.rerun()

if st.session_state.step == 1:
    st.caption("卖给谁 · 解决什么 · 怎么收费")

    idea = st.text_area(
        "想法",
        value=st.session_state.idea,
        placeholder="例：帮工厂做抖音代运营，按月 8000 元",
        height=72,
        label_visibility="collapsed",
    )

    c1, c2, c3 = st.columns(3)
    for i, example in enumerate(EXAMPLE_IDEAS):
        with [c1, c2, c3][i]:
            if st.button(f"示例{i+1}", key=f"ex_{i}", use_container_width=True):
                st.session_state.idea = example
                st.rerun()

    r1, r2 = st.columns(2)
    with r1:
        monthly_target = st.text_input("月入目标", value=st.session_state.get("monthly_target", ""), placeholder="如 8000 元")
    with r2:
        time_status = st.selectbox("可用时间", TIME_OPTIONS, key="time_status")
    capital_level = st.selectbox("启动资金", CAPITAL_OPTIONS, key="capital_level")

    if st.button("生成决策卡 →", type="primary", use_container_width=True):
        if len(idea.strip()) < 10:
            st.warning("请再写具体一点。")
        else:
            st.session_state.idea = idea.strip()
            st.session_state.monthly_target = monthly_target.strip()
            st.session_state.context = {"time_status": time_status, "capital_level": capital_level}
            st.session_state.survey = {}
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    st.markdown(f'<span class="idea-pill">{html.escape(st.session_state.idea)}</span>', unsafe_allow_html=True)
    st.caption("3 组信息 · 对应决策卡里的客户、定价、把握度")

    prev = st.session_state.get("survey", {})

    st.markdown(
        '<div class="q-block"><div class="q-block-head">'
        '<span class="q-block-num">01</span><span class="q-block-title">谁会付钱</span></div>'
        '<div class="q-block-hint">→ 影响客单价、首单周期</div></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        customer_who = st.text_input(
            "客户是谁",
            value=prev.get("customer_who", ""),
            placeholder="如：二三线工厂老板、想副业的程序员",
            key="s_customer_who",
        )
    with c2:
        reach_channel = st.selectbox(
            "主要获客渠道",
            CUSTOMER_CHANNELS,
            index=CUSTOMER_CHANNELS.index(prev["reach_channel"]) if prev.get("reach_channel") in CUSTOMER_CHANNELS else 0,
            key="s_reach_channel",
        )
    demand_signal = st.selectbox(
        "需求信号",
        DEMAND_LEVELS,
        index=DEMAND_LEVELS.index(prev["demand_signal"]) if prev.get("demand_signal") in DEMAND_LEVELS else 0,
        key="s_demand_signal",
    )

    st.markdown(
        '<div class="q-block"><div class="q-block-head">'
        '<span class="q-block-num">02</span><span class="q-block-title">钱算得拢吗</span></div>'
        '<div class="q-block-hint">→ 影响保本线、7 天支出上限</div></div>',
        unsafe_allow_html=True,
    )
    p1, p2 = st.columns(2)
    with p1:
        your_price = st.text_input(
            "你计划怎么收费",
            value=prev.get("your_price", ""),
            placeholder="如：8000元/月、500元/次",
            key="s_your_price",
        )
    with p2:
        market_price = st.text_input(
            "市场参考价",
            value=prev.get("market_price", ""),
            placeholder="如：同行 3000-6000/月",
            key="s_market_price",
        )
    why_you = st.text_area(
        "客户为什么选你",
        value=prev.get("why_you", ""),
        placeholder="如：更懂行业、响应更快、有成功案例…",
        height=64,
        key="s_why_you",
        label_visibility="visible",
    )

    st.markdown(
        '<div class="q-block"><div class="q-block-head">'
        '<span class="q-block-num">03</span><span class="q-block-title">你有多大把握</span></div>'
        '<div class="q-block-hint">→ 影响结论与置信度</div></div>',
        unsafe_allow_html=True,
    )
    stage = st.selectbox(
        "验证进度",
        VALIDATION_STAGES,
        index=VALIDATION_STAGES.index(prev["stage"]) if prev.get("stage") in VALIDATION_STAGES else 0,
        key="s_stage",
    )
    r1, r2 = st.columns(2)
    with r1:
        biggest_risk = st.selectbox(
            "最大顾虑",
            RISK_OPTIONS,
            index=RISK_OPTIONS.index(prev["biggest_risk"]) if prev.get("biggest_risk") in RISK_OPTIONS else 0,
            key="s_biggest_risk",
        )
    with r2:
        if_stall = st.selectbox(
            "4 周无进展时",
            STALL_ACTIONS,
            index=STALL_ACTIONS.index(prev["if_stall"]) if prev.get("if_stall") in STALL_ACTIONS else 0,
            key="s_if_stall",
        )
    risk_note = st.text_input(
        "补充（选填）",
        value=prev.get("risk_note", ""),
        placeholder="任何想补充的背景",
        key="s_risk_note",
        label_visibility="collapsed",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← 返回", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("出决策卡 →", type="primary", use_container_width=True):
            survey = {
                "customer_who": customer_who.strip(),
                "reach_channel": reach_channel,
                "demand_signal": demand_signal,
                "your_price": your_price.strip(),
                "market_price": market_price.strip(),
                "why_you": why_you.strip(),
                "stage": stage,
                "biggest_risk": biggest_risk,
                "if_stall": if_stall,
                "risk_note": risk_note.strip(),
            }
            if validate_survey(survey):
                st.warning("请至少填完：客户是谁、计划收费、客户为什么选你。")
            else:
                st.session_state.survey = survey
                with st.spinner("计算中…"):
                    st.session_state.report = generate_report(
                        st.session_state.idea,
                        survey,
                        st.session_state.context["time_status"],
                        st.session_state.context["capital_level"],
                        st.session_state.monthly_target,
                    )
                st.session_state.step = 3
                st.rerun()

elif st.session_state.step == 3 and st.session_state.report:
    report = st.session_state.report

    if report.startswith("<!--API_ERROR-->"):
        st.error(report.replace("<!--API_ERROR-->\n", "", 1))
        if st.button("← 返回"):
            st.session_state.step = 2
            st.session_state.report = None
            st.rerun()
        st.stop()

    sections = parse_report(report)
    conclusion = sections.get("决策结论", "") or sections.get("综合建议", "")
    numbers = sections.get("数字推演", "") or sections.get("盈亏快算", "")
    alt = sections.get("替代方向", "")
    actions = sections.get("7天行动清单", "") or sections.get("7天三件事", "")
    stop = sections.get("止损线", "") or sections.get("7天止损线", "")

    if not sections:
        st.markdown(report)
    else:
        render_decision_card(conclusion)
        render_metrics_grid(numbers)

        if actions:
            st.markdown(
                f'<div class="panel"><div class="panel-title">7 天行动</div>{html.escape(actions).replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )

        if alt and "维持当前" not in alt:
            st.markdown(
                f'<div class="panel"><div class="panel-title">更小风险的试法</div>{html.escape(alt).replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )

        if stop:
            with st.expander("止损线"):
                st.markdown(stop)

    render_coaching_upsell()

    action_lines = extract_action_lines(actions)
    if action_lines:
        st.caption("勾选完成 · 设截止日期")
        tasks_to_save = {}
        for i, line in enumerate(action_lines):
            ck, dt = st.columns([4, 2])
            with ck:
                done = st.checkbox(line, key=f"done_{i}", value=st.session_state.task_done.get(i, False))
                st.session_state.task_done[i] = done
            with dt:
                due = st.date_input(
                    "截止",
                    value=datetime.now().date() + timedelta(days=i + 2),
                    key=f"due_{i}",
                    label_visibility="collapsed",
                )
            tasks_to_save[f"task_{i}"] = {"action": line, "due_date": due.strftime("%Y-%m-%d"), "done": done}
        if st.button("保存进度", use_container_width=True):
            st.session_state.tasks.update(tasks_to_save)
            st.success("已保存")

    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "下载",
            data=report,
            file_name=f"决策卡_{datetime.now():%Y%m%d}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with d2:
        if st.button("改回答", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with d3:
        if st.button("新想法", use_container_width=True):
            reset_for_new_idea()
            st.rerun()

    with st.expander("完整报告"):
        st.markdown(report)

    st.caption("AI 推演仅供参考，决策请结合自身情况。")
