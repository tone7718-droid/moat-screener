# 해자 기업 스크리너 (Moat Screener)

S&P500 + 나스닥100 기업을 수익성 지속성(경제적 해자) 기준으로 점수화하고,
상위 50개의 현재 가격 밸류에이션을 매일 자동 갱신하는 정적 웹사이트.

## 구조

| 파일 | 역할 |
|---|---|
| `index.html` | 웹사이트 (정적, web_data.json을 읽어 표시) |
| `web_data.json` | 표시 데이터 (자동 갱신됨) |
| `top50_base.json` | 해자 상위 50 목록 (분기마다 수동 갱신 권장) |
| `moats_data.json` | 기업별 정성 분석 (Claude 작성) |
| `update_data.py` | 밸류에이션 재계산 스크립트 |
| `.github/workflows/update.yml` | 평일 22:10 UTC 자동 실행 (한국 오전 7:10) |

## 자동화 흐름

GitHub Actions(평일 1회) → `update_data.py` 실행 → `web_data.json` 커밋
→ Vercel Git 연동이 자동 재배포

수동 실행: GitHub 저장소 → Actions 탭 → "매일 밸류에이션 갱신" → Run workflow

## 점수 기준

- **해자점수**: ROIC 수준·지속성 50점 + 매출총이익률 수준·안정성 30점 + FCF/희석/성장 20점
- **밸류점수**: FCF수익률 40점(8%↑ 만점) + EV/EBIT 30점(10배↓ 만점) + PEG 30점(1.0↓ 만점)

## 면책

투자 권유가 아닙니다. 데이터는 Yahoo Finance 무료 API(최대 4개년) 기반이며
오류가 있을 수 있습니다. 모든 투자 판단과 책임은 사용자 본인에게 있습니다.
