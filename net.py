"""网络层：Bearer 鉴权请求、接口测速、OpenAI 兼容 chat 调用与用量解析。"""
import json, time, urllib.error, urllib.request

TIMEOUT = 25
UA = {"User-Agent": "api-panel-tool/1.0"}


def request(url, method="GET", key_value=None, payload=None):
    """发起请求，返回 (status|None, latency_ms, body_text)。"""
    headers = dict(UA)
    if key_value:
        headers["Authorization"] = f"Bearer {key_value}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
        return r.status, int((time.perf_counter() - t0) * 1000), body
    except urllib.error.HTTPError as e:
        lat = int((time.perf_counter() - t0) * 1000)
        return e.code, lat, e.read().decode("utf-8", "replace")
    except Exception as e:  # network / timeout
        lat = int((time.perf_counter() - t0) * 1000)
        return None, lat, str(e)


def chat(url, key_value, model, prompt, max_tokens=None, temperature=0.7):
    """调用 OpenAI 兼容 /chat/completions，返回 (status, latency, usage_dict, reply_text, raw_error)。"""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    status, lat, text = request(url, "POST", key_value, body)
    if status is None or status >= 400:
        return status, lat, None, None, text[:400]
    try:
        js = json.loads(text)
    except json.JSONDecodeError:
        return status, lat, None, None, "non-JSON response"
    usage = js.get("usage") or {}
    reply = ""
    try:
        reply = js["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        pass
    return status, lat, usage, reply, None
