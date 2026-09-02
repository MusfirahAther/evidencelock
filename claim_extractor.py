import re

# -------------------------------------------------------------
# 1. Helper Function: parse_number
# Cleans numeric text (removes commas like "5,000") and converts
# it to a clean Python int or float.
# -------------------------------------------------------------
def parse_number(num_str):
    """
    Converts a number string (e.g. '5,000' or '18.5') to an int or float.
    """
    clean_str = num_str.replace(",", "").strip()
    try:
        val = float(clean_str)
        # Return as integer if it's a whole number (e.g. 5000 instead of 5000.0)
        if val.is_integer():
            return int(val)
        return val
    except ValueError:
        return None


# -------------------------------------------------------------
# 2. Helper Function: extract_time_period
# Searches a sentence for common time reference keywords such as
# 'the most recent month', 'last year', 'the reported period', etc.
# -------------------------------------------------------------
def extract_time_period(sentence):
    """
    Finds and extracts any time-period phrases mentioned in the sentence.
    Returns the time phrase as a string, or None if no time period is found.
    """
    # Regex Patterns for Time Expressions:
    # - Matches comparative periods: 'most recent month compared to the previous month'
    # - Matches specific periods: 'during the reported period', 'in 2023', 'in Q3'
    # - Matches relative years: 'compared to the previous year', 'last year'
    time_patterns = [
        r'(?:in|during|for|over)\s+(?:the\s+)?(?:most\s+recent\s+month|reported\s+period|last\s+(?:year|quarter|month)|previous\s+(?:year|quarter|month)|past\s+\w+|\d{4}|Q[1-4])(?:\s+compared\s+to\s+(?:the\s+)?(?:previous|last)\s+(?:month|year|quarter))?',
        r'compared\s+to\s+(?:the\s+)?(?:previous|last)\s+(?:year|quarter|month)',
        r'(?:most\s+recent|previous|last)\s+(?:month|year|quarter)',
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b'
    ]

    for pattern in time_patterns:
        match = re.search(pattern, sentence, re.IGNORECASE)
        if match:
            time_str = match.group(0).strip()
            # Remove leading preposition (in, during, for, over) for a cleaner time label
            clean_time_str = re.sub(r'^(?:in|during|for|over)\s+', '', time_str, flags=re.IGNORECASE).strip()
            return clean_time_str

    return None


# -------------------------------------------------------------
# 3. Main Extraction Function: extract_claims
# Scans input text and returns a list of dictionaries, one for
# each checkable numeric claim found.
# -------------------------------------------------------------
def extract_claims(report_text):
    """
    Scans report_text and extracts structured claims for:
      - TYPE 1 (growth): Percentage increase/decrease claims (e.g. 'Revenue increased by 18%')
      - TYPE 2 (total):  Count/sum claims (e.g. 'We processed a total of 5,000 orders')
    
    Returns a list of dicts with keys:
      ['original_sentence', 'claim_type', 'claimed_value', 'subject', 'time_period']
    """
    claims = []

    # Common business metrics to identify the subject of a claim
    known_metrics = [
        "revenue", "sales", "profit", "orders", "customers",
        "units", "margin", "income", "expenses", "transactions", "volume"
    ]

    # Split report text into lines
    lines = report_text.split("\n")

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Skip numbered headings like "1. Revenue Growth" or lines ending with ":"
        if re.match(r"^\d+\.\s+[A-Za-z\s]+$", line) or line.endswith(":"):
            continue

        # Split sentences if multiple exist on the same line (separated by . ! ?)
        sentences = re.split(r"(?<=[.!?])\s+", line)

        for sentence in sentences:
            sentence = sentence.strip()
            # Strip leading list bullets/numbers (e.g. "1. " or "- ")
            clean_sentence = re.sub(r"^(?:\d+[\.\)]|\-|\*)\s*", "", sentence).strip()
            if not clean_sentence:
                continue

            # ---------------------------------------------------------
            # REGEX PATTERN 1: Growth / Percentage Claims
            # - growth_verbs: matches action words ("increased", "grew", "rose", "dropped", etc.)
            # - percent_pattern: matches a number followed by % or "percent" (e.g. "18%", "25 %")
            # - discount_filter: ignores conditions like "discounts above 20%" (not a growth claim)
            # ---------------------------------------------------------
            growth_verbs = r"\b(?:increased|grew|grown|rose|jumped|climbed|decreased|dropped|declined|fell|growth)\b"
            percent_pattern = r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)"
            discount_filter = r"\b(?:discount|rate\s+of|threshold)\s*(?:above|below|over|under|of)?\s*\d+\s*%"

            has_growth_verb = bool(re.search(growth_verbs, clean_sentence, re.IGNORECASE))
            percent_match = re.search(percent_pattern, clean_sentence, re.IGNORECASE)
            is_discount = bool(re.search(discount_filter, clean_sentence, re.IGNORECASE))

            if has_growth_verb and percent_match and not is_discount:
                val = parse_number(percent_match.group(1))

                # Find the subject (metric) being discussed
                subject = None
                for metric in known_metrics:
                    if re.search(rf"\b{metric}\b", clean_sentence, re.IGNORECASE):
                        subject = metric
                        break

                # Fallback: extract word right before the growth verb
                if not subject:
                    subj_match = re.search(rf"([A-Za-z]+)\s+{growth_verbs}", clean_sentence, re.IGNORECASE)
                    if subj_match:
                        subject = subj_match.group(1).lower()

                time_period = extract_time_period(clean_sentence)

                claims.append({
                    "original_sentence": clean_sentence,
                    "claim_type": "growth",
                    "claimed_value": val,
                    "subject": subject if subject else "metric",
                    "time_period": time_period
                })
                continue

            # ---------------------------------------------------------
            # REGEX PATTERN 2: Total / Count Claims
            # - total_phrase: matches "total of 5,000 orders", "processed a total of 5,000 orders"
            # - alt_total_phrase: matches "5,000 total orders"
            # Both capture Group 1 (the count number) and Group 2 (what is being counted)
            # ---------------------------------------------------------
            total_phrase = r"(?:total\s+of|totaling|sum\s+of|processed\s+a\s+total\s+of|count\s+of)\s+([\d,]+(?:\.\d+)?)\s*([A-Za-z]+)"
            alt_total_phrase = r"([\d,]+(?:\.\d+)?)\s+total\s+([A-Za-z]+)"

            match_total = re.search(total_phrase, clean_sentence, re.IGNORECASE)
            match_alt = re.search(alt_total_phrase, clean_sentence, re.IGNORECASE)
            target_match = match_total or match_alt

            if target_match:
                raw_num = target_match.group(1)
                raw_subject = target_match.group(2).lower()
                val = parse_number(raw_num)
                time_period = extract_time_period(clean_sentence)

                claims.append({
                    "original_sentence": clean_sentence,
                    "claim_type": "total",
                    "claimed_value": val,
                    "subject": raw_subject,
                    "time_period": time_period
                })
                continue

    return claims
