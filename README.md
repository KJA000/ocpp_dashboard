# OCPP 1.6 기반 EV 충전 시스템 대시보드

본 프로젝트는 **OCPP 1.6 (Open Charge Point Protocol)** 표준을 기반으로  
**충전기(SECC) – 서버(CSMS) – 사용자 인터페이스(Frontend)** 간의 통신 흐름을  
시뮬레이션하고 시각화하는 전기차 충전 관리 시스템입니다.

Frontend 대시보드를 통해 충전 상태를 확인할 수 있으며,  
Backend 서버(CSMS)와 가상 충전기(SECC)를 연동하여  
**인증 → 플러그 연결 → 충전 시작**의 전체 시나리오를 재현합니다.

---

## 📁 프로젝트 구조

OCPP_CS/
└─ ocpp_dashboard/
├─ Frontend/
│ └─ frontend/ # React 기반 프론트엔드
├─ manage.py # CSMS 서버 실행 파일
└─ ocpp_dashboard/ # Django 기반 CSMS 서버 코드

OCPP_CP/
└─ main.py # 충전기(SECC) 시뮬레이터

yaml
코드 복사

---

## ⚙️ 실행 환경

- **Frontend**: Node.js, React
- **Backend (CSMS)**: Python, Django
- **Charge Point (SECC)**: Python (GUI 기반 시뮬레이터)

---

## 🚀 실행 방법

### 1️⃣ Frontend 실행 (충전 대시보드)

```bash
cd OCPP_CS/ocpp_dashboard/Frontend/frontend
npm install
npm start
React 기반 충전 대시보드가 실행됩니다.

충전 상태 및 이벤트 흐름을 실시간으로 확인할 수 있습니다.

2️⃣ 서버(CSMS) 실행
bash
코드 복사
cd OCPP_CS/ocpp_dashboard
python manage.py runserver
OCPP 1.6 기반 Central System Management Server(CSMS)가 실행됩니다.

충전기(SECC)와 WebSocket 통신을 수행합니다.

3️⃣ 충전기(SECC) 실행
bash
코드 복사
cd OCPP_CP
python main.py
가상 충전기(SECC) GUI가 실행됩니다.

CSMS와 연결되어 충전 상태를 시뮬레이션합니다.

🔄 시나리오 실행 순서
충전기(SECC) GUI 실행 후 CSMS 연결

Python GUI에서 Id valid 상태 확인

Insert Plug 선택

충전 상태를 Charging 으로 변경

Frontend 대시보드에서 상태 변화 확인

위 과정을 통해 OCPP 1.6 기반의
인증 → 연결 → 충전 시작 흐름을 확인할 수 있습니다.

🎯 프로젝트 목적
OCPP 1.6 프로토콜의 실제 동작 흐름 이해

EV 충전 시스템의 상태 전이(State Transition) 구조 학습

충전기–서버–UI 간 연동 구조 설계 및 구현

졸업 프로젝트 수준의 실행 가능한 시뮬레이션 환경 구축
