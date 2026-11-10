"""Text-layer types shared by PDF ingestion and image-only evaluation."""
from dataclasses import dataclass,asdict

@dataclass(frozen=True)
class Word:
    text: str
    bbox: tuple[float,float,float,float]
    # Engine-reported OCR score; not a probability of correctness.
    confidence: float | None = None

@dataclass(frozen=True)
class PageText:
    page: int
    method: str
    width: float
    height: float
    words: tuple[Word,...]
    warnings: tuple[str,...] = ()

    def to_dict(self):return asdict(self)
