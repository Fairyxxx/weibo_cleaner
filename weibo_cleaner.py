#!/usr/bin/env python3
"""
微博清理工具 (Weibo Cleaner)
=============================
功能完整的微博批量清理命令行工具，支持：
  - Cookie 登录 / 手动扫码登录
  - 获取全部微博列表（原创、转发、图片、视频等）
  - 按时间范围筛选
  - 按类型筛选
  - 批量删除（可设删除间隔防风控）
  - 实时进度显示
  - 错误处理与自动重试
  - dry-run 预览模式
  - 命令行参数接口

依赖：pip install requests
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

# ─── 常量 ─────────────────────────────────────────────
DEFAULT_CONFIG_DIR = os.path.expanduser("~/.weibo_cleaner")
COOKIE_FILE = os.path.join(DEFAULT_CONFIG_DIR, "cookies.json")
CONFIG_FILE = os.path.join(DEFAULT_CONFIG_DIR, "config.json")
LOGIN_URL = "https://passport.weibo.cn/signin/login"
PRELOGIN_URL = "https://login.sina.com.cn/sso/prelogin.php"
SSO_LOGIN_URL = "https://passport.weibo.cn/sso/login"
USER_INFO_URL = "https://api.weibo.com/2/users/show.json"
MYMBLOGLIST_URL = "https://weibo.com/ajax/profile/mbloglist"
DEL_URL = "https://weibo.com/ajax/profile/destroy"
DEL_URL_OLD = "https://weibo.com/aj/mblog/del"

# UA
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

# 东八区时区
TZ_CN = timezone(timedelta(hours=8))


# ─── 工具函数 ─────────────────────────────────────────
def now_str() -> str:
    return datetime.now(TZ_CN).strftime("%Y-%m-%d %H:%M:%S")


def make_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://weibo.com/",
    }
    if extra:
        h.update(extra)
    return h


def parse_weibo_time(created_at: str) -> Optional[datetime]:
    """解析微博时间字符串，返回带时区的 datetime"""
    if not created_at:
        return None
    # 格式示例："Fri Jul 11 14:30:00 +0800 2025"
    try:
        return datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        pass
    try:
        return datetime.strptime(created_at, "%a %b %d %H:%M:%S +0800 %Y")
    except ValueError:
        pass
    return None


def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── 登录模块 ─────────────────────────────────────────
class WeiboLogin:
    """处理微博登录，支持 cookie 和扫码两种方式"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(make_headers())
        self.uid: Optional[str] = None
        self.nickname: Optional[str] = None

    def login_by_cookie(
        self, cookie_str: Optional[str] = None
    ) -> Tuple[bool, str]:
        """通过 cookie 字符串或文件中的 cookie 登录"""
        cookies = {}

        # 优先使用传入的 cookie 字符串
        if cookie_str:
            for item in cookie_str.split(";"):
                item = item.strip()
                if "=" in item:
                    k, v = item.split("=", 1)
                    cookies[k.strip()] = v.strip()
        else:
            # 尝试从文件加载
            saved = load_json(COOKIE_FILE)
            cookies = saved.get("cookies", {})
            if not cookies:
                return False, f"未提供 cookie，且 {COOKIE_FILE} 中无已保存的 cookie。"

        for k, v in cookies.items():
            self.session.cookies.set(k, v, domain=".weibo.com")

        return self._verify_login()

    def login_by_scan(self) -> Tuple[bool, str]:
        """扫码登录（简化版：引导用户用浏览器扫码获取 cookie）"""
        print(f"[{now_str()}] 扫码登录需要手动获取 cookie。")
        print("  1. 在浏览器中打开 https://weibo.com 并登录")
        print("  2. 按 F12 → Application → Cookies → https://weibo.com")
        print(
            "  3. 复制所有 cookie，格式如 "
            '"SUB=xxx; _T_WM=yyy; ..."'
        )
        print()
        cookie_str = input("请粘贴 cookie 字符串: ").strip()
        if not cookie_str:
            return False, "未输入 cookie。"

        return self.login_by_cookie(cookie_str)

    def _verify_login(self) -> Tuple[bool, str]:
        """验证登录状态"""
        try:
            resp = self.session.get(
                "https://weibo.com/ajax/profile/info",
                headers=make_headers({"Referer": "https://weibo.com/"}),
                timeout=15,
            )
            if resp.status_code != 200:
                return False, f"请求失败，HTTP {resp.status_code}"

            data = resp.json()
            if data.get("ok") == 1:
                user = data.get("data", {}).get("user", {})
                self.uid = str(user.get("id", ""))
                self.nickname = user.get("screen_name", "未知用户")
                self._save_cookies()
                return True, f"登录成功：{self.nickname} (UID: {self.uid})"
            else:
                return False, "cookie 已过期或无效，请重新登录。"
        except Exception as e:
            return False, f"验证登录时出错: {e}"

    def _save_cookies(self):
        """保存 cookie 到文件"""
        cookies = {}
        for cookie in self.session.cookies:
            cookies[cookie.name] = cookie.value
        save_json(COOKIE_FILE, {"cookies": cookies, "uid": self.uid,
                                "nickname": self.nickname})
        print(f"[{now_str()}] Cookie 已保存到 {COOKIE_FILE}")


