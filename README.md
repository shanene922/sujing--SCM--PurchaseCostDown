# 供应链降本分析

这是一个可本机运行的 Streamlit 多页面数据看板项目，用于将 Power BI 的“供应链降本分析”迁移到 Streamlit。

项目重点实现：
- 深色主题多页面仪表板
- 飞书在线表格读取
- Power BI 核心指标口径迁移
- 左侧全局筛选器联动所有页面
- 页面切换后筛选状态保留
- Plotly 图表点击联动下方表格 / 矩阵
- AgGrid 矩阵与树形层级展示

## 项目结构

```text
project_root/
  .python-version
  app.py
  pyproject.toml
  uv.lock
  pages/
    1_采购降本整体情况.py
    2_Sourcing降本情况.py
    3_各供应商降本情况.py
  src/
    __init__.py
    config.py
    styles.py
    state.py
    data_loader.py
    feishu_client.py
    feishu_sheets.py
    transforms.py
    date_dim.py
    metrics.py
    filters.py
    charts.py
    tables.py
    utils.py
  tools/
    uv-workflow.ps1
    install-uv-workflow.ps1
  .env.example
  requirements.txt
  README.md
```

## 安装步骤（uv）

1. 安装 uv（仅首次）

```powershell
winget install --id=astral-sh.uv -e
```

2. 初始化/迁移并同步依赖（当前项目）

```powershell
.\tools\uv-workflow.ps1 bootstrap -ProjectPath . -Name supplychain-purchase-costdown-streamlit -PythonVersion 3.12
```

3. 运行应用

```powershell
uv run -m streamlit run app.py
```

## .env 配置说明

复制 `.env.example` 为 `.env`，并按实际信息填写：

```env
APP_ID=
APP_SECRET=
SPREADSHEET_TOKEN=
SHEET_ID=
Purchase_CostDown_URL=
```

说明：
- 支持 `APP_ID` / `APP_SECRET`
- 同时兼容你现有工程里的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`
- 若未填写 `SPREADSHEET_TOKEN` 和 `SHEET_ID`，程序会自动从 `Purchase_CostDown_URL` 中解析


## 运行方式

```powershell
uv run -m streamlit run app.py
```

浏览器打开后：
- 首页为项目说明与预览
- 详细分析页面请从左侧 Pages 导航进入

## 部署到公司内部云

- 推荐容器化部署（Docker/K8s），并通过环境变量注入密钥（不要提交 `.env`）。
- 可复用本仓库 `tools/uv-workflow.ps1` 做初始化/同步/运行自动化。
- 生产环境建议默认 `APP_DEBUG=false`，避免展示调试数据面板。

## 页面说明

### 1. 采购降本整体情况
- 顶部 5 个 KPI 卡片
- 入库金额 vs 总降本金额（负）组合图
- 总降本金额（负） vs 降本百分比组合图
- 降本类别圆环图
- 按 SOURCING 的降本百分比折线图
- 点击图表后，下方联动明细表过滤

### 2. Sourcing降本情况
- 支持指标切换：降本百分比 / 总入库金额 / 总降本金额（负）
- 按 SOURCING 的时间趋势图
- 两张 AgGrid 矩阵，支持树形展开、横向滚动、排序与过滤

### 3. 各供应商降本情况
- 顶部 KPI：降本供应商数量、涨价供应商数量
- 横向簇状柱图展示各供应商的综合降本、降价与涨价金额
- 支持 Top N 切换
- 点击供应商后联动两个矩阵

## 已实现功能

- 飞书 tenant_access_token 获取
- 飞书 Sheets values 接口读取
- 表头探针读取与第一行有效表头识别
- 分块读取大表
- 分块失败后二分重试
- 删除全空行、向下填充、类型转换、日期兼容 Excel 序列
- 自动构建日期维表 `Date_2026` 的可扩展版
- 指标集中封装在 `src/metrics.py`
- 全局筛选器使用 `session_state` 保持跨页状态
- `刷新数据` 按钮清理缓存并重新拉取飞书数据
- Plotly 点击联动 + AgGrid 明细/矩阵

