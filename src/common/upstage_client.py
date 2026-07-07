"""Upstage API 공통 클라이언트.

단위구현계획서.md 제5장 [T-002] 8항 구현 내용을 따른다.
Solar Pro 모델의 chat 호출을 위한 기본 클라이언트 인터페이스를 제공한다.
(Document Parse 등 다른 Upstage API는 후속 Task에서 확장한다.)
"""
import os

from langchain_upstage import ChatUpstage


class UpstageClient:
    """Upstage API 호출을 담당하는 공통 클라이언트.

    API 키는 환경변수 UPSTAGE_API_KEY에서 로딩한다 (.env 파일 경유).
    """

    def __init__(self) -> None:
        api_key = os.getenv("UPSTAGE_API_KEY")
        if not api_key:
            raise ValueError(
                "UPSTAGE_API_KEY 환경변수가 설정되어 있지 않습니다. "
                ".env 파일에 UPSTAGE_API_KEY=<키> 를 추가하세요."
            )
        self.api_key = api_key
        self._chat_model = ChatUpstage(api_key=api_key, model="solar-pro")

    def chat(self, message: str) -> str:
        """Solar Pro 모델에 텍스트 메시지를 보내고 응답 텍스트를 반환한다."""
        response = self._chat_model.invoke(message)
        content = response.content
        # langchain의 content는 str | list(멀티모달)일 수 있어 str로 정규화한다.
        if isinstance(content, list):
            return "".join(
                part if isinstance(part, str) else str(part.get("text", ""))
                for part in content
            )
        return content

