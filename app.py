import os
import json
import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

st.set_page_config(
    page_title="7天冷启动加速器",
    page_icon="🚀",
    layout="centered",
    initial_sidebar_state="collapsed",
)

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    st.error("⚠️ 未检测到 ANTHROPIC_API_KEY")
    st.code("在 Streamlit Cloud 的 Advanced Settings → Secrets 中配置\nANTHROPIC_API_KEY = \"sk-xxx\"", language="toml")
    st.stop()

client = Anthropic(api_key=api_key)

TASKS_FILE = os.path.join(os.path.dirname(__file__), "tasks.json")


def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def get_pending_tasks():
    tasks = load_tasks()
    today = datetime.now().strftime("%Y-%m-%d")
    pending = []
    for task_id, task in tasks.items():
        if not task.get("done", False) and task.get("due_date", "") <= today:
            pending.append(task)
    return pending


def generate_followup_questions(idea):
    prompt = f"""你是一位7天启动教练。用户要在一个新方向上7天内拿到第一个结果，你要用3个问题直接戳破他的执行障碍。

用户的方向：{idea}

风格要求：
- 每个问题都要具体到"名字""数字""日期"
- 不要问"你的优势是什么"，要问"你上周跟哪个潜在客户聊过？"
- 不要问"市场怎么样"，要问"如果明天就要收第一笔钱，你会找谁？"
- 不要问"你怎么获客"，要问"你准备怎么找到第一个客户？具体第一步是什么？"
- 不要问"你有多少资金"，要问"如果3个月没收入，你还能撑多久？"
- 语气像有经验的老大哥，直接、不留面子，但为他好

输出格式（只输出问题，不要废话）：
Q1: ...
Q2: ...
Q3: ...
"""
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text
        questions = []
        for line in text.strip().split("\n"):
            if line.strip().startswith("Q") and ":" in line:
                questions.append(line.split(":", 1)[1].strip())
        return questions[:3] if questions else default_questions()
    except Exception:
        return default_questions()


def default_questions():
    return [
        "你认识的最有可能成为第一个客户的人是谁？你现在能立刻发微信给他吗？",
        "跟你想法最接近的、已经在做的人是谁？他们做得怎么样？",
        "如果3个月没有收入，你的Plan B是什么？",
    ]


