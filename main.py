"""API 密钥调度面板 - 交互式菜单版
运行: python main.py   （无需任何命令行参数）
"""
import getpass
import json
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import net
import storage

H = 6
T = 4


def now(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _mask(v):
    return v[:H] + "*" * 10 + v[-T:] if len(v) > H + T else "*" * 12


def _fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _input(prompt, default=None, secret=False):
    if secret:
        raw = getpass.getpass(prompt)
    else:
        raw = input(prompt).strip()
    if not raw and default is not None:
        return default
    return raw


def _pick_key():
    rows = storage.list_keys()
    if not rows:
        print("! 尚未录入任何密钥，请先选 [1] 录入")
        return None
    print("选择密钥:")
    for i, r in enumerate(rows, 1):
        tag = " (生效)" if r["active"] else ""
        print(f"  [{i}] {r['name']}  {_mask(r['value'])}{tag}")
    sel = _input("编号(回车=当前生效): ", "0")
    try:
        idx = int(sel)
    except ValueError:
        return None
    if idx == 0:
        row = storage.get_active_key()
        if row is None:
            print("! 无生效密钥，请直接输入编号")
            return None
        return row
    if 1 <= idx <= len(rows):
        return rows[idx - 1]
    print("! 编号无效")
    return None


def menu_add():
    name = _input("密钥名称: ")
    if not name:
        print("! 名称不能为空"); return
    if storage.find_key(name):
        print(f"! 已存在同名密钥: {name}"); return
    value = _input("粘贴 API 密钥(隐藏输入): ", secret=True)
    if not value:
        print("! 密钥不能为空"); return
    storage.add_key(name, value)
    print(f"[ok] 已录入密钥: {name}")


def menu_ls():
    rows = storage.list_keys()
    if not rows:
        print("(暂无密钥)")
        return
    print(f"{'名称':<16}{'密钥(掩码)':<32}{'生效':<6}录入时间")
    for r in rows:
        print(f"{r['name']:<16}{_mask(r['value']):<32}{'*' if r['active'] else '':<6}{_fmt_ts(r['created_at'])}")


def menu_active():
    rows = storage.list_keys()
    if not rows:
        print("(暂无密钥)"); return
    print("选择要设为生效的密钥:")
    for i, r in enumerate(rows, 1):
        print(f"  [{i}] {r['name']}")
    sel = _input("编号: ")
    try:
        idx = int(sel)
        if not (1 <= idx <= len(rows)):
            raise ValueError
    except ValueError:
        print("! 编号无效"); return
    storage.set_active(rows[idx - 1]["name"])
    print(f"[ok] 生效密钥 -> {rows[idx - 1]['name']}")


def menu_rm():
    rows = storage.list_keys()
    if not rows:
        print("(暂无密钥)"); return
    print("选择要删除的密钥:")
    for i, r in enumerate(rows, 1):
        print(f"  [{i}] {r['name']}  {_mask(r['value'])}")
    sel = _input("编号: ")
    try:
        idx = int(sel)
        if not (1 <= idx <= len(rows)):
            raise ValueError
    except ValueError:
        print("! 编号无效"); return
    name = rows[idx - 1]["name"]
    cfm = _input(f"确认删除密钥 '{name}'? (y/N): ", "n").lower()
    if cfm != "y":
        print("已取消"); return
    storage.delete_key(name)
    print(f"[ok] 已删除密钥: {name}")


def menu_probe():
    row = _pick_key()
    if row is None:
        return
    url = _input("接口 URL: ")
    if not url:
        print("! URL 不能为空"); return
    method = _input("方法 (GET/POST, 默认 GET): ", "GET").upper()
    data = None
    if method == "POST":
        raw = _input("POST body(JSON, 可留空): ", "")
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print("! JSON 解析失败"); return
    print(f"测速中: {method} {url} (key={row['name']}) ...")
    status, lat, body = net.request(url, method, row["value"], data)
    if status is None:
        print(f"[err] 网络/超时错误: {body}")
    else:
        print(f"[{status}] {lat} ms")
        print(body[:300])


def menu_chat():
    row = _pick_key()
    if row is None:
        return
    url = _input("接口 URL (默认 DeepSeek): ", "https://api.deepseek.com/chat/completions")
    model = _input("模型 (默认 deepseek-chat): ", "deepseek-chat")
    if not model:
        print("! 模型不能为空"); return
    prompt = _input("提示词(prompt): ")
    if not prompt:
        print("! prompt 不能为空"); return
    mt = _input("max_tokens(可留空): ", "")
    max_tokens = int(mt) if mt.isdigit() else None
    print("请求中 ...")
    status, lat, usage, reply, err = net.chat(url, row["value"], model, prompt, max_tokens)
    if status is None or status >= 400:
        print(f"[err] HTTP {status} in {lat} ms: {err}")
        return
    tokens = int((usage or {}).get("total_tokens") or 0)
    storage.record_usage(row["id"], tokens, lat, url, model)
    print(f"[ok] HTTP {status} in {lat} ms | model={usage.get('model', model)}")
    print(f"     prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} total={tokens}")
    if reply:
        print("     reply:", reply[:200].replace("\n", " "))


def menu_usage():
    rows, tot = storage.usage_report()
    if not tot["reqs"]:
        print("(暂无用量记录，先执行 [6] 调用接口)")
        return
    print(f"{'密钥':<16}{'请求数':<8}{'总tokens':<12}平均延迟(ms)")
    for r in rows:
        print(f"{r['key_name']:<16}{r['reqs']:<8}{r['tokens']:<12}{r['avg_lat']:.0f}")
    print("-" * 48)
    print(f"合计: 请求 {tot['reqs']} 次, tokens {tot['tokens']}")


MENU = """\n===== API 密钥调度面板 =====
  [1] 录入密钥          [5] 接口测速
  [2] 列出密钥          [6] 调用接口(记录token用量)
  [3] 设置生效密钥      [7] token用量统计
  [4] 删除密钥          [0] 退出
================================"""


def main():
    storage.init_db()
    actions = {
        "1": menu_add,
        "2": menu_ls,
        "3": menu_active,
        "4": menu_rm,
        "5": menu_probe,
        "6": menu_chat,
        "7": menu_usage,
    }
    while True:
        print(MENU)
        choice = _input("请选择: ")
        if choice == "0":
            print("再见")
            break
        fn = actions.get(choice)
        if fn is None:
            print("! 无效选项，请输入 0-7")
            continue
        try:
            fn()
        except KeyboardInterrupt:
            print("\n已取消")
        except Exception as e:
            print(f"[err] {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n再见")
