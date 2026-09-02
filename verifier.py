import re
import pandas as pd
import numpy as np

# -------------------------------------------------------------
# 1. Helper Function: find_column
# Safely locates a column in the DataFrame by doing case-insensitive
# and whitespace-insensitive matching against candidate names.
# -------------------------------------------------------------
def find_column(df, candidates):
    """
    Searches df.columns for any of the candidate column names,
    ignoring case and leading/trailing whitespace.
    Returns the exact column name in df, or None if not found.
    """
    cols_map = {str(col).strip().lower(): col for col in df.columns}
    for cand in candidates:
        cand_clean = cand.strip().lower()
        if cand_clean in cols_map:
            return cols_map[cand_clean]
    return None


# -------------------------------------------------------------
# 2. Helper Function: is_within_tolerance
# Checks if the claimed value matches the real calculated value
# within a 1% tolerance margin.
# -------------------------------------------------------------
def is_within_tolerance(claimed, real, claim_type="growth"):
    """
    Determines if claimed value is within 1% of the real value.
    - For growth claims (percentages): within 1 percentage point (e.g. 21.4% vs 21.44%)
      or relative 1% error.
    - For total counts: relative difference <= 1% (0.01).
    """
    if claimed is None or real is None:
        return False

    abs_diff = abs(claimed - real)

    if claim_type == "growth":
        # Check percentage point difference (<= 1.0) or relative error (<= 1%)
        if abs_diff <= 1.0:
            return True
        if abs(real) > 0 and (abs_diff / abs(real)) <= 0.01:
            return True
        return False
    else:
        # Total counts: relative difference <= 1%
        if real == 0:
            return abs_diff == 0
        return (abs_diff / abs(real)) <= 0.01


