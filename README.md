# 인터넷용 AI 사진 PASS/FAIL

## 가장 쉬운 배포 방법: Render

1. GitHub에 이 폴더의 파일을 올립니다.
2. Render에서 GitHub 저장소를 연결해 Web Service를 만듭니다.
3. Build Command:
   pip install -r requirements.txt
4. Start Command:
   gunicorn app:app
5. Environment Variables:
   ADMIN_PASSWORD=원하는관리자비밀번호
   SECRET_KEY=긴랜덤문자열
6. 배포 후 생성된 https://....onrender.com/admin 으로 접속합니다.
7. 관리자 로그인 → 기준 사진 업로드 → PASS 기준 설정.
8. https://....onrender.com/participant 가 참가자 페이지입니다.
9. 참가자 페이지 주소를 QR 코드로 만들어 공유하면 됩니다.

첫 AI 검사 때 DINOv2 모델을 내려받기 때문에 첫 요청은 느릴 수 있습니다.

## AI 방식
facebook/dinov2-small의 CLS 이미지 임베딩을 사용하고 코사인 유사도로 점수를 계산합니다.
기준 사진의 임베딩은 관리자 저장 시 미리 계산해 저장합니다.

## 중요
이 예제는 서비스 구조를 보여주는 완성형 프로토타입입니다.
대규모 트래픽에서는 PostgreSQL, 객체 스토리지, Redis/작업 큐, GPU 또는 별도 AI 서버를 추가하는 것이 좋습니다.
