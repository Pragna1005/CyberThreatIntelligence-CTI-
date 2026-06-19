"""
Chunker: converts raw JSONL data files into uniform chunk objects ready for embedding.

Output schema for every chunk:
{
    "chunk_id":  "<source>_<id>_<index>",
    "source":    "MITRE | ThreatFox | MSRC",
    "text":      "...human-readable text that gets embedded...",
    "metadata":  { ...source-specific fields for Qdrant payload + filtering... }
}

Run:
    python scripts/chunker.py
Outputs written to chunks/
"""

import json
import os
import re

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, "json_data")
CHUNKS_DIR = os.path.join(BASE_DIR, "chunks")

CHUNK_SIZE    = 400   # words per chunk
CHUNK_OVERLAP = 50    # word overlap between consecutive chunks


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  Written: {path}  ({len(records)} chunks)")


def split_into_chunks(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into word-based chunks with overlap."""
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def clean_text(text):
    """Remove excess whitespace and citation markers like (Citation: ...)."""
    text = re.sub(r'\(Citation:[^)]+\)', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ---------------------------------------------------------------------------
# MITRE ATT&CK chunker
# ---------------------------------------------------------------------------

def chunk_mitre():
    """
    Input:  json_data/mitre_rag_documents.jsonl
            Fields: id, source, title, text

    Strategy: most docs are under 400 words — keep as single chunk.
              22 docs are over 400 words — split with overlap.

    Text format embedded:
        "Technique: <title> (<id>)\n\n<description text>"
    """
    records = read_jsonl(os.path.join(DATA_DIR, "mitre_rag_documents.jsonl"))
    chunks  = []

    for rec in records:
        technique_id = rec["id"]
        title        = rec["title"]
        raw_text     = clean_text(rec["text"])
        full_text    = f"Technique: {title} ({technique_id})\n\n{raw_text}"

        parts = split_into_chunks(full_text)

        for idx, part in enumerate(parts):
            chunks.append({
                "chunk_id": f"mitre_{technique_id}_{idx}",
                "source":   "MITRE",
                "text":     part,
                "metadata": {
                    "technique_id":  technique_id,
                    "title":         title,
                    "chunk_index":   idx,
                    "total_chunks":  len(parts),
                }
            })

    write_jsonl(os.path.join(CHUNKS_DIR, "mitre_chunks.jsonl"), chunks)
    return chunks


# ---------------------------------------------------------------------------
# ThreatFox IOC chunker
# ---------------------------------------------------------------------------

def chunk_threatfox():
    """
    Input:  json_data/threatfox_sample.jsonl
            Fields: source, first_seen_utc, ioc_value, ioc_type,
                    threat_type, malware_printable, last_seen_utc,
                    confidence_level, is_compromised, reference, tags

    Strategy: each IOC record is already atomic — one record = one chunk.
              Build a human-readable sentence so the embedding captures meaning,
              not just raw field values.

    Text format embedded:
        "IOC: <value> | Type: <ioc_type> | Malware: <name> |
         Threat: <threat_type> | Confidence: <n>% | Tags: <t1, t2>"
    """
    records = read_jsonl(os.path.join(DATA_DIR, "threatfox_sample.jsonl"))
    chunks  = []

    for idx, rec in enumerate(records):
        ioc_value  = rec.get("ioc_value", "")
        ioc_type   = rec.get("ioc_type", "")
        malware    = rec.get("malware_printable") or "Unknown"
        threat     = rec.get("threat_type", "")
        confidence = rec.get("confidence_level", "")
        tags       = ", ".join(str(t) for t in (rec.get("tags") or [])) or "none"
        first_seen = rec.get("first_seen_utc", "")
        reference  = rec.get("reference") or ""

        text = (
            f"IOC: {ioc_value} | "
            f"Type: {ioc_type} | "
            f"Malware: {malware} | "
            f"Threat: {threat} | "
            f"Confidence: {confidence}% | "
            f"Tags: {tags} | "
            f"First seen: {first_seen}"
        )
        if reference:
            text += f" | Reference: {reference}"

        chunks.append({
            "chunk_id": f"threatfox_{ioc_type}_{idx}",
            "source":   "ThreatFox",
            "text":     text,
            "metadata": {
                "ioc_value":        ioc_value,
                "ioc_type":         ioc_type,
                "malware":          malware,
                "threat_type":      threat,
                "confidence_level": confidence,
                "tags":             rec.get("tags") or [],
                "first_seen_utc":   first_seen,
                "is_compromised":   rec.get("is_compromised", False),
                "reference":        reference,
            }
        })

    write_jsonl(os.path.join(CHUNKS_DIR, "threatfox_chunks.jsonl"), chunks)
    return chunks


# ---------------------------------------------------------------------------
# MSRC Security Updates chunker
# ---------------------------------------------------------------------------

def chunk_security_updates():
    """
    Input:  json_data/security_updates.jsonl
            Fields: source, cve_id, product, url, base_score,
                    cvss_vector, exploitability, has_faq,
                    has_workaround, has_mitigation

    Strategy: each CVE is already short — one record = one chunk.

    Text format embedded:
        "CVE: <id> | Product: <name> | Severity: <score> (<level>) |
         Exploitability: <text> | Mitigation available: Yes/No"
    """
    records = read_jsonl(os.path.join(DATA_DIR, "security_updates.jsonl"))
    chunks  = []

    for idx, rec in enumerate(records):
        cve_id      = rec.get("cve_id", "")
        product     = rec.get("product", "")
        score       = float(rec.get("base_score") or 0)
        exploitability = rec.get("exploitability", "")
        has_mit     = rec.get("has_mitigation", False)
        has_wa      = rec.get("has_workaround", False)
        cvss        = rec.get("cvss_vector", "")
        url         = rec.get("url", "")

        if score >= 9.0:
            severity_label = "Critical"
        elif score >= 7.0:
            severity_label = "High"
        elif score >= 4.0:
            severity_label = "Medium"
        else:
            severity_label = "Low"

        text = (
            f"CVE: {cve_id} | "
            f"Product: {product} | "
            f"Severity: {score} ({severity_label}) | "
            f"Exploitability: {exploitability} | "
            f"Mitigation available: {'Yes' if has_mit else 'No'} | "
            f"Workaround available: {'Yes' if has_wa else 'No'} | "
            f"CVSS Vector: {cvss}"
        )

        chunks.append({
            "chunk_id": f"msrc_{cve_id}_{idx}",
            "source":   "MSRC",
            "text":     text,
            "metadata": {
                "cve_id":          cve_id,
                "product":         product,
                "base_score":      score,
                "severity":        severity_label,
                "exploitability":  exploitability,
                "has_mitigation":  has_mit,
                "has_workaround":  has_wa,
                "cvss_vector":     cvss,
                "url":             url,
            }
        })

    write_jsonl(os.path.join(CHUNKS_DIR, "security_chunks.jsonl"), chunks)
    return chunks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    print("Chunking MITRE ATT&CK ...")
    mitre_chunks = chunk_mitre()

    print("Chunking ThreatFox IOCs ...")
    tf_chunks = chunk_threatfox()

    print("Chunking MSRC Security Updates ...")
    sec_chunks = chunk_security_updates()

    total = len(mitre_chunks) + len(tf_chunks) + len(sec_chunks)
    print(f"\nDone. Total chunks: {total}")
    print(f"  MITRE:     {len(mitre_chunks)}")
    print(f"  ThreatFox: {len(tf_chunks)}")
    print(f"  MSRC:      {len(sec_chunks)}")