# -------------------------------------------------------------
# 3. Main Verification Function: verify_claim
# Takes a single extracted claim dictionary and a pandas DataFrame,
# calculates the ground-truth value, and returns the verdict and evidence.
# -------------------------------------------------------------
def verify_claim(claim, df):
    """
    Verifies a numeric claim against the provided DataFrame.

    Parameters:
      claim (dict): Dictionary with keys 'original_sentence', 'claim_type',
                    'claimed_value', 'subject', 'time_period'.
      df (pd.DataFrame): The ground truth dataset.

    Returns:
      dict: {
          'original_sentence': str,
          'verdict': 'CORRECT' | 'WRONG' | 'UNCLEAR',
          'claimed_value': float | int,
          'real_value': float | int | None,
          'evidence': str
      }
    """
    original_sentence = claim.get("original_sentence", "")
    claim_type = (claim.get("claim_type") or "").lower()
    claimed_val = claim.get("claimed_value")
    subject = (claim.get("subject") or "").lower()
    time_period = (claim.get("time_period") or "").lower()

    # Safety check: ensure dataset is present and not empty
    if df is None or df.empty:
        return {
            "original_sentence": original_sentence,
            "verdict": "UNCLEAR",
            "claimed_value": claimed_val,
            "real_value": None,
            "evidence": "No dataset uploaded or dataset is completely empty."
        }

    if claimed_val is None:
        return {
            "original_sentence": original_sentence,
            "verdict": "UNCLEAR",
            "claimed_value": None,
            "real_value": None,
            "evidence": "No checkable numeric value was found in the claim."
        }

    # =========================================================
    # TYPE 1: GROWTH / PERCENTAGE CLAIMS
    # =========================================================
    if claim_type == "growth":
        # 1. Identify which metric column to calculate (Sales, Profit, etc.)
        if subject in ["revenue", "sales", "annual sales", "monthly sales", "turnover", "income"]:
            metric_col = find_column(df, ["Sales", "Revenue", "Total Sales", "Amount", "Gross Sales"])
            metric_label = "Sales"
        elif subject in ["profit", "net profit", "earnings", "margin"]:
            metric_col = find_column(df, ["Profit", "Net Profit", "Earnings", "Net Income"])
            metric_label = "Profit"
        elif subject in ["orders", "order volume", "volume"]:
            metric_col = find_column(df, ["Order ID", "Sales"])
            metric_label = "Orders"
        else:
            metric_col = find_column(df, ["Sales", "Revenue", "Profit"])
            metric_label = subject.capitalize()

        if not metric_col or metric_col not in df.columns:
            return {
                "original_sentence": original_sentence,
                "verdict": "UNCLEAR",
                "claimed_value": claimed_val,
                "real_value": None,
                "evidence": f"Could not find matching metric column in dataset for subject '{subject}'."
            }

        # 2. Identify and parse the Date column
        date_col = find_column(df, ["Order Date", "Date", "Invoice Date", "Transaction Date", "Ship Date"])
        if not date_col or date_col not in df.columns:
            return {
                "original_sentence": original_sentence,
                "verdict": "UNCLEAR",
                "claimed_value": claimed_val,
                "real_value": None,
                "evidence": "No recognizable Date column (e.g. 'Order Date') found in dataset for time-series calculation."
            }

        # Safe date conversion to avoid crashes on bad formats
        try:
            parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
        except Exception as e:
            return {
                "original_sentence": original_sentence,
                "verdict": "UNCLEAR",
                "claimed_value": claimed_val,
                "real_value": None,
                "evidence": f"Error parsing dates in '{date_col}': {str(e)}"
            }

        valid_mask = parsed_dates.notna()
        if not valid_mask.any():
            return {
                "original_sentence": original_sentence,
                "verdict": "UNCLEAR",
                "claimed_value": claimed_val,
                "real_value": None,
                "evidence": f"The '{date_col}' column contains no valid timestamps."
            }

        # Build working subset with valid parsed dates and numeric metric
        df_working = df[valid_mask].copy()
        df_working["_clean_date"] = parsed_dates[valid_mask]
        df_working["_metric_num"] = pd.to_numeric(df_working[metric_col], errors="coerce").fillna(0)

        # 3. Detect time window: Month-over-Month vs Year-over-Year
        is_monthly = any(term in time_period or term in original_sentence.lower() for term in ["month", "monthly", "recent month", "mom"])
        is_yearly = any(term in time_period or term in original_sentence.lower() for term in ["year", "annual", "annually", "yoy", "previous year"])

        # Monthly growth calculation
        if is_monthly and not (is_yearly and "month" not in time_period):
            df_working["_period"] = df_working["_clean_date"].dt.to_period("M")
            grouped = df_working.groupby("_period")["_metric_num"].sum().sort_index()
            periods = grouped.index.tolist()

            if len(periods) < 2:
                return {
                    "original_sentence": original_sentence,
                    "verdict": "UNCLEAR",
                    "claimed_value": claimed_val,
                    "real_value": None,
                    "evidence": "Dataset requires at least 2 distinct months of data to calculate month-over-month growth."
                }

            curr_period, prev_period = periods[-1], periods[-2]
            curr_val, prev_val = float(grouped[curr_period]), float(grouped[prev_period])

            # Division by zero guard
            if prev_val == 0:
                return {
                    "original_sentence": original_sentence,
                    "verdict": "UNCLEAR",
                    "claimed_value": claimed_val,
                    "real_value": None,
                    "evidence": f"Previous month ({prev_period.strftime('%B %Y')}) {metric_label} was $0.00, cannot compute percentage growth (division by zero)."
                }

            real_growth = round(((curr_val - prev_val) / prev_val) * 100, 2)
            curr_str = curr_period.strftime("%B %Y")
            prev_str = prev_period.strftime("%B %Y")

            verdict = "CORRECT" if is_within_tolerance(claimed_val, real_growth, claim_type="growth") else "WRONG"
            evidence = (
                f"Calculated from {prev_str} {metric_label} (${prev_val:,.2f}) "
                f"to {curr_str} {metric_label} (${curr_val:,.2f}), "
                f"resulting in a {real_growth:+.2f}% change."
            )

            return {
                "original_sentence": original_sentence,
                "verdict": verdict,
                "claimed_value": claimed_val,
                "real_value": real_growth,
                "evidence": evidence
            }

        # Yearly growth calculation
        elif is_yearly:
            df_working["_period"] = df_working["_clean_date"].dt.year
            grouped = df_working.groupby("_period")["_metric_num"].sum().sort_index()
            periods = grouped.index.tolist()

            if len(periods) < 2:
                return {
                    "original_sentence": original_sentence,
                    "verdict": "UNCLEAR",
                    "claimed_value": claimed_val,
                    "real_value": None,
                    "evidence": "Dataset requires at least 2 distinct years of data to calculate annual growth."
                }

            curr_period, prev_period = periods[-1], periods[-2]
            curr_val, prev_val = float(grouped[curr_period]), float(grouped[prev_period])

            # Division by zero guard
            if prev_val == 0:
                return {
                    "original_sentence": original_sentence,
                    "verdict": "UNCLEAR",
                    "claimed_value": claimed_val,
                    "real_value": None,
                    "evidence": f"Previous year ({prev_period}) {metric_label} was $0.00, cannot compute annual growth (division by zero)."
                }

            real_growth = round(((curr_val - prev_val) / prev_val) * 100, 2)

            verdict = "CORRECT" if is_within_tolerance(claimed_val, real_growth, claim_type="growth") else "WRONG"
            evidence = (
                f"Calculated annual {metric_label} growth from {prev_period} (${prev_val:,.2f}) "
                f"to {curr_period} (${curr_val:,.2f}), yielding {real_growth:+.2f}% growth."
            )

            return {
                "original_sentence": original_sentence,
                "verdict": verdict,
                "claimed_value": claimed_val,
                "real_value": real_growth,
                "evidence": evidence
            }

        else:
            return {
                "original_sentence": original_sentence,
                "verdict": "UNCLEAR",
                "claimed_value": claimed_val,
                "real_value": None,
                "evidence": f"Could not determine comparison timeframe ('{time_period}') to verify growth claim."
            }

    # =========================================================
    # TYPE 2: TOTAL / COUNT CLAIMS
    # =========================================================
    elif claim_type == "total":
        # 1. Orders count
        if subject in ["orders", "order"]:
            order_id_col = find_column(df, ["Order ID", "OrderID", "Order_ID"])
            if order_id_col:
                real_count = int(df[order_id_col].nunique())
                evidence = f"Calculated total unique orders ({real_count:,} distinct Order IDs) across the dataset."
            else:
                real_count = int(len(df))
                evidence = f"Calculated total order records ({real_count:,} rows) in the dataset."

        # 2. Customers count
        elif subject in ["customers", "customer"]:
            cust_id_col = find_column(df, ["Customer ID", "CustomerID", "Customer Name"])
            if cust_id_col:
                real_count = int(df[cust_id_col].nunique())
                evidence = f"Calculated total unique customers ({real_count:,} distinct {cust_id_col}s)."
            else:
                real_count = int(len(df))
                evidence = f"Calculated total customer records ({real_count:,} rows)."

        # 3. Total Sales / Revenue sum
        elif subject in ["sales", "revenue"]:
            sales_col = find_column(df, ["Sales", "Revenue", "Total Sales", "Amount"])
            if sales_col:
                sales_series = pd.to_numeric(df[sales_col], errors="coerce").fillna(0)
                real_count = round(float(sales_series.sum()), 2)
                evidence = f"Calculated sum of all {sales_col} records (${real_count:,.2f}) across the dataset."
            else:
                return {
                    "original_sentence": original_sentence,
                    "verdict": "UNCLEAR",
                    "claimed_value": claimed_val,
                    "real_value": None,
                    "evidence": "Could not find a Sales or Revenue column to calculate total sales."
                }

        # 4. Total Units / Quantity sum
        elif subject in ["units", "quantity", "items"]:
            qty_col = find_column(df, ["Quantity", "Units", "Items"])
            if qty_col:
                qty_series = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
                real_count = int(qty_series.sum())
                evidence = f"Calculated total units ({real_count:,}) from the {qty_col} column."
            else:
                real_count = int(len(df))
                evidence = f"Calculated total rows ({real_count:,})."

        # 5. Default fallback count
        else:
            real_count = int(len(df))
            evidence = f"Calculated total row records ({real_count:,}) in dataset for subject '{subject}'."

        verdict = "CORRECT" if is_within_tolerance(claimed_val, real_count, claim_type="total") else "WRONG"

        return {
            "original_sentence": original_sentence,
            "verdict": verdict,
            "claimed_value": claimed_val,
            "real_value": real_count,
            "evidence": evidence
        }

    # Unknown claim type
    else:
        return {
            "original_sentence": original_sentence,
            "verdict": "UNCLEAR",
            "claimed_value": claimed_val,
            "real_value": None,
            "evidence": f"Unsupported claim type: '{claim_type}'."
        }


