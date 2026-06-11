import requests
import pandas as pd
import json
import os
from datetime import date, timedelta

# ==================================
# CONFIG — loaded from environment
# (GitHub Actions will inject these)
# ==================================

CLIENT_ID     = os.environ.get("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ZOHO_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("ZOHO_REFRESH_TOKEN")

ZOHO_ACCOUNTS_URL = "https://accounts.zoho.com"
ZOHO_API_BASE     = "https://www.zohoapis.com"

FIELDS = [
    "id",
    "Created_Time",
    "Lead_Source",
    "Lead_Status",
    "Company",
    "First_Name",
    "Last_Name",
    "Email"
]


# ==================================
# GET ACCESS TOKEN
# ==================================

def get_access_token():
    url = f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token"
    params = {
        "refresh_token": REFRESH_TOKEN,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "refresh_token"
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    data = response.json()
    if "access_token" not in data:
        raise Exception(f"Failed to get access token: {data}")
    return data["access_token"]


# ==================================
# FETCH ALL LEADS
# ==================================

def fetch_all_leads(access_token):
    headers     = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    field_string = ",".join(FIELDS)
    url = (
        f"{ZOHO_API_BASE}/crm/v8/Leads"
        f"?fields={field_string}&per_page=200"
    )
    all_records = []

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    payload = response.json()
    all_records.extend(payload.get("data", []))
    info = payload.get("info", {})

    while info.get("more_records"):
        next_page_token = info.get("next_page_token")
        page_url = (
            f"{ZOHO_API_BASE}/crm/v8/Leads"
            f"?fields={field_string}&page_token={next_page_token}"
        )
        response = requests.get(page_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        all_records.extend(payload.get("data", []))
        info = payload.get("info", {})

    return all_records


# ==================================
# BUILD DATAFRAME
# ==================================

def build_dataframe(records):
    rows = []
    for lead in records:
        rows.append({
            "id":          lead.get("id"),
            "created_time": lead.get("Created_Time"),
            "lead_source": lead.get("Lead_Source"),
            "lead_status": lead.get("Lead_Status"),
            "company":     lead.get("Company"),
            "first_name":  lead.get("First_Name"),
            "last_name":   lead.get("Last_Name"),
            "email":       lead.get("Email")
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        df["created_time"] = pd.to_datetime(
            df["created_time"], errors="coerce", utc=True
        )
        df["lead_date"] = df["created_time"].dt.date

    return df


# ==================================
# BUILD KPIs
# ==================================

def build_kpis(df):
    today     = date.today()
    yesterday = today - timedelta(days=1)

    # Start of current week (Monday)
    week_start  = today - timedelta(days=today.weekday())

    # Start of current month
    month_start = today.replace(day=1)

    total  = len(df)
    yest   = len(df[df["lead_date"] == yesterday])
    wtd    = len(df[df["lead_date"] >= week_start])
    mtd    = len(df[df["lead_date"] >= month_start])

    # Lead breakdown by source
    by_source = (
        df["lead_source"]
        .fillna("Unknown")
        .value_counts()
        .to_dict()
    )

    # Lead breakdown by status
    by_status = (
        df["lead_status"]
        .fillna("Unknown")
        .value_counts()
        .to_dict()
    )

    # Last 30 days daily trend (for sparklines)
    thirty_days_ago = today - timedelta(days=29)
    trend_df = df[df["lead_date"] >= thirty_days_ago].copy()
    daily_trend = (
        trend_df.groupby("lead_date")
        .size()
        .reindex(
            pd.date_range(thirty_days_ago, today).date,
            fill_value=0
        )
    )
    sparkline = [int(v) for v in daily_trend.values]

    return {
        "last_updated":    today.isoformat(),
        "total_leads":     total,
        "yesterday_leads": yest,
        "wtd_leads":       wtd,
        "mtd_leads":       mtd,
        "by_source":       by_source,
        "by_status":       by_status,
        "sparkline_30d":   sparkline
    }


# ==================================
# MAIN — saves data.json
# ==================================

def main():
    print("Getting access token...")
    token = get_access_token()

    print("Fetching leads...")
    leads = fetch_all_leads(token)
    print(f"Fetched {len(leads):,} leads")

    print("Building dataframe...")
    df = build_dataframe(leads)

    print("Computing KPIs...")
    kpis = build_kpis(df)

    print("Saving data.json...")
    with open("data.json", "w") as f:
        json.dump(kpis, f, indent=2)

    print("Done! data.json saved.")
    print(json.dumps(kpis, indent=2))


main()
