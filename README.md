# 메신저 접속 상태 감지·기록 프로그램

"서울특별시 메신저"에서 **특정 사람의 상태(온라인 / 자리비움 / 오프라인) 변화**를
자동으로 감지해서

1. **일별 txt 로그**로 기록하고 (새벽 3시 기준으로 날짜 구분, 파일명 = 날짜, 이름 미표기)
2. **웹(HTML) 페이지**에서 현재 상태와 변경 로그를 볼 수 있게 합니다 (GitHub Pages).

메신저는 외부 API가 없으므로 화면의 상태 아이콘 색을 읽어 판별합니다.

| 아이콘 | 색 | 상태 |
|--------|------|------|
| 🔴 | 빨강 | 온라인 |
| 🔵 | 파랑(시계) | 자리비움 |
| ⚫ | 회색 | 오프라인 |

---

## 1. EXE 받기 (PowerShell 필요 없음)

PC에서 명령어를 칠 필요 없이, GitHub가 자동으로 exe를 만들어 줍니다.

1. GitHub 저장소 → **Actions** 탭 → **Build Windows EXE** → **Run workflow** 클릭
   (코드를 푸시하면 자동으로도 빌드됩니다)
2. 빌드가 끝나면 해당 실행 결과 페이지 하단 **Artifacts → `messenger_status-exe`** 다운로드
3. 압축을 풀면 `messenger_status.exe` 가 나옵니다.

> 직접 빌드하려면(선택): `pip install -r requirements.txt pyinstaller` 후
> `pyinstaller --onefile --name messenger_status status_monitor.py`

---

## 2. 사용법

`messenger_status.exe` 를 **그냥 더블클릭**하면:
- 처음이면 → 좌표 등록 화면이 뜸
- 이미 등록돼 있으면 → 감시 시작

명령으로 구분해서 쓸 수도 있습니다(명령 프롬프트에서):

```
messenger_status.exe calibrate   # 감시할 사람 아이콘 좌표 등록
messenger_status.exe run         # 감시 시작 (Ctrl+C 종료)
```

**좌표 등록**: 메신저 목록을 늘 같은 위치에 띄워 둔 상태에서, 감시할 사람의
상태 아이콘(동그라미) 위에 마우스를 올리고 Enter를 누르면 됩니다.

> 감시 중에는 메신저 창이 가려지거나 위치/크기가 바뀌면 안 됩니다.
> 바뀌면 좌표를 다시 등록하세요.

---

## 3. txt 로그

`logs/` 폴더에 **하루에 한 파일**씩 쌓입니다.

- 파일명: `2026-06-29.txt` 처럼 날짜
- **새벽 3시 기준**으로 날짜가 바뀝니다 (예: 6/30 새벽 2시 59분 기록은 `2026-06-29.txt`,
  3시 00분부터는 `2026-06-30.txt`)
- 대상자 이름은 적지 않습니다

내용 예시:
```
2026-06-29 09:03:21  온라인
2026-06-29 12:10:05  자리비움
2026-06-29 18:42:50  오프라인
```

---

## 4. 웹(HTML)에서 확인 — GitHub Pages

### (1) Pages 켜기 (최초 1회)
저장소 → **Settings → Pages → Build and deployment**
→ Source: *Deploy from a branch*
→ Branch: `claude/messenger-status-detection-n0evlx`, 폴더: `/docs` → Save

잠시 후 `https://<사용자>.github.io/mess/` 주소로 페이지가 열립니다.
(현재 상태 + 변경 로그가 표시되고 20초마다 자동 새로고침)

### (2) 프로그램이 자동 업로드하도록 설정
`config.json` 의 `github` 부분을 채웁니다 (이 파일은 토큰이 들어있어 git에 올라가지 않습니다):

```json
"github": {
  "enabled": true,
  "repo": "kwaho-stack/mess",
  "branch": "claude/messenger-status-detection-n0evlx",
  "token": "ghp_..."
}
```

- 토큰: GitHub → Settings → Developer settings → **Personal access tokens**
  → 이 저장소에 **Contents: Read and write** 권한
- `enabled: true` 면 상태가 바뀔 때마다 `docs/data.json` 과 그날 txt 로그를
  GitHub에 자동 업로드 → 웹 페이지가 갱신됩니다.
- `enabled: false`(기본)면 로컬 파일(`logs/`, `docs/data.json`)만 만듭니다.

---

## 파일 구성

| 파일 | 설명 |
|------|------|
| `status_monitor.py` | 본체 (감지·기록·업로드) |
| `requirements.txt` | 필요한 라이브러리 |
| `docs/index.html` | 웹 페이지 (GitHub Pages) |
| `docs/data.json` | 현재 상태·로그 데이터(프로그램이 갱신) |
| `.github/workflows/build-exe.yml` | exe 자동 빌드 |
| `config.json` | 설정/좌표/토큰 (자동 생성, git 제외) |
| `logs/날짜.txt` | 일별 로그 (자동 생성) |

## 한계
- 메신저 창 위치/크기/테마가 바뀌면 좌표 재등록 필요
- PC가 잠기거나 절전이면 감지가 멈춤
- 색만 보므로 목록을 스크롤해 대상이 안 보이면 잘못 읽을 수 있음
