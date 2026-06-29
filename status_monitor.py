#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
서울특별시 메신저 - 접속 상태(온라인/자리비움/오프라인) 감지·기록 프로그램

특정 사람의 상태 아이콘 색을 주기적으로 확인해서
  - 상태가 바뀌면 그 시각을 일별 txt 로그에 기록 (새벽 3시 기준으로 날짜 구분)
  - 현재 상태와 변경 로그를 docs/data.json 으로 만들어 HTML 에서 볼 수 있게 함
  - (선택) GitHub 에 자동 업로드하여 웹에서 확인 가능

실행
  messenger_status.exe            더블클릭 (좌표 없으면 등록, 있으면 실행)
  messenger_status.exe calibrate  좌표 등록
  messenger_status.exe run        실행
"""

import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta

import mss
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
if not os.path.isdir(BASE_DIR):
    BASE_DIR = os.getcwd()
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# 상태 코드 -> 한글 이름
KOR = {"ON": "온라인", "AWAY": "자리비움", "OFF": "오프라인"}

DEFAULT_CONFIG = {
    "poll_interval_sec": 5,     # 몇 초마다 확인할지
    "sample_radius": 3,         # 아이콘 중심에서 평균낼 반경(px)
    "rollover_hour": 3,         # 하루 마감 시각(새벽 3시)
    "log_dir": "logs",          # 일별 txt 로그 폴더
    "docs_dir": "docs",         # HTML / data.json 폴더
    "max_web_events": 300,      # 웹에 보여줄 최근 이벤트 개수
    "target": {"name": "", "x": 0, "y": 0},
    # --- GitHub 자동 업로드(선택). 비워두면 로컬 파일만 만듦 ---
    "github": {
        "enabled": False,
        "repo": "",             # 예: "kwaho-stack/mess"
        "branch": "claude/messenger-status-detection-n0evlx",
        "token": ""             # Personal Access Token (contents 쓰기 권한)
    },
}


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# 진단용: 터미널 대신 monitor.log 파일에 기록
LOG_FILE = os.path.join(BASE_DIR, "monitor.log")


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 색 -> 상태 판별
# ---------------------------------------------------------------------------
def avg_color(sct, x, y, radius):
    size = radius * 2 + 1
    region = {"left": x - radius, "top": y - radius, "width": size, "height": size}
    shot = sct.grab(region)
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    # 1x1 로 줄이면 영역 평균색이 된다 (deprecated getdata 회피)
    return img.resize((1, 1), Image.BOX).getpixel((0, 0))


def classify(rgb):
    """평균 RGB -> 'ON' / 'AWAY' / 'OFF' / 'UNKNOWN'"""
    r, g, b = rgb
    chroma = max(rgb) - min(rgb)
    if chroma < 30:                                   # 무채색 = 회색 = 오프라인
        return "OFF"
    if r >= g and r >= b and (r - max(g, b)) > 25:    # 빨강 = 온라인
        return "ON"
    if b >= r and b >= g and (b - min(r, g)) > 25:    # 파랑(시계) = 자리비움
        return "AWAY"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# 날짜(새벽 3시 마감 기준)
# ---------------------------------------------------------------------------
def logical_date(dt, rollover_hour):
    """새벽 3시 이전이면 전날로 친다."""
    d = dt.date()
    if dt.hour < rollover_hour:
        d = d - timedelta(days=1)
    return d


def day_log_path(cfg, dt):
    d = logical_date(dt, cfg["rollover_hour"])
    log_dir = os.path.join(BASE_DIR, cfg["log_dir"])
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"{d.isoformat()}.txt"), d


# ---------------------------------------------------------------------------
# 로그 / 웹 데이터 기록
# ---------------------------------------------------------------------------
def append_txt(path, dt, state_code):
    line = f"{dt.strftime('%Y-%m-%d %H:%M:%S')}  {KOR[state_code]}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def read_today_state(cfg, now):
    """오늘(논리적 날짜) txt 가 있으면 마지막 상태/시각/이벤트들을 복원."""
    path, _ = day_log_path(cfg, now)
    events = []
    last_state, since = None, None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                ts, _, kor = raw.partition("  ")
                events.append({"time": ts, "state": kor})
        if events:
            last = events[-1]
            since = last["time"]
            # 한글 -> 코드 역변환
            for code, name in KOR.items():
                if name == last["state"]:
                    last_state = code
    return last_state, since, events


def write_web_data(cfg, current_code, since, events):
    docs = os.path.join(BASE_DIR, cfg["docs_dir"])
    os.makedirs(docs, exist_ok=True)
    data = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current": KOR.get(current_code, "알수없음"),
        "since": since or "",
        "events": events[-cfg["max_web_events"]:][::-1],  # 최신순
    }
    path = os.path.join(docs, "data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path, data


# ---------------------------------------------------------------------------
# GitHub 업로드(선택)
# ---------------------------------------------------------------------------
def github_put(cfg, repo_path, content_bytes, message):
    gh = cfg.get("github", {})
    if not gh.get("enabled"):
        return
    if not gh.get("token") or not gh.get("repo"):
        log("업로드 안함: config.json 의 github token/repo 가 비어 있음")
        return
    api = f"https://api.github.com/repos/{gh['repo']}/contents/{repo_path}"
    headers = {
        "Authorization": f"Bearer {gh['token'].strip()}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "messenger-status-monitor",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # 기존 파일 sha 조회
    sha = None
    try:
        req = urllib.request.Request(api + f"?ref={gh['branch']}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            sha = json.loads(r.read()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pass  # 파일이 아직 없음 → 새로 생성
        else:
            log(f"조회 실패 {e.code} {repo_path}: {e.read().decode(errors='ignore')[:200]}")
    except Exception as e:
        log(f"연결 실패 {repo_path}: {e}")
        return
    body = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "branch": gh["branch"],
    }
    if sha:
        body["sha"] = sha
    try:
        req = urllib.request.Request(
            api, data=json.dumps(body).encode(), headers=headers, method="PUT")
        urllib.request.urlopen(req, timeout=15).read()
        log(f"업로드 OK -> {gh['repo']}@{gh['branch']}:{repo_path}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        log(f"업로드 실패 {e.code} {repo_path}: {detail}")
    except Exception as e:
        log(f"업로드 실패 {repo_path}: {e}")


def publish(cfg, data, day):
    """data.json 과 그 날 txt 를 GitHub 로 올린다."""
    if not cfg.get("github", {}).get("enabled"):
        return
    docs = cfg["docs_dir"]
    github_put(cfg, f"{docs}/data.json",
               json.dumps(data, ensure_ascii=False, indent=2).encode(),
               f"update status: {data['current']} ({data['updated']})")
    # 그 날 txt 도 업로드
    txt_path = os.path.join(BASE_DIR, cfg["log_dir"], f"{day.isoformat()}.txt")
    if os.path.exists(txt_path):
        with open(txt_path, "rb") as f:
            github_put(cfg, f"{cfg['log_dir']}/{day.isoformat()}.txt",
                       f.read(), f"log {day.isoformat()}")


# ---------------------------------------------------------------------------
# calibrate
# ---------------------------------------------------------------------------
def cmd_calibrate():
    import pyautogui

    cfg = load_config()
    input("아이콘 위에 마우스를 올리고 Enter > ")
    x, y = pyautogui.position()
    with mss.MSS() as sct:
        rgb = avg_color(sct, x, y, cfg["sample_radius"])
    state = classify(rgb)

    cfg["target"] = {"name": "", "x": x, "y": y}
    save_config(cfg)
    print(f"등록됨 ({x}, {y}) · 현재 {KOR.get(state, '?')}")
    if state == "UNKNOWN":
        print("색이 애매합니다. 아이콘 정중앙으로 다시 등록하세요.")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
def cmd_run():
    cfg = load_config()
    tgt = cfg.get("target", {})
    if not tgt.get("x"):
        cmd_calibrate()
        cfg = load_config()
        tgt = cfg.get("target", {})

    x, y = tgt["x"], tgt["y"]
    interval = cfg["poll_interval_sec"]
    radius = cfg["sample_radius"]

    now = datetime.now()
    last_state, since, events = read_today_state(cfg, now)
    _, cur_day = day_log_path(cfg, now)

    print("실행 중입니다. 이 창은 그대로 두세요. (종료: 이 창 닫기)")

    gh = cfg.get("github", {})
    log(f"시작: github_enabled={gh.get('enabled')} repo={gh.get('repo')} branch={gh.get('branch')}")

    # 시작 시 한 번 웹데이터 만들고 즉시 업로드 → 바로 확인 가능
    _, data = write_web_data(cfg, last_state or "OFF", since, events)
    publish(cfg, data, cur_day)

    try:
        with mss.MSS() as sct:
            while True:
                now = datetime.now()
                _, day = day_log_path(cfg, now)

                # 날짜(3시) 넘어가면 새 파일로 전환 + 이전 날 마무리 업로드
                if day != cur_day:
                    publish(cfg, data, cur_day)
                    last_state, since, events = None, None, []
                    cur_day = day

                rgb = avg_color(sct, x, y, radius)
                state = classify(rgb)
                if state == "UNKNOWN":
                    time.sleep(interval)
                    continue

                if state != last_state:
                    ts = now.strftime("%Y-%m-%d %H:%M:%S")
                    path, _ = day_log_path(cfg, now)
                    append_txt(path, now, state)
                    events.append({"time": ts, "state": KOR[state]})
                    since = ts
                    log(f"상태변경 {KOR[state]}")
                    last_state = state
                    _, data = write_web_data(cfg, state, since, events)
                    publish(cfg, data, day)
                else:
                    # 상태 그대로면 웹의 갱신시각만 로컬에서 갱신
                    _, data = write_web_data(cfg, state, since, events)

                time.sleep(interval)
    except KeyboardInterrupt:
        print("\n종료")


# ---------------------------------------------------------------------------
def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if cmd == "calibrate":
        cmd_calibrate()
    elif cmd == "run":
        cmd_run()
    elif cmd in ("", "auto"):
        # 더블클릭 시: 등록 안됐으면 등록, 됐으면 감시
        cfg = load_config()
        if not cfg.get("target", {}).get("x"):
            cmd_calibrate()
        cmd_run()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