# -------------------------------------------------------------
# 4. Step 4 Correction Engine: generate_corrected_report
# Replaces incorrect numbers in the report text with ground-truth
# calculated numbers, marks unclear claims, and leaves correct claims intact.
# -------------------------------------------------------------
def generate_corrected_report(original_text, verification_results):
    """
    Generates a corrected version of the business report text based on
    the verification results:
      - For WRONG claims: Replaces the claimed number with the calculated real number.
      - For CORRECT claims: Leaves the sentence unchanged.
      - For UNCLEAR claims: Appends '[Could not verify — insufficient data]'.
    """
    if not original_text or not verification_results:
        return original_text

    corrected_text = original_text

    for res in verification_results:
        orig_sentence = res.get("original_sentence", "")
        verdict = res.get("verdict", "")
        claimed_val = res.get("claimed_value")
        real_val = res.get("real_value")

        if not orig_sentence:
            continue

        # CORRECT claims are left completely unchanged
        if verdict == "CORRECT":
            continue

        # UNCLEAR claims get an explanatory flag
        elif verdict == "UNCLEAR":
            if orig_sentence in corrected_text:
                annotated_sentence = f"{orig_sentence} [Could not verify — insufficient data]"
                corrected_text = corrected_text.replace(orig_sentence, annotated_sentence, 1)

        # WRONG claims have their incorrect numbers replaced with the ground truth
        elif verdict == "WRONG" and real_val is not None:
            new_sentence = orig_sentence

            # Check if this is a count/total claim (e.g. 5,000 orders)
            is_percentage = ("%" in orig_sentence or "percent" in orig_sentence.lower())

            if not is_percentage and isinstance(real_val, (int, float)):
                # Format integer count with commas (e.g. 5111 -> "5,111")
                if isinstance(real_val, int) or (isinstance(real_val, float) and real_val.is_integer()):
                    real_formatted = f"{int(real_val):,}"
                else:
                    real_formatted = f"{real_val:,.2f}"

                # Match claimed number with or without commas (e.g. "5,000" or "5000")
                if isinstance(claimed_val, (int, float)):
                    claimed_regex = rf"\b(?:{claimed_val}|{int(claimed_val):,})\b"
                else:
                    claimed_regex = rf"\b{re.escape(str(claimed_val))}\b"

                new_sentence = re.sub(claimed_regex, real_formatted, new_sentence, count=1)

            # Otherwise, this is a growth/percentage claim
            else:
                real_formatted = f"{real_val:.2f}%" if isinstance(real_val, float) else f"{real_val}%"

                # If growth turned out negative, update phrasing naturally:
                # "increased by 18%" -> "decreased by 28.09%"
                if real_val < 0:
                    pos_val_str = f"{abs(real_val):.2f}%"
                    if re.search(rf"increased\s+by\s+{claimed_val}\s*%", new_sentence, re.IGNORECASE):
                        new_sentence = re.sub(
                            rf"increased\s+by\s+{claimed_val}\s*%",
                            f"decreased by {pos_val_str}",
                            new_sentence,
                            flags=re.IGNORECASE
                        )
                    elif re.search(rf"grew\s+by\s+{claimed_val}\s*%", new_sentence, re.IGNORECASE):
                        new_sentence = re.sub(
                            rf"grew\s+by\s+{claimed_val}\s*%",
                            f"declined by {pos_val_str}",
                            new_sentence,
                            flags=re.IGNORECASE
                        )
                    else:
                        new_sentence = re.sub(rf"{claimed_val}\s*%", real_formatted, new_sentence, count=1)
                else:
                    # Positive growth replacement: "grew by 25%" -> "grew by 21.44%"
                    new_sentence = re.sub(rf"{claimed_val}\s*%", real_formatted, new_sentence, count=1)

            # Substitute in full report text
            if orig_sentence in corrected_text:
                corrected_text = corrected_text.replace(orig_sentence, new_sentence, 1)

    return corrected_text
