from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from core.models import JudgeResult, JudgeStatus

_JUDGE_TEMPLATE = """\
You are a strict QA evaluator. Given a question, an AI response, and evaluation criteria, \
determine whether the response meets ALL criteria.

Question: {question}

AI Response:
{response}

Evaluation Criteria:
{criteria}

Respond with:
- status: "PASS" if ALL criteria are met, "FAIL" otherwise
- reason: brief explanation (1-2 sentences)"""


class LLMJudge:
    def __init__(self, provider: str, api_key: str, model: str, temperature: float = 0.0):
        self.provider = provider.lower()
        self.prompt = ChatPromptTemplate.from_template(_JUDGE_TEMPLATE)
        self.chain = self.prompt | self._build_llm(api_key, model, temperature).with_structured_output(JudgeResult)

    def _build_llm(self, api_key: str, model: str, temperature: float):
        if self.provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(api_key=api_key, model=model, temperature=temperature)
        elif self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(api_key=api_key, model=model, temperature=temperature)
        else:
            raise ValueError(f"Unsupported provider: '{self.provider}'. Use 'openai' or 'anthropic'.")

    def judge(self, question: str, response: str, criteria: list[str]) -> JudgeResult:
        try:
            result = self.chain.invoke({
                "question": question,
                "response": response,
                "criteria": "\n".join(f"- {c}" for c in criteria),
            })
            return result
        except Exception as e:
            return JudgeResult(status=JudgeStatus.ERROR, reason=f"Judge error: {e}")
