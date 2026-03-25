"""ONNX-классификатор намерений (rag / chat / followup).

Использует fine-tuned ruBERT-tiny2 модель (3.7ms на CPU, 111MB).
Замена LLM-классификатора: бесплатно, офлайн, быстро.
"""

import logging
import os
from pathlib import Path
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)

Intent = Literal["rag", "chat", "followup"]
LABELS: list[str] = ["rag", "chat", "followup"]

_MODEL_DIR = Path(__file__).parent / "intent_model"
_session = None
_tokenizer = None


def _load():
    """Lazy-load ONNX model and tokenizer."""
    global _session, _tokenizer

    if _session is not None:
        return

    import onnxruntime as ort
    from transformers import AutoTokenizer

    model_path = _MODEL_DIR / "model.onnx"
    if not model_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {model_path}")

    _session = ort.InferenceSession(
        str(model_path),
        providers=["CPUExecutionProvider"],
    )
    _tokenizer = AutoTokenizer.from_pretrained(str(_MODEL_DIR))
    logger.info("ONNX intent classifier loaded from %s", _MODEL_DIR)


def classify_intent_onnx(text: str) -> tuple[Intent, float]:
    """Classify intent using local ONNX model.

    Returns:
        (intent, confidence) — e.g. ("rag", 0.95)
    """
    _load()

    inputs = _tokenizer(
        text,
        return_tensors="np",
        padding="max_length",
        truncation=True,
        max_length=128,
    )

    outputs = _session.run(
        None,
        {
            "input_ids": inputs["input_ids"].astype(np.int64),
            "attention_mask": inputs["attention_mask"].astype(np.int64),
        },
    )

    logits = outputs[0][0]
    probs = np.exp(logits - np.max(logits))  # numerically stable softmax
    probs = probs / probs.sum()

    pred_id = int(np.argmax(probs))
    confidence = float(probs[pred_id])
    intent = LABELS[pred_id]

    return intent, confidence  # type: ignore[return-value]
