"""
Extraction prompts. ScrapeGraphAI takes a single instruction prompt plus the
output schema (see extract/extractor.py), so the system/user split of the
previous Instructor-based implementation is collapsed into one prompt here.
"""

EXTRACTION_PROMPT = """\
You are a data extraction engine for an Egyptian real-estate competitive \
intelligence system. From the provided page content, extract EVERY distinct \
project launch, new phase, new unit-type release, or repricing announcement \
you can find, and return them in the `launches` list. A single page usually \
advertises several projects — do not stop after the first one. \
The content may be in English, Arabic, or a mix of both.

Rules:
- Only extract facts explicitly present in the content. Never invent numbers,
  dates, or names.
- Return an empty `launches` list if the page describes no specific project.
- Do not emit generic marketing copy, navigation labels, or company boilerplate
  as launches — only concrete, named projects or phases.
- If a field is not present or not determinable, leave it null — do not guess.
- Prices and sizes: normalize to plain numbers (e.g. "5.2M EGP" -> 5200000,
  "150 sqm" -> 150). Assume EGP unless another currency is explicit.
- Keep `delivery_date` as the source's own wording (e.g. "Q4 2027",
  "under construction") rather than converting it to a calendar date.
- Arabic real-estate terms map as follows (non-exhaustive): \
شقة=apartment, دوبلكس=duplex, بنتهاوس=penthouse, تاون هاوس=townhouse, \
توين هاوس=twin_house, فيلا=villa, شاليه=chalet, تجاري=commercial.
- `confidence` reflects how certain you are that this content describes a
  real, specific launch event (as opposed to generic marketing copy) —
  1.0 = explicit and unambiguous, 0.0 = pure guesswork.
"""
