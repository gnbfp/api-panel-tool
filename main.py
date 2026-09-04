"""API 密钥调度面板 - 命令行入口
用法示例:
  python main.py add mykey                 # 交互粘贴密钥(不显示、不进shell历史)
  python main.py ls
  python main.py active mykey
  python main.py rm mykey
  python main.py probe https://httpbin.org/get --key mykey
  python main.py chat --key mykey --model gpt-4o-mini --prompt "hi"
  python main.py usage
"""
import argparse, json, sys
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


def _key_row(args_key):
    row = storage.find_key(args_key) if args_key else storage.get_active_key()
    if row is None:
        sys.exit("key not found / no active key: use `active <name>` or --key <name>")
    return row


def cmd_add(a):
    value = a.key or input("Paste API key (echoed) or use interactive mode: ").strip()
    if not value:
        sys.exit("empty key")
    try:
        storage.add_key(a.name, value)
    except storage.DupError:
        sys.exit(f"name already exists: {a.name}")
    print(f"[ok] key saved: {a.name}")


def cmd_ls(_a):
    rows = storage.list_keys()
    if not rows:
        print("no keys yet -> python main.py add <name>")
        return
    print(f"{'name':<16}{'key(masked)':<32}{'active':<7}created")
    for r in rows:
        print(f"{r['name']:<16}{_mask(r['value']):<32}{'*' if r['active'] else '':<7}{now(r['created_at'])}")


def cmd_active(a):
    if a.name:
        storage.set_active(a.name)
        print(f"[ok] active key -> {a.name}")
    else:
        row = storage.get_active_key()
        print(f"active: {row['name'] if row else '(none)'}")


def cmd_rm(a):
    storage.delete_key(a.name)
    print(f"[ok] deleted key: {a.name}")


def cmd_probe(a):
    row = _key_row(a.key)
    payload = json.loads(a.data) if a.data else None
    status, lat, body = net.request(a.url, a.method, row["value"], payload)
    if status is None:
        print(f"[err] network/timeout: {body}")
    else:
        print(f"[{status}] {lat} ms  url={a.url}")
        print(body[:300])


def cmd_chat(a):
    row = _key_row(a.key)
    status, lat, usage, reply, err = net.chat(
        a.url, row["value"], a.model, a.prompt, a.max_tokens
    )
    if status is None or status >= 400:
        print(f"[err] HTTP {status} in {lat} ms: {err}")
        return
    tokens = int((usage or {}).get("total_tokens") or 0)
    storage.record_usage(row["id"], tokens, lat, a.url, a.model)
    print(f"[ok] HTTP {status} in {lat} ms | model={usage.get('model', a.model)}")
    print(f"     usage: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} total={tokens}")
    if reply:
        print("     reply:", reply[:200].replace("\n", " "))


def cmd_usage(a):
    rows, tot = storage.usage_report(a.key, a.days)
    if not tot["reqs"]:
        print("no usage records yet -> run `chat` first")
        return
    print(f"{'key':<16}{'reqs':<7}{'total_tokens':<14}avg_lat(ms)")
    for r in rows:
        print(f"{r['key_name']:<16}{r['reqs']:<7}{r['tokens']:<14}{r['avg_lat']:.0f}")
    print("-" * 50)
    print(f"TOTAL: requests={tot['reqs']}  tokens={tot['tokens']}")


def main():
    storage.init_db()
    p = argparse.ArgumentParser(prog="api-panel", description="API 密钥调度面板")
    s = p.add_subparsers(dest="cmd", required=True)

    pa = s.add_parser("add", help="录入密钥")
    pa.add_argument("name"); pa.add_argument("key", nargs="?")
    pa.set_defaults(fn=cmd_add)

    pl = s.add_parser("ls", help="列出密钥(掩码)")
    pl.set_defaults(fn=cmd_ls)

    pact = s.add_parser("active", help="查看/设置当前生效密钥")
    pact.add_argument("name", nargs="?")
    pact.set_defaults(fn=cmd_active)

    prm = s.add_parser("rm", help="删除密钥")
    prm.add_argument("name")
    prm.set_defaults(fn=cmd_rm)

    pp = s.add_parser("probe", help="接口测速")
    pp.add_argument("url"); pp.add_argument("--key"); pp.add_argument("--method", default="GET")
    pp.add_argument("--data", help='POST body JSON, e.g. {"q":"hi"}')
    pp.set_defaults(fn=cmd_probe)

    pc = s.add_parser("chat", help="调用 OpenAI 兼容接口并记录 token 用量")
    pc.add_argument("--url", default="https://api.openai.com/v1/chat/completions")
    pc.add_argument("--key"); pc.add_argument("--model", required=True); pc.add_argument("--prompt", required=True)
    pc.add_argument("--max-tokens", type=int)
    pc.set_defaults(fn=cmd_chat)

    pu = s.add_parser("usage", help="token 用量统计")
    pu.add_argument("--key"); pu.add_argument("--days", type=int)
    pu.set_defaults(fn=cmd_usage)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
