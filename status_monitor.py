#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
서울특별시 메신저 - 접속 상태(ON/OFF) 감지 및 기록 프로그램

특정 사람의 상태 아이콘 색을 주기적으로 확인해서,
ON(빨강) -> OFF(회색) 으로 바뀌는 순간의 시간을 CSV 로 기록합니다.

사용 순서
  1) pip install -r requirements.txt
  2) 감시할 사람 등록(좌표 찍기):   python status_monitor.py calibrate
  3) 감시 시작:                    python status_monitor.py run

메신저는 외부 API 가 없으므로 화면(아이콘 색)을 읽어서 판별합니다.
따라서 감시 중에는 메신저 목록 창이 항상 같은 위치에 보여야 합니다.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime

import mss
from PIL import Image

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "poll_interval_sec": 5,      # 몇 초마다 확인할지
    "sample_radius": 3,          # 아이콘 중심에서 몇 px 범위를 평균낼지
    "log_file": "status_log.csv",
    "targets": [],               # [{"name": "심재호", "x": 27, "y": 423}, ...]
}


# ---------------------------------------------------------------------------
# 설정 입출력
# ---------------------------------------------------------------------------
def load_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG, targets=[])
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # 누락된 키 보정
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 색 -> 상태 판별
# ---------------------------------------------------------------------------
def _avg_color(sct, x, y, radius):
    """(x, y) 주변 사각형 영역의 평균 RGB 를 구한다."""
    size = radius * 2 + 1
    region = {"left": x - radius, "top": y - radius, "width": size, "height": size}
    shot = sct.grab(region)
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    pixels = list(img.getdata())
    n = len(pixels)
    r = sum(p[0] for p in pixels) / n
    g = sum(p[1] for p in pixels) / n
    b = sum(p[2] for p in pixels) / n
    return (r, g, b)


def classify(rgb):
    """
    평균 RGB 를 보고 상태를 분류한다.
      ON    : 빨강 계열  -> "ON"
      AWAY  : 파랑 계열(시계, 자리비움) -> "AWAY"
      OFF   : 회색/무채색 -> "OFF"
    """
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    chroma = mx - mn  # 채도(색의 선명함). 낮으면 회색.

    # 채도가 낮으면 무채색 = OFF(회색)
    if chroma < 30:
        return "OFF"

    # 빨강이 가장 강하고 초록/파랑보다 충분히 높으면 ON
    if r >= g and r >= b and (r - max(g, b)) > 25:
        return "ON"

    # 파랑이 가장 강하면 자리비움(시계)
    if b >= r and b >= g and (b - min(r, g)) > 25:
        return "AWAY"

    # 그 외(애매) 는 일단 OFF 로 취급하지 않고 직전 상태 유지를 위해 UNKNOWN
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# calibrate : 감시할 사람 좌표 등록
# ---------------------------------------------------------------------------
def cmd_calibrate():
    import pyautogui

    cfg = load_config()
    print("=" * 60)
    print(" 좌표 등록 모드")
    print("=" * 60)
    print("메신저 목록에서 감시할 사람의 '상태 아이콘(ON/OFF 동그라미)' 위에")
    print("마우스를 올려둔 채로, 이 창에서 Enter 를 누르세요.")
    print("끝내려면 이름을 비우고 Enter.")
    print("-" * 60)

    while True:
        name = input("\n감시할 사람 이름 (그만하려면 빈칸): ").strip()
        if not name:
            break
        input(f"  -> '{name}' 의 상태 아이콘 위에 마우스를 올리고 Enter...")
        x, y = pyautogui.position()

        # 현재 색/상태도 같이 보여줌
        with mss.mss() as sct:
            rgb = _avg_color(sct, x, y, cfg["sample_radius"])
        state = classify(rgb)
        print(f"  좌표=({x}, {y})  색={tuple(int(v) for v in rgb)}  판별={state}")

        if state == "UNKNOWN":
            print("  ⚠ 색 판별이 애매합니다. 아이콘 정중앙을 다시 가리키세요.")

        # 기존 동일 이름 제거 후 추가
        cfg["targets"] = [t for t in cfg["targets"] if t["name"] != name]
        cfg["targets"].append({"name": name, "x": x, "y": y})
        save_config(cfg)
        print(f"  ✅ 등록 완료. 현재 등록 인원: {len(cfg['targets'])}명")

    print("\n저장됨:", CONFIG_PATH)
    if cfg["targets"]:
        print("등록된 사람:", ", ".join(t["name"] for t in cfg["targets"]))


# ---------------------------------------------------------------------------
# run : 감시 시작
# ---------------------------------------------------------------------------
def log_event(log_path, name, event, rgb):
    new_file = not os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["시각", "이름", "이벤트", "RGB"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            name,
            event,
            ",".join(str(int(v)) for v in rgb),
        ])


def cmd_run():
    cfg = load_config()
    if not cfg["targets"]:
        print("등록된 사람이 없습니다. 먼저 'python status_monitor.py calibrate' 를 실행하세요.")
        return

    log_path = os.path.join(os.path.dirname(CONFIG_PATH), cfg["log_file"])
    interval = cfg["poll_interval_sec"]
    radius = cfg["sample_radius"]

    print("=" * 60)
    print(" 감시 시작 (Ctrl+C 로 종료)")
    print("=" * 60)
    print("대상:", ", ".join(t["name"] for t in cfg["targets"]))
    print(f"확인 주기: {interval}초   기록 파일: {log_path}")
    print("-" * 60)

    # 직전 상태 기억
    last_state = {t["name"]: None for t in cfg["targets"]}

    try:
        with mss.mss() as sct:
            while True:
                now = datetime.now().strftime("%H:%M:%S")
                for t in cfg["targets"]:
                    name, x, y = t["name"], t["x"], t["y"]
                    rgb = _avg_color(sct, x, y, radius)
                    state = classify(rgb)

                    # UNKNOWN 은 노이즈로 보고 직전 상태 유지
                    if state == "UNKNOWN":
                        continue

                    prev = last_state[name]
                    if prev is not None and prev != state:
                        print(f"[{now}] {name}: {prev} -> {state}")
                        # 핵심: ON -> OFF 전환 기록
                        if prev == "ON" and state == "OFF":
                            log_event(log_path, name, "ON->OFF (오프라인 전환)", rgb)
                            print(f"        💾 기록됨: {name} 오프라인 전환")
                        else:
                            # 다른 전환도 참고용으로 기록 (필요 없으면 이 else 블록 삭제)
                            log_event(log_path, name, f"{prev}->{state}", rgb)

                    last_state[name] = state

                time.sleep(interval)
    except KeyboardInterrupt:
        print("\n종료했습니다.")


# ---------------------------------------------------------------------------
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "calibrate":
        cmd_calibrate()
    elif cmd == "run":
        cmd_run()
    else:
        print(__doc__)
        print("사용법:")
        print("  python status_monitor.py calibrate   # 감시할 사람 좌표 등록")
        print("  python status_monitor.py run         # 감시 시작")


if __name__ == "__main__":
    main()