def generate_report(idea, followup_answers, time_status, capital_level):
    answers_text = "\n".join([f"- {k}: {v}" for k, v in followup_answers.items()])

    prompt = f"""你是一位7天启动教练。用户要签一份"7天执行合同"，你必须给他一份极度具体、签了就得干的交付物。

【输入信息】
启动方向：{idea}
障碍回答：
{answers_text}
时间状态：{time_status}
资金量级：{capital_level}

【输出格式】
严格按以下结构输出（Markdown格式）。总字数不超过800字，没有废话。

# 教练判定
用一句话给出判定：【建议7天冲刺 / 谨慎启动 / 建议换方向】
理由不超过两句话。如果判定是"建议换方向"，直接说为什么，不要给后续动作。

# 7天三件事（本周必须完成）
只列3条。每条格式：
1. 【动作】做什么
   - 对象：找谁/做什么
   - 标准：做到什么程度算完成
   - 时间：建议在哪天完成
   - 验收：完成的具体标志是什么

# 第一个客户
逼用户写出一个具体人名。格式：
- 最可能付费的人：______
- 你准备怎么联系他：______
- 他能付多少钱：______
如果用户写不出人名，直接判定这个方向当前不成立，建议换方向。

# 7天止损线
- 时间止损：如果哪天还没结果，必须停？
- 金钱止损：最多再烧多少钱？
- 信号止损：出现什么信号必须立刻换方向？

# 第8天
如果7天内完成了以上3件事，第8天应该做什么？只写一句话。

要求：
- 不超过800字
- 没有废话
- 每个字都在逼用户行动
- 如果信息不足，直接说"信息不足，无法判断"，不要硬编
"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    except Exception as e:
        return f"生成报告时出错：{e}"


def parse_report(report):
    sections = {}
    current_section = None
    current_content = []

    for line in report.split("\n"):
        stripped = line.strip()
        # 支持 # 判定、## 判定、判定：等多种格式
        if stripped.startswith(("# 教练判定", "## 教练判定", "教练判定：", "【教练判定】", "# 判定", "## 判定", "判定：", "【判定】")):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "教练判定"
            current_content = []
        elif stripped.startswith(("# 7天三件事", "## 7天三件事", "7天三件事：", "【7天三件事】", "# 本周3件事", "## 本周3件事", "本周3件事：", "【本周3件事】")):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "7天三件事"
            current_content = []
        elif stripped.startswith(("# 第一个客户", "## 第一个客户", "第一个客户：", "【第一个客户】")):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "第一个客户"
            current_content = []
        elif stripped.startswith(("# 7天止损线", "## 7天止损线", "7天止损线：", "【7天止损线】", "# 止损线", "## 止损线", "止损线：", "【止损线】")):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "7天止损线"
            current_content = []
        elif stripped.startswith(("# 第8天", "## 第8天", "第8天：", "【第8天】")):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "第8天"
            current_content = []
        elif current_section:
            current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


# ===== Session State =====
if "step" not in st.session_state:
    st.session_state.step = 1
if "idea" not in st.session_state:
    st.session_state.idea = ""
if "followup_qs" not in st.session_state:
    st.session_state.followup_qs = []
if "followup_answers" not in st.session_state:
    st.session_state.followup_answers = {}
if "context" not in st.session_state:
    st.session_state.context = {}
if "report" not in st.session_state:
    st.session_state.report = None


# ===== Custom CSS =====
st.markdown("""
<style>
    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none !important;}

    /* Global typography */
    .main {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        max-width: 720px;
        margin: 0 auto;
    }

    /* Hero section */
    .hero {
        text-align: center;
        padding: 3rem 1rem 2rem;
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
        border-radius: 16px;
        margin-bottom: 2rem;
        color: white;
    }
    .hero h1 {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        letter-spacing: -0.02em;
    }
    .hero p {
        font-size: 1rem;
        opacity: 0.8;
        margin: 0;
    }
    .hero-icon {
        font-size: 3rem;
        margin-bottom: 0.5rem;
    }

    /* Cards */
    .stCard {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04);
        border: 1px solid #e2e8f0;
        margin-bottom: 1rem;
    }

    /* Input styling */
    .stTextArea textarea {
        border-radius: 10px !important;
        border: 1.5px solid #cbd5e1 !important;
        font-size: 1rem !important;
        padding: 1rem !important;
        line-height: 1.6 !important;
    }
    .stTextArea textarea:focus {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 3px rgba(37,99,235,0.1) !important;
    }

    /* Selectbox styling */
    .stSelectbox > div > div {
        border-radius: 10px !important;
        border: 1.5px solid #cbd5e1 !important;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 0.75rem 1.5rem !important;
        font-size: 1rem !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        border: none !important;
        box-shadow: 0 4px 14px rgba(37,99,235,0.3) !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(37,99,235,0.4) !important;
    }

    /* Section titles */
    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #e2e8f0;
    }

    /* Verdict cards */
    .verdict-green {
        background: linear-gradient(135deg, #dcfce7, #f0fdf4);
        border-left: 4px solid #22c55e;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    .verdict-yellow {
        background: linear-gradient(135deg, #fef9c3, #fefce8);
        border-left: 4px solid #eab308;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    .verdict-red {
        background: linear-gradient(135deg, #fee2e2, #fef2f2);
        border-left: 4px solid #ef4444;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }

    /* Info badges */
    .info-badge {
        display: inline-block;
        background: #f1f5f9;
        border-radius: 20px;
        padding: 0.35rem 0.9rem;
        font-size: 0.85rem;
        color: #475569;
        margin-bottom: 1rem;
    }

    /* Question cards */
    .question-card {
        background: #f8fafc;
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 0.75rem;
        border: 1px solid #e2e8f0;
    }
    .question-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: #2563eb;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Action items */
    .action-item {
        background: white;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }

    /* Spinner */
    .stSpinner > div {
        border-color: #2563eb !important;
    }

    /* Divider */
    hr {
        border-color: #e2e8f0 !important;
        margin: 2rem 0 !important;
    }

    /* Caption */
    .stCaption {
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
    }

    /* Expander */
    .streamlit-expanderHeader {
        font-size: 0.95rem !important;
        color: #475569 !important;
        background: #f8fafc !important;
        border-radius: 10px !important;
    }

    /* Date input */
    .stDateInput > div > div {
        border-radius: 8px !important;
    }
</style>
""", unsafe_allow_html=True)


# ===== Hero Section =====
st.markdown("""
<div class="hero">
    <div class="hero-icon">🚀</div>
    <h1>7天冷启动加速器</h1>
    <p>用7天从想法到第一个客户，AI 给你执行合同 + 盯着你拿到结果</p>
</div>
""", unsafe_allow_html=True)


# ===== Pending Tasks Alert =====
pending = get_pending_tasks()
if pending:
    with st.container(border=True):
        st.warning(f"⏰ 你有 {len(pending)} 件待办任务到期了")
        for t in pending:
            st.write(f"- {t['action']}（截止：{t['due_date']}）")
        if st.button("标记全部完成", key="mark_all_done"):
            tasks = load_tasks()
            for t in tasks.values():
                if not t.get("done", False) and t.get("due_date", "") <= datetime.now().strftime("%Y-%m-%d"):
                    t["done"] = True
            save_tasks(tasks)
            st.rerun()


# ===== STEP 1: Idea Input =====
if st.session_state.step == 1:
    st.markdown("<div class='section-title'>第一步：锁定你的启动方向</div>", unsafe_allow_html=True)

    idea = st.text_area(
        "",
        value=st.session_state.idea,
        placeholder="例如：帮二三线城市的制造业工厂做抖音短视频代运营，按月收费",
        height=100,
        label_visibility="collapsed",
    )

    col1, col2 = st.columns(2)
    with col1:
        time_status = st.selectbox(
            "你的时间状态",
            ["失业，可以全职投入", "自由职业，时间灵活", "在职，每天能挤出2-3小时", "在职，只能周末做"],
            key="time_status",
        )
    with col2:
        capital_level = st.selectbox(
            "启动资金量级",
            ["几乎为零（< 3000元）", "少量（3,000 - 10,000元）", "中等（1万 - 5万元）", "充裕（5万 - 10万元）", "充足（10万元以上）"],
            key="capital_level",
        )

    if st.button("下一步：拆解执行障碍", use_container_width=True, type="primary"):
        if not idea.strip():
            st.warning("请先描述你想做什么。")
        else:
            st.session_state.idea = idea
            st.session_state.context["time_status"] = time_status
            st.session_state.context["capital_level"] = capital_level
            # 清除旧的追问 widget key，避免新问题残留旧答案
            for k in list(st.session_state.keys()):
                if k.startswith("fq_"):
                    del st.session_state[k]
            st.session_state.followup_answers = {}
            with st.spinner("正在拆解你的执行障碍..."):
                st.session_state.followup_qs = generate_followup_questions(idea)
            st.session_state.step = 2
            st.rerun()


# ===== STEP 2: Follow-up Questions =====
elif st.session_state.step == 2:
    st.markdown("<div class='section-title'>第二步：拆解执行障碍</div>", unsafe_allow_html=True)

    st.markdown(f"<div class='info-badge'>💡 你的方向：{st.session_state.idea}</div>", unsafe_allow_html=True)
    st.caption("这些问题逼你想清楚：谁付钱、怎么找到他、扛得住吗。答完就签7天合同。")

    for i, q in enumerate(st.session_state.followup_qs):
        st.markdown(f"<div class='question-label'>障碍 {i+1}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:1rem; color:#1e293b; margin-bottom:0.5rem; font-weight:500;'>{q}</div>", unsafe_allow_html=True)
        st.text_area(
            "",
            value=st.session_state.followup_answers.get(q, ""),
            key=f"fq_{i}",
            height=80,
            placeholder="直接回答，不要绕弯子",
            label_visibility="collapsed",
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 返回修改方向", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("生成7天执行合同", use_container_width=True, type="primary"):
            answers = {}
            for i, q in enumerate(st.session_state.followup_qs):
                answers[q] = st.session_state.get(f"fq_{i}", "")
            if not all(v.strip() for v in answers.values()):
                st.warning("请回答所有障碍。")
            else:
                st.session_state.followup_answers = answers
                with st.spinner("正在生成7天执行合同..."):
                    st.session_state.report = generate_report(
                        st.session_state.idea,
                        st.session_state.followup_answers,
                        st.session_state.context["time_status"],
                        st.session_state.context["capital_level"],
                    )
                st.session_state.step = 3
                st.rerun()


# ===== STEP 3: Report =====
elif st.session_state.step == 3 and st.session_state.report:
    report = st.session_state.report
    sections = parse_report(report)

    st.markdown("<div class='section-title'>你的7天执行合同</div>", unsafe_allow_html=True)

    # 先取默认值，避免后面 action_lines 报错
    actions = sections.get("7天三件事", sections.get("本周3件事", ""))
    first_customer = sections.get("第一个客户", "")
    stop_loss = sections.get("7天止损线", sections.get("止损线", ""))
    verdict = sections.get("教练判定", sections.get("判定", ""))
    day8 = sections.get("第8天", "")

    # Fallback: if parsing failed completely, show raw report
    if not sections:
        st.info("AI 返回的报告格式与预期不同，以下是原始内容：")
        st.markdown(report)
    else:
        # Verdict card
        if "换方向" in verdict or "不建议" in verdict:
            st.markdown(f"<div class='verdict-red'><strong>🎯 教练判定</strong><br/>{verdict.replace(chr(10), '<br/>')}</div>", unsafe_allow_html=True)
        elif "谨慎" in verdict:
            st.markdown(f"<div class='verdict-yellow'><strong>🎯 教练判定</strong><br/>{verdict.replace(chr(10), '<br/>')}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='verdict-green'><strong>🎯 教练判定</strong><br/>{verdict.replace(chr(10), '<br/>')}</div>", unsafe_allow_html=True)

        with st.container(border=True):
            st.subheader("⚡ 7天三件事（签了就得干）")
            st.markdown(actions)

        with st.container(border=True):
            st.subheader("👤 第一个客户")
            st.markdown(first_customer)

        with st.container(border=True):
            st.subheader("🛑 7天止损线")
            st.markdown(stop_loss)

        if day8:
            with st.container(border=True):
                st.subheader("📅 第8天")
                st.markdown(day8)

    # Expandable details
    with st.expander("📊 展开看完整合同（可选）"):
        st.markdown(report)

    # Action tracking
    st.divider()
    st.markdown("<div class='section-title'>📅 任务追踪</div>", unsafe_allow_html=True)
    st.caption("给这3件事设定完成日期，我们会提醒你")

    action_lines = [line.strip() for line in actions.split("\n") if line.strip().startswith("1.") or line.strip().startswith("2.") or line.strip().startswith("3.")]

    tasks_to_save = {}
    for i, line in enumerate(action_lines[:3]):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"<div class='action-item'>{line}</div>", unsafe_allow_html=True)
        with c2:
            due = st.date_input(
                f"截止日期 {i+1}",
                value=datetime.now() + timedelta(days=3),
                key=f"due_{i}",
            )
            tasks_to_save[f"task_{datetime.now().timestamp()}_{i}"] = {
                "action": line,
                "due_date": due.strftime("%Y-%m-%d"),
                "done": False,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

    if st.button("保存任务并设置提醒", use_container_width=True):
        existing = load_tasks()
        existing.update(tasks_to_save)
        save_tasks(existing)
        st.success("✅ 任务已保存。下次打开时会提醒你。")

    # CTA: 陪跑入口
    st.divider()
    with st.container(border=True):
        st.subheader("💬 需要人盯着你跑完这7天？")
        st.markdown("""
        很多人卡在"知道该做什么，但做不到"。

        **7天陪跑（99元）包含：**
        - 每天检查你完成了哪件
        - 卡住了随时问，当天给解法
        - 第7天复盘，没结果退一半

        **加我微信，备注"7天"：** `你的微信号`

        *(把上面"你的微信号"改成你的真实微信，用户才能找到你)*
        """)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 重新回答", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with col2:
        if st.button("🔄 换个新方向", use_container_width=True):
            st.session_state.step = 1
            st.session_state.idea = ""
            st.session_state.followup_qs = []
            st.session_state.followup_answers = {}
            st.session_state.report = None
            st.rerun()

    st.caption("⚠️ 本合同由 AI 基于你提供的信息生成，签完就得干。")
