# 商业想法验证器

## 项目定位
一个极简 Web 工具，帮助自由职业者、副业人群、小创业者快速验证商业想法的可行性。

## 技术栈
- Python 3.10+
- Streamlit（前端/UI）
- Anthropic Claude API（分析引擎）
- python-dotenv（环境变量管理）

## 目录结构
```
idea-validator/
├── CLAUDE.md           # 本项目规范
├── requirements.txt    # 依赖
├── .env.example        # 环境变量模板
├── .gitignore          # Git 忽略规则
└── app.py              # 主应用
```

## 运行方式

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY

# 4. 启动
streamlit run app.py
```

## 核心功能
1. 用户输入商业想法、预期收入、成本结构、时间投入、启动资金
2. 调用 Claude API 生成结构化分析报告
3. 报告包含：结论、盈亏测算、风险点、起步建议、行动清单

## 约束
- API Key 必须从环境变量读取，不得硬编码
- UI 使用中文
- 代码简洁，非程序员用户也能看懂和修改
- 不存储任何用户数据
