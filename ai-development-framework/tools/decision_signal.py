"""J0 typed residual signals. They are observations, never admission decisions."""
from dataclasses import dataclass
import math
import re
from typing import Literal, Protocol


Kind = Literal["yes_no", "choice", "score"]
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def _id(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _unit_number(value):
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


@dataclass(frozen=True, slots=True)
class TypedQuestion:
    id: str
    kind: Kind
    choices: tuple[str, ...] = ()
    schema_version: str = "1.0"

    def __post_init__(self):
        if self.schema_version != "1.0" or not _id(self.id) or self.kind not in ("yes_no", "choice", "score"):
            raise ValueError("invalid_typed_question")
        if self.kind == "choice":
            if not isinstance(self.choices, tuple) or len(self.choices) < 2 or not all(_id(item) for item in self.choices) or len(set(self.choices)) != len(self.choices):
                raise ValueError("invalid_typed_question")
        elif self.choices != ():
            raise ValueError("invalid_typed_question")

    def to_dict(self):
        return {"schema_version": self.schema_version, "id": self.id, "kind": self.kind, **({"choices": list(self.choices)} if self.kind == "choice" else {})}


@dataclass(frozen=True, slots=True)
class DecisionSignal:
    provider_id: str
    question_id: str
    kind: Kind
    abstain: bool
    answer: bool | str | int | float | None = None
    confidence: float | None = None
    schema_version: str = "1.0"

    def __post_init__(self):
        if self.schema_version != "1.0" or not _id(self.provider_id) or not _id(self.question_id) or self.kind not in ("yes_no", "choice", "score") or type(self.abstain) is not bool:
            raise ValueError("invalid_decision_signal")
        if self.confidence is not None and not _unit_number(self.confidence):
            raise ValueError("invalid_decision_signal")
        if self.abstain:
            valid_answer = self.answer is None
        elif self.kind == "yes_no":
            valid_answer = type(self.answer) is bool
        elif self.kind == "choice":
            valid_answer = _id(self.answer)
        else:
            valid_answer = _unit_number(self.answer)
        if not valid_answer:
            raise ValueError("invalid_decision_signal")

    def to_dict(self):
        value = {"schema_version": self.schema_version, "provider_id": self.provider_id, "question_id": self.question_id, "kind": self.kind, "abstain": self.abstain, "answer": self.answer}
        if self.confidence is not None:
            value["confidence"] = self.confidence
        return value


class DecisionSignalProvider(Protocol):
    def request(self, question: TypedQuestion) -> DecisionSignal: ...


class NoopDecisionSignalProvider:
    provider_id = "noop"

    def request(self, question: TypedQuestion) -> DecisionSignal:
        return DecisionSignal(provider_id=self.provider_id, question_id=question.id, kind=question.kind, abstain=True)


def request_residual(decision, question: TypedQuestion, provider: DecisionSignalProvider | None = None, *, enabled=False) -> DecisionSignal:
    """Observe only after a hard-rule admit; never alter or create an AdmissionDecision."""
    if not isinstance(question, TypedQuestion):
        raise ValueError("invalid_typed_question")
    abstain = NoopDecisionSignalProvider().request(question)
    if enabled is not True or not isinstance(decision, dict) or decision.get("outcome") != "admit_read":
        return abstain
    try:
        signal = (provider if provider is not None else NoopDecisionSignalProvider()).request(question)
        if type(signal) is not DecisionSignal:
            return abstain
        signal.__post_init__()
    except Exception:
        return abstain
    if signal.question_id != question.id or signal.kind != question.kind:
        return abstain
    if question.kind == "choice" and not signal.abstain and signal.answer not in question.choices:
        return abstain
    return signal