# ─── 微博获取模块 ─────────────────────────────────────
class WeiboFetcher:
    """获取微博列表，支持分页与筛选"""

    def __init__(self, session: requests.Session, uid: str):
        self.session = session
        self.uid = uid
        self.containerid: Optional[str] = None

    def _get_containerid(self) -> bool:
        """获取个人主页微博列表的 containerid"""
        url = f"https://weibo.com/ajax/profile/info?uid={self.uid}"
        try:
            resp = self.session.get(
                url, headers=make_headers({"Referer": "https://weibo.com/"}), timeout=15
            )
            data = resp.json()
            if data.get("ok") == 1:
                tabs = (
                    data.get("data", {})
                    .get("tabsInfo", {})
                    .get("tabs", [])
                )
                for tab in tabs:
                    if tab.get("tab_type") == "weibo":
                        self.containerid = tab.get("containerid")
                        return True
            return False
        except Exception:
            return False

    def fetch_all(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        types: Optional[List[str]] = None,
        page_count: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        拉取微博列表。
        since:  起始时间（含），东八区 datetime
        until:  结束时间（含），东八区 datetime
        types:  类型筛选列表，可选值: 'original'(原创), 'repost'(转发),
                'image'(图片), 'video'(视频)
        page_count: 0=全部, >0=最大页数
        """
        if not self.containerid and not self._get_containerid():
            print(f"[{now_str()}] 无法获取 containerid，请确认 UID 正确。")
            return []

        all_mblogs = []
        page = 1
        since_str = ""
        retry_count = 0
        max_retries = 3

        while True:
            params = {
                "uid": self.uid,
                "containerid": self.containerid,
                "page": page,
                "feature_type": "all",
            }
            if since_str:
                params["since_id"] = since_str

            try:
                resp = self.session.get(
                    MYMBLOGLIST_URL,
                    params=params,
                    headers=make_headers(
                        {"Referer": f"https://weibo.com/u/{self.uid}"}
                    ),
                    timeout=20,
                )

                if resp.status_code == 403 or resp.status_code == 429:
                    retry_count += 1
                    if retry_count > max_retries:
                        print(f"[{now_str()}] 触发风控，已达到最大重试次数，停止拉取。")
                        break
                    wait = 30 * retry_count
                    print(
                        f"[{now_str()}] HTTP {resp.status_code}，"
                        f"等待 {wait} 秒后重试 ({retry_count}/{max_retries})..."
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
                retry_count = 0  # 恢复重试计数

                if data.get("ok") != 1:
                    break

                cards = data.get("data", {}).get("cards", [])
                if not cards:
                    break

                for card in cards:
                    mblog = card.get("mblog")
                    if not mblog:
                        continue

                    # 过滤广告、推荐
                    if card.get("card_type") != 9:
                        continue

                    # 时间筛选
                    created_str = mblog.get("created_at", "")
                    created_dt = parse_weibo_time(created_str)
                    if created_dt:
                        if since and created_dt < since:
                            continue
                        if until and created_dt > until:
                            continue
                    else:
                        # 无法解析时间则跳过
                        continue

                    # 类型筛选
                    if types:
                        weibo_type = classify_weibo(mblog)
                        if weibo_type not in types:
                            continue

                    all_mblogs.append(mblog)

                # 分页控制
                if page_count > 0 and page >= page_count:
                    break
                since_str = data.get("data", {}).get("since_id", "")
                if not since_str:
                    break
                page += 1
                time.sleep(0.8)  # 请求间隔，避免触发风控

            except requests.RequestException as e:
                retry_count += 1
                if retry_count > max_retries:
                    print(f"[{now_str()}] 网络错误已达上限: {e}")
                    break
                print(f"[{now_str()}] 请求出错: {e}，等待后重试...")
                time.sleep(10)
                continue

        return all_mblogs


def classify_weibo(mblog: dict) -> str:
    """对单条微博做类型判定"""
    retweeted = mblog.get("retweeted_status")
    if retweeted:
        return "repost"

    # 判断是否包含图片
    pic_ids = mblog.get("pic_ids") or []
    pic_infos = mblog.get("pic_infos") or {}
    has_image = bool(pic_ids or pic_infos)

    # 判断是否包含视频
    page_info = mblog.get("page_info", {})
    has_video = page_info.get("type") == "video" or bool(
        mblog.get("video_cover")
    )
    # 也检查 mix_media_info
    mix_media = mblog.get("mix_media_info", {})
    if (
        mix_media
        and isinstance(mix_media, dict)
        and mix_media.get("items")
    ):
        for item in mix_media["items"]:
            if isinstance(item, dict) and item.get("type") == "video":
                has_video = True
                break

    if has_video:
        return "video"
    if has_image:
        return "image"
    return "original"


def summarize_weibo(mblog: dict, index: int) -> str:
    """生成微博摘要（用于预览）"""
    mid = mblog.get("mid", "")
    text = mblog.get("text_raw", "") or mblog.get("text", "")
    # 去掉 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    if len(text) > 60:
        text = text[:57] + "..."

    created_str = mblog.get("created_at", "")
    dt = parse_weibo_time(created_str)
    time_str = dt.strftime("%Y-%m-%d %H:%M") if dt else created_str

    wtype = classify_weibo(mblog)
    type_label = {"original": "原创", "repost": "转发",
                  "image": "图片", "video": "视频"}.get(wtype, wtype)

    return f"[{index}] {time_str} [{type_label}] {mid}  {text}"


# ─── 删除模块 ─────────────────────────────────────────
class WeiboDeleter:
    """批量删除微博"""

    def __init__(self, session: requests.Session, uid: str):
        self.session = session
        self.uid = uid
        self.delete_count = 0
        self.fail_count = 0

    def delete_one(self, mblog: dict) -> Tuple[bool, str]:
        """删除单条微博，返回 (成功, 信息)"""
        mid = mblog.get("mid", "")
        if not mid:
            return False, "缺少 mid"

        # 构建 referer
        referer = f"https://weibo.com/{self.uid}/{mid}"

        # 新接口
        try:
            resp = self.session.post(
                DEL_URL,
                json={"mid": mid},
                headers=make_headers({"Referer": referer}),
                timeout=15,
            )
            data = resp.json()
            if data.get("ok") == 1:
                return True, "删除成功"
            elif data.get("ok") == 0:
                msg = data.get("msg", "未知错误")
                return False, f"删除失败: {msg}"
        except Exception as e:
            pass

        # 兼容老接口
        try:
            resp = self.session.post(
                DEL_URL_OLD,
                data={"mid": mid},
                headers=make_headers({
                    "Referer": referer,
                    "Content-Type": "application/x-www-form-urlencoded",
                }),
                timeout=15,
            )
            data = resp.json()
            if data.get("code") == "100000":
                return True, "删除成功 (旧接口)"
            return False, f"删除失败: {data.get('msg', '未知')}"
        except Exception as e:
            return False, f"请求异常: {e}"

    def batch_delete(
        self,
        mblogs: List[Dict[str, Any]],
        interval: float = 2.0,
        cooldown_on_err: int = 60,
    ) -> Tuple[int, int]:
        """
        批量删除微博
        interval:       每次删除间隔（秒），建议 ≥2
        cooldown_on_err: 删除失败时的冷却时间（秒）
        返回 (成功数, 失败数)
        """
        total = len(mblogs)
        self.delete_count = 0
        self.fail_count = 0
        consecutive_fails = 0
        max_consecutive_fails = 5

        print(f"\n[{now_str()}] 开始删除，共 {total} 条，间隔 {interval} 秒")
        print("-" * 50)

        for i, mblog in enumerate(mblogs, 1):
            mid = mblog.get("mid", "?")
            created_str = mblog.get("created_at", "")
            dt = parse_weibo_time(created_str)
            time_str = dt.strftime("%Y-%m-%d %H:%M") if dt else created_str

            ok, msg = self.delete_one(mblog)

            if ok:
                self.delete_count += 1
                consecutive_fails = 0
                status = "OK"
            else:
                self.fail_count += 1
                consecutive_fails += 1
                status = f"FAIL: {msg}"
                # 可能是触发了风控
                if "验证" in msg or "频繁" in msg or "403" in msg:
                    print(
                        f"[{now_str()}] 疑似触发风控，"
                        f"冷却 {cooldown_on_err} 秒..."
                    )
                    time.sleep(cooldown_on_err)
                    consecutive_fails = 0  # 冷却后重置计数
                    continue

            # 进度：当前/总数  成功/失败
            progress = f"[{i}/{total}]"
            print(
                f"{progress} {time_str} mid={mid}  {status}  "
                f"(成功:{self.delete_count} 失败:{self.fail_count})"
            )

            # 连续失败过多则暂停
            if consecutive_fails >= max_consecutive_fails:
                print(
                    f"\n[{now_str()}] 连续失败 {consecutive_fails} 次，"
                    f"暂停 {cooldown_on_err} 秒..."
                )
                time.sleep(cooldown_on_err)
                consecutive_fails = 0

            # 删除间隔
            if i < total:
                time.sleep(interval)

        print("-" * 50)
        print(
            f"[{now_str()}] 删除完毕。"
            f"成功: {self.delete_count}, 失败: {self.fail_count}"
        )
        return self.delete_count, self.fail_count


# ─── 主程序 ───────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="微博清理工具 - 批量管理/删除微博",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 预览所有微博（dry-run）
  python weibo_cleaner.py --dry-run

  # 预览 2023 年之前的微博
  python weibo_cleaner.py --dry-run --before 2023-01-01

  # 只预览转发的微博
  python weibo_cleaner.py --dry-run --type repost

  # 删除 2022 年之前的所有转发微博
  python weibo_cleaner.py --before 2022-01-01 --type repost --confirm

  # 删除最近一周的原创微博，间隔 3 秒
  python weibo_cleaner.py --since 2026-07-10 --type original --interval 3.0 --confirm

  # 使用 cookie 文件登录
  python weibo_cleaner.py --cookie "SUB=xxx; _T_WM=yyy; ..." --dry-run

  # 扫码登录后删除所有微博（谨慎!)
  python weibo_cleaner.py --all --confirm --interval 3.0
        """,
    )

    # ── 登录 ──
    login_group = p.add_argument_group("登录方式")
    login_group.add_argument(
        "--cookie",
        type=str,
        default=None,
        help="Cookie 字符串，格式: 'key1=val1; key2=val2; ...'",
    )
    login_group.add_argument(
        "--scan",
        action="store_true",
        help="使用扫码登录引导方式",
    )

    # ── 筛选 ──
    filter_group = p.add_argument_group("筛选条件")
    filter_group.add_argument(
        "--since",
        type=str,
        default=None,
        help="起始日期（含），格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
    )
    filter_group.add_argument(
        "--before",
        type=str,
        default=None,
        help="截止日期（含），格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
    )
    filter_group.add_argument(
        "--type",
        type=str,
        default=None,
        choices=["original", "repost", "image", "video"],
        help="微博类型筛选",
    )
    filter_group.add_argument(
        "--all",
        action="store_true",
        help="获取全部微博（默认仅获取前 2000 条）",
    )
    filter_group.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="最大拉取页数（0=全部，需配合 --all）",
    )

    # ── 操作 ──
    action_group = p.add_argument_group("操作模式")
    action_group.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式：仅列出要删除的微博，不执行删除",
    )
    action_group.add_argument(
        "--confirm",
        action="store_true",
        help="确认执行删除。必须与 --dry-run 互斥",
    )

    # ── 删除设置 ──
    del_group = p.add_argument_group("删除设置")
    del_group.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="每次删除间隔秒数（默认 2.0，建议 ≥2 避免风控）",
    )
    del_group.add_argument(
        "--cooldown",
        type=int,
        default=60,
        help="触发风控时冷却等待秒数（默认 60）",
    )

    # ── UID ──
    p.add_argument(
        "--uid",
        type=str,
        default=None,
        help="指定要清理的 UID（默认使用当前登录账号）",
    )

    return p


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """解析命令行传入的日期时间"""
    if not value:
        return None
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=TZ_CN)
        except ValueError:
            continue
    print(f"[ERROR] 无法解析日期: {value}，请使用 YYYY-MM-DD 格式")
    sys.exit(1)


