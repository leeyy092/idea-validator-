import os
import json
import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

st.set_page_config(page_title="创业想法验证器", page_icon="🧭", layout="centered")

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    st.error("⚠️ 未检测到 ANTHROPIC_API_KEY。请创建 .env 文件并填入你的 API Key。")
    st.code("cp .env.example .env\n# 然后编辑 .env 文件", language="bash")
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


# ===== Functions =====
def generate_followup_questions(idea):
    prompt = f"""你是一位极其直接、不留情面的商业验证顾问。用户有一个创业想法，你要用3个问题直接戳破他的假设，逼他面对现实。

用户的想法：{idea}

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

    prompt = f"""你是一位收费 500元/小时的商业验证顾问。用户付费请你帮他验证一个创业想法，你必须给出一份极度精简、可直接执行的交付物。

【输入信息】
想法：{idea}
追问回答：
{answers_text}
时间状态：{time_status}
资金量级：{capital_level}

【输出格式】
严格按以下结构输出（Markdown格式）。总字数不超过800字，没有废话。

# 判定
用一句话给出判定：【建议做 / 谨慎试水 / 建议换方向】
理由不超过两句话。

# 本周3件事
列出3条具体动作。每条格式：
1. 【动作】做什么
   - 对象：找谁/做什么
   - 标准：做到什么程度算完成
   - 时间：建议在哪天完成

# 第一个客户
逼用户写出一个具体人名。格式：
- 最可能付费的人：______
- 你准备怎么联系他：______
- 他能付多少钱：______
如果用户写不出人名，直接判定这个想法当前不成立。

# 止损线
- 时间止损：______
- 金钱止损：______
- 信号止损：出现什么信号必须停

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
    """Parse report into sections."""
    sections = {}
    current_section = None
    current_content = []

    for line in report.split("\n"):
        if line.startswith("# 判定"):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "判定"
            current_content = []
        elif line.startswith("# 本周3件事"):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "本周3件事"
            current_content = []
        elif line.startswith("# 第一个客户"):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "第一个客户"
            current_content = []
        elif line.startswith("# 止损线"):
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "止损线"
            current_content = []
        elif current_section:
            current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


# ===== Header =====
st.title("🧭 创业想法验证器")
st.caption("不帮你做梦，帮你算清账。输出一张可执行的决策卡片。")

# Check pending tasks
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
    idea = st.text_area(
        "你想做什么生意/服务？（一句话说清楚）",
        value=st.session_state.idea,
        placeholder="例如：帮二三线城市的制造业工厂做抖音短视频代运营，按月收费",
        height=80,
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

    if st.button("下一步：回答关键问题", use_container_width=True):
        if not idea.strip():
            st.warning("请先描述你想做什么。")
        else:
            st.session_state.idea = idea
            st.session_state.context["time_status"] = time_status
            st.session_state.context["capital_level"] = capital_level
            with st.spinner("正在分析你的想法..."):
                st.session_state.followup_qs = generate_followup_questions(idea)
            st.session_state.step = 2
            st.rerun()


# ===== STEP 2: Follow-up Questions =====
elif st.session_state.step == 2:
    st.subheader("💬 回答这 3 个关键问题")
    st.info(f"你的想法：{st.session_state.idea}")
    st.caption("这些问题是 AI 根据你的想法生成的，目的是逼你想清楚最关键的细节。")

    for i, q in enumerate(st.session_state.followup_qs):
        st.session_state.followup_answers[q] = st.text_area(
            f"问题 {i+1}：{q}",
            value=st.session_state.followup_answers.get(q, ""),
            key=f"fq_{i}",
            height=80,
            placeholder="直接回答，不要绕弯子",
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 返回修改想法", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("生成决策卡片", use_container_width=True, type="primary"):
            if not all(st.session_state.followup_answers.get(q, "").strip() for q in st.session_state.followup_qs):
                st.warning("请回答所有问题。")
            else:
                with st.spinner("正在生成决策卡片..."):
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

    # Parse report sections
    sections = parse_report(report)

    # Verdict card
    verdict = sections.get("判定", "无法解析")
    verdict_color = "green"
    if "换方向" in verdict or "不建议" in verdict:
        verdict_color = "red"
    elif "谨慎" in verdict:
        verdict_color = "orange"

    with st.container(border=True):
        st.subheader("🎯 判定")
        if verdict_color == "green":
            st.success(verdict)
        elif verdict_color == "red":
            st.error(verdict)
        else:
            st.warning(verdict)

    # 3 actions
    actions = sections.get("本周3件事", "")
    with st.container(border=True):
        st.subheader("⚡ 本周3件事")
        st.markdown(actions)

    # First customer
    first_customer = sections.get("第一个客户", "")
    with st.container(border=True):
        st.subheader("👤 第一个客户")
        st.markdown(first_customer)

    # Stop loss
    stop_loss = sections.get("止损线", "")
    with st.container(border=True):
        st.subheader("🛑 止损线")
        st.markdown(stop_loss)

    # Expandable details
    with st.expander("📊 展开看详细推演（可选）"):
        st.markdown(report)

    # Action tracking
    st.divider()
    st.subheader("📅 任务追踪")
    st.caption("给这3件事设定完成日期，我们会提醒你")

    action_lines = [line.strip() for line in actions.split("\n") if line.strip().startswith("1.") or line.strip().startswith("2.") or line.strip().startswith("3.")]

    col_save = True
    tasks_to_save = {}
    for i, line in enumerate(action_lines[:3]):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.write(f"{line}")
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
        st.success("任务已保存。下次打开时会提醒你。")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 重新回答", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with col2:
        if st.button("🔄 换个新想法", use_container_width=True):
            st.session_state.step = 1
            st.session_state.idea = ""
            st.session_state.followup_qs = []
            st.session_state.followup_answers = {}
            st.session_state.report = None
            st.rerun()

    st.caption("⚠️ 本报告由 AI 基于你提供的信息生成，仅供参考。")
