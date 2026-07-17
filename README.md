---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: e066e2c279c31e9848da59eaf3379606_303fb75f81a711f18a64525400826444
    ReservedCode1: wgpBlabmqLGyrT8IAqK81x3YWH4o6WwD9DIOJkhYDsknG00ysOYoxjNgWGw2enhBP1USmRkU12C08ZaON+FCFN9d64LKnjihmuB05ynFiCuFU2TQIdkX9aj1pWrbCmkKRRZwiMadvU40gcmjxXPkSXUSIVD3Y6Qqckq6kEKshXFS+LCP87dTL2E3kdY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: e066e2c279c31e9848da59eaf3379606_303fb75f81a711f18a64525400826444
    ReservedCode2: wgpBlabmqLGyrT8IAqK81x3YWH4o6WwD9DIOJkhYDsknG00ysOYoxjNgWGw2enhBP1USmRkU12C08ZaON+FCFN9d64LKnjihmuB05ynFiCuFU2TQIdkX9aj1pWrbCmkKRRZwiMadvU40gcmjxXPkSXUSIVD3Y6Qqckq6kEKshXFS+LCP87dTL2E3kdY=
---

# Weibo Cleaner 🧹

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

一个功能完整的微博批量清理命令行工具。支持按时间、类型等条件筛选并批量删除微博，内置风控保护、进度显示和干跑预览模式。

---

## ✨ 功能特性

| 模块 | 功能 |
|------|------|
| 🔐 登录 | Cookie 字符串 / 本地文件加载 / 扫码引导三种方式 |
| 📥 拉取 | 调用微博 Ajax API 逐页抓取全部微博 |
| 🔍 筛选 | 按时间范围 (`--since` / `--before`)、类型（原创/转发/图片/视频）过滤 |
| 🗑️ 删除 | 批量删除，兼容新旧两套删除 API |
| 🛡️ 风控保护 | 可设删除间隔、风控冷却时间，连续失败自动暂停 |
| 👁️ 预览模式 | `--dry-run` 先列出所有待删微博，确认无误再执行 |
| 📊 进度显示 | 实时输出 `[当前/总数] 时间 mid 状态 (成功/失败计数)` |
| 🔄 错误重试 | 自动重试最多 3 次，风控 403/429 自动递增等待 |

---

## 📦 安装

### 环境要求

- Python 3.8+
- pip

### 安装依赖

```bash
pip install requests
```

### 下载

```bash
git clone https://github.com/yourname/weibo-cleaner.git
cd weibo-cleaner
```

或直接下载 `weibo_cleaner.py` 到本地任意目录。

---

## 🚀 快速开始

### 1. 预览模式（推荐首次使用）

先用 `--dry-run` 预览要删除的内容，确认无误后再真正执行。

```bash
# 预览所有微博
python weibo_cleaner.py --dry-run

# 预览 2023 年之前的微博
python weibo_cleaner.py --dry-run --before 2023-01-01

# 仅预览转发类微博
python weibo_cleaner.py --dry-run --type repost

# 预览 2024 年 1 月到 6 月之间的原创微博
python weibo_cleaner.py --dry-run --since 2024-01-01 --before 2024-06-30 --type original
```

### 2. 执行删除

确认无误后，加上 `--confirm` 执行真正的删除。

```bash
# 删除 2022 年之前的所有转发微博，间隔 3 秒
python weibo_cleaner.py --before 2022-01-01 --type repost --confirm --interval 3.0

# 删除最近一周的原创微博
python weibo_cleaner.py --since 2026-07-10 --type original --confirm

# 删除全部微博（谨慎操作！）
python weibo_cleaner.py --all --confirm --interval 3.0
```

---

## 📖 完整参数说明

```
usage: weibo_cleaner.py [-h] [--cookie COOKIE] [--scan]
                        [--since SINCE] [--before BEFORE]
                        [--type {original,repost,image,video}]
                        [--all] [--max-pages MAX_PAGES]
                        [--dry-run | --confirm]
                        [--interval INTERVAL] [--cooldown COOLDOWN]
                        [--uid UID]
```

### 登录方式

| 参数 | 说明 |
|------|------|
| `--cookie` | Cookie 字符串，格式：`'key1=val1; key2=val2'` |
| `--scan` | 扫码登录引导模式 |

> 不指定登录方式时，默认从 `~/.weibo_cleaner/cookies.json` 加载已保存的 Cookie。

### 筛选条件

| 参数 | 说明 |
|------|------|
| `--since` | 起始日期（含），格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM:SS` |
| `--before` | 截止日期（含），格式同上 |
| `--type` | 微博类型：`original`(原创) / `repost`(转发) / `image`(图片) / `video`(视频) |
| `--all` | 拉取全部微博（默认最多 2000 条） |
| `--max-pages` | 最大拉取页数（0=全部，需配合 `--all`） |
| `--uid` | 指定要清理的 UID（默认当前登录账号） |

### 操作模式（二选一）

| 参数 | 说明 |
|------|------|
| `--dry-run` | 预览模式：仅列出待删除微博，不执行删除 |
| `--confirm` | 确认删除模式：真正执行删除 |

### 删除设置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--interval` | 2.0 | 每次删除间隔（秒），建议 ≥2 |
| `--cooldown` | 60 | 触发风控时冷却等待时间（秒） |

---

## 🔐 如何获取 Cookie

1. 在浏览器中打开 [weibo.com](https://weibo.com) 并登录
2. 按 `F12` → **Application** → **Cookies** → `https://weibo.com`
3. 找到 `SUB` 字段，复制其值
4. 使用以下命令：

```bash
python weibo_cleaner.py --cookie "SUB=你的SUB值; _T_WM=你的_T_WM值" --dry-run
```

Cookie 登录成功一次后会自动保存到 `~/.weibo_cleaner/cookies.json`，下次无需再传。

---

## ⚠️ 注意事项

- **删除不可逆**：微博删除后无法恢复，建议先用 `--dry-run` 预览
- **风控机制**：短时间内大量删除可能触发微博风控，建议设置 `--interval` ≥ 2 秒
- **Cookie 有效期**：Cookie 过期后需重新登录
- **数量限制**：默认最多拉取 2000 条，使用 `--all` 可获取全部

---

## 📁 文件结构

```
~/.weibo_cleaner/
├── cookies.json    # 自动保存的 Cookie（登录成功后生成）
└── config.json     # 配置文件（预留）
```

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

---

## 📄 许可证

MIT License