def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── 参数校验 ──
    if args.dry_run and args.confirm:
        print("[ERROR] --dry-run 和 --confirm 不能同时使用。")
        sys.exit(1)
    if not args.dry_run and not args.confirm:
        print("[ERROR] 必须指定 --dry-run（预览）或 --confirm（确认删除）。")
        sys.exit(1)
    if args.confirm and args.interval < 1.0:
        print(
            "[WARNING] 删除间隔小于 1 秒，被强制设为 1 秒以避免风控。"
        )
        args.interval = 1.0

    # ── 类型筛选 ──
    types = None
    if args.type:
        types = [args.type]

    # 时间筛选
    since = parse_datetime(args.since)
    until = parse_datetime(args.before)

    # ── 登录 ──
    login = WeiboLogin()

    if args.cookie:
        ok, msg = login.login_by_cookie(args.cookie)
    elif args.scan:
        ok, msg = login.login_by_scan()
    else:
        # 默认尝试从文件加载
        ok, msg = login.login_by_cookie()

    if not ok:
        print(f"[ERROR] 登录失败: {msg}")
        print("提示: 使用 --scan 扫码登录，或 --cookie 传入 cookie 字符串。")
        sys.exit(1)

    print(f"[{now_str()}] {msg}")

    # ── 确定 UID ──
    uid = args.uid or login.uid

    # ── 拉取微博 ──
    fetcher = WeiboFetcher(login.session, uid)
    max_pages = args.max_pages or (0 if args.all else 50)

    print(f"[{now_str()}] 正在拉取微博列表...")
    mblogs = fetcher.fetch_all(
        since=since,
        until=until,
        types=types,
        page_count=max_pages,
    )

    total = len(mblogs)
    print(f"[{now_str()}] 共获取 {total} 条符合条件的微博。")

    if total == 0:
        print("没有需要处理的微博。")
        return

    # ── Dry-run 预览 ──
    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY-RUN 预览模式 - 以下微博将被删除：")
        print("=" * 60)
        for i, mblog in enumerate(mblogs, 1):
            print(summarize_weibo(mblog, i))
        print("=" * 60)
        print(f"\n共 {total} 条微博待删除。")
        print("确认删除请运行: 加上 --confirm 参数并去掉 --dry-run")
        return

    # ── 确认删除 ──
    if args.confirm:
        print("\n" + "=" * 60)
        if total > 50:
            print(f"⚠  即将删除 {total} 条微博，此操作不可逆！")
            confirm = input("确认删除？输入 yes 继续: ").strip()
            if confirm.lower() != "yes":
                print("已取消。")
                return
        print("=" * 60)

        deleter = WeiboDeleter(login.session, uid)
        success, fail = deleter.batch_delete(
            mblogs,
            interval=args.interval,
            cooldown_on_err=args.cooldown,
        )

        # 最终摘要
        print(f"\n{'=' * 60}")
        print("删除任务完成。")
        print(f"  成功: {success} 条")
        print(f"  失败: {fail} 条")
        print(f"  总计: {total} 条")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
