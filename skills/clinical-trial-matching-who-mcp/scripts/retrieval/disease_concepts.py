"""Deterministic multilingual disease terms for registry retrieval.

Patient-facing disease text is preserved. WHO/ClinicalTrials.gov searches use
English concepts because their indexed records and search behavior are
predominantly English. Regional-registry terms remain in the source language.
"""
from __future__ import annotations

import re
from typing import Any


_CONCEPTS: tuple[dict[str, Any], ...] = (
    {"id": "colorectal_cancer", "english": ("colorectal cancer", "colon cancer", "rectal cancer"),
     "aliases": ("结直肠癌", "结肠癌", "直肠癌", "大肠癌", "肠癌", "crc")},
    {"id": "non_small_cell_lung_cancer", "english": ("non-small cell lung cancer", "lung cancer"),
     "aliases": ("非小细胞肺癌", "非小细胞肺腺癌", "肺腺癌", "nsclc")},
    {"id": "small_cell_lung_cancer", "english": ("small cell lung cancer", "lung cancer"),
     "aliases": ("小细胞肺癌", "sclc")},
    {"id": "lung_cancer", "english": ("lung cancer",), "aliases": ("肺癌",)},
    {"id": "breast_cancer", "english": ("breast cancer",), "aliases": ("乳腺癌", "乳癌")},
    {"id": "gastric_cancer", "english": ("gastric cancer", "stomach cancer"),
     "aliases": ("胃癌", "胃腺癌")},
    {"id": "gastroesophageal_junction_cancer", "english": ("gastroesophageal junction cancer", "gastric cancer"),
     "aliases": ("胃食管结合部癌", "胃食管交界癌", "贲门癌", "gej cancer")},
    {"id": "esophageal_cancer", "english": ("esophageal cancer",), "aliases": ("食管癌", "食道癌")},
    {"id": "pancreatic_cancer", "english": ("pancreatic cancer", "pancreatic ductal adenocarcinoma"),
     "aliases": ("胰腺癌", "胰腺导管腺癌", "pdac")},
    {"id": "hepatocellular_carcinoma", "english": ("hepatocellular carcinoma", "liver cancer"),
     "aliases": ("肝细胞癌", "原发性肝癌", "肝癌", "hcc")},
    {"id": "biliary_tract_cancer", "english": ("biliary tract cancer", "cholangiocarcinoma"),
     "aliases": ("胆道癌", "胆管癌", "胆囊癌")},
    {"id": "prostate_cancer", "english": ("prostate cancer",), "aliases": ("前列腺癌",)},
    {"id": "ovarian_cancer", "english": ("ovarian cancer", "fallopian tube cancer", "primary peritoneal cancer"),
     "aliases": ("卵巢癌", "输卵管癌", "原发性腹膜癌")},
    {"id": "cervical_cancer", "english": ("cervical cancer",), "aliases": ("宫颈癌", "子宫颈癌")},
    {"id": "endometrial_cancer", "english": ("endometrial cancer", "uterine cancer"),
     "aliases": ("子宫内膜癌", "子宫癌")},
    {"id": "renal_cell_carcinoma", "english": ("renal cell carcinoma", "kidney cancer"),
     "aliases": ("肾细胞癌", "肾癌", "rcc")},
    {"id": "urothelial_cancer", "english": ("urothelial carcinoma", "bladder cancer"),
     "aliases": ("尿路上皮癌", "膀胱癌")},
    {"id": "head_and_neck_cancer", "english": ("head and neck cancer", "head and neck squamous cell carcinoma"),
     "aliases": ("头颈癌", "头颈部鳞癌", "鼻咽癌", "口腔癌", "hnscc")},
    {"id": "thyroid_cancer", "english": ("thyroid cancer",), "aliases": ("甲状腺癌",)},
    {"id": "melanoma", "english": ("melanoma",), "aliases": ("黑色素瘤",)},
    {"id": "glioma", "english": ("glioma", "brain tumor"), "aliases": ("胶质瘤", "脑胶质瘤")},
    {"id": "glioblastoma", "english": ("glioblastoma", "high-grade glioma"),
     "aliases": ("胶质母细胞瘤", "gbm")},
    {"id": "sarcoma", "english": ("sarcoma",), "aliases": ("肉瘤", "软组织肉瘤", "骨肉瘤")},
    {"id": "neuroendocrine_tumor", "english": ("neuroendocrine tumor", "neuroendocrine carcinoma"),
     "aliases": ("神经内分泌肿瘤", "神经内分泌癌", "net", "nec")},
    {"id": "leukemia", "english": ("leukemia",), "aliases": ("白血病",)},
    {"id": "lymphoma", "english": ("lymphoma",), "aliases": ("淋巴瘤",)},
    {"id": "multiple_myeloma", "english": ("multiple myeloma",), "aliases": ("多发性骨髓瘤", "骨髓瘤")},
    {"id": "mesothelioma", "english": ("mesothelioma",), "aliases": ("间皮瘤",)},
    {"id": "testicular_cancer", "english": ("testicular cancer", "germ cell tumor"),
     "aliases": ("睾丸癌", "生殖细胞肿瘤")},
    {"id": "thymic_tumor", "english": ("thymic tumor", "thymoma", "thymic carcinoma"),
     "aliases": ("胸腺瘤", "胸腺癌")},
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", _clean(value).casefold())


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = _clean(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def contains_cjk(value: Any) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", _clean(value)))


def resolve_disease_terms(cancer_type: Any, search_terms: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve WHO English terms and regional-registry source-language terms.

    Explicit ``search_terms.disease_aliases`` or ``english_disease_terms`` take
    priority and provide an extension point for rare diseases without changing
    this catalog.
    """
    original = _clean(cancer_type)
    supplied = search_terms or {}
    explicit_english = _unique(
        _list(supplied.get("english_disease_terms"))
        + _list(supplied.get("disease_aliases"))
    )
    explicit_english = [value for value in explicit_english if not contains_cjk(value)]
    explicit_local = _unique(
        _list(supplied.get("registry_disease_terms"))
        + _list(supplied.get("chinese_disease_terms"))
    )

    original_key = _key(original)
    matched = None
    for concept in _CONCEPTS:
        candidates = tuple(concept["english"]) + tuple(concept["aliases"])
        keys = [_key(value) for value in candidates]
        if original_key and any(key and (key == original_key or key in original_key) for key in keys):
            matched = concept
            break

    catalog_english = list(matched["english"]) if matched else []
    if explicit_english:
        english = _unique(explicit_english + catalog_english)
        source = "explicit_patient_context"
    elif catalog_english:
        english = _unique(catalog_english)
        source = "deterministic_catalog"
    elif original and not contains_cjk(original):
        english = [original]
        source = "original_english"
    else:
        english = ["solid tumor"]
        source = "safe_pan_tumor_fallback"

    local = _unique(explicit_local + ([original] if original else []))
    return {
        "original": original,
        "concept_id": matched["id"] if matched else None,
        "primary_english": english[0],
        "english_aliases": english,
        "registry_aliases": local,
        "source": source,
        "requires_human_review": source == "safe_pan_tumor_fallback",
    }
