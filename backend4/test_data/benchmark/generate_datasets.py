"""
Deterministic generator for 6 comprehensive business benchmark datasets.
Seeds are fixed to ensure 100% reproducible ground-truth figures.
"""
from pathlib import Path
import numpy as np
import pandas as pd

BENCHMARK_DIR = Path(__file__).resolve().parent

def generate_all():
    np.random.seed(42)

    # -------------------------------------------------------------
    # 1. Retail Sales (01_retail_sales.csv)
    # -------------------------------------------------------------
    n_retail = 120
    dates = pd.date_range("2024-01-05", periods=n_retail, freq="3D").strftime("%Y-%m-%d")
    categories = ["Electronics", "Furniture", "Office Supplies", "Apparel"]
    regions = ["North", "South", "East", "West"]
    products = {
        "Electronics": ["Pro Laptop", "Noise-Cancelling Headphones", "4K Monitor", "USB-C Hub"],
        "Furniture": ["Ergonomic Desk", "Executive Chair", "Filing Cabinet", "Bookshelf"],
        "Office Supplies": ["Laser Paper Pack", "Gel Pen Box", "Desk Organizer", "Heavy-Duty Stapler"],
        "Apparel": ["Branded Hoodie", "Polo Shirt", "Winter Jacket", "Athletic Cap"]
    }
    
    rows = []
    for i in range(n_retail):
        cat = categories[i % len(categories)]
        reg = regions[(i // 2) % len(regions)]
        prod = products[cat][i % len(products[cat])]
        qty = int(np.random.randint(1, 15))
        base_price = {"Electronics": 450.0, "Furniture": 320.0, "Office Supplies": 35.0, "Apparel": 65.0}[cat]
        unit_price = round(float(base_price + (i % 5) * 5), 2)
        disc_pct = 0.25 if (cat == "Furniture" and i % 3 == 0) else (0.10 if i % 5 == 0 else 0.0)
        unit_cost = round(float(unit_price * (0.65 if cat != "Furniture" else 0.85)), 2)
        
        gross = round(qty * unit_price, 2)
        discount = round(gross * disc_pct, 2)
        revenue = round(gross - discount, 2)
        cogs = round(qty * unit_cost, 2)
        profit = round(revenue - cogs, 2)
        returned = 1 if (i % 11 == 0) else 0
        
        rows.append({
            "order_id": f"ORD-{1000 + i}",
            "date": dates[i],
            "customer_id": f"CUST-{(i % 30) + 1:03d}",
            "region": reg,
            "category": cat,
            "product": prod,
            "quantity": qty,
            "unit_price": unit_price,
            "discount": discount,
            "revenue": revenue,
            "cogs": cogs,
            "profit": profit,
            "returned": returned
        })
    df_retail = pd.DataFrame(rows)
    df_retail.to_csv(BENCHMARK_DIR / "01_retail_sales.csv", index=False)

    # -------------------------------------------------------------
    # 2. Financial P&L (02_financial_pnl.csv)
    # -------------------------------------------------------------
    pnl_periods = pd.date_range("2024-01-01", periods=24, freq="MS").strftime("%Y-%m-%d")
    pnl_rows = []
    base_rev = 120000.0
    for idx, per in enumerate(pnl_periods):
        quarter = f"Q{(idx % 12) // 3 + 1}-{per[:4]}"
        rev = round(base_rev + idx * 4500.0 + (12000.0 if (idx % 12 in [10, 11]) else 0.0), 2)
        cogs = round(rev * 0.52, 2)
        gp = round(rev - cogs, 2)
        mktg = round(rev * 0.14, 2)
        rd = round(rev * 0.10, 2)
        ga = round(rev * 0.08, 2)
        opex = round(mktg + rd + ga, 2)
        ebitda = round(gp - opex, 2)
        depr = round(4500.0 + idx * 50.0, 2)
        interest = round(1200.0 - idx * 20.0, 2)
        ebt = round(ebitda - depr - interest, 2)
        tax = round(max(0.0, ebt * 0.22), 2)
        net_profit = round(ebt - tax, 2)
        
        pnl_rows.append({
            "period": per,
            "quarter": quarter,
            "revenue": rev,
            "cogs": cogs,
            "gross_profit": gp,
            "marketing_spend": mktg,
            "rd_spend": rd,
            "ga_spend": ga,
            "opex": opex,
            "ebitda": ebitda,
            "depreciation": depr,
            "interest": interest,
            "tax": tax,
            "net_profit": net_profit
        })
    df_pnl = pd.DataFrame(pnl_rows)
    df_pnl.to_csv(BENCHMARK_DIR / "02_financial_pnl.csv", index=False)

    # -------------------------------------------------------------
    # 3. Customer E-commerce (03_customer_ecommerce.csv)
    # -------------------------------------------------------------
    n_cust = 100
    channels = ["Organic Search", "Paid Ads", "Social Media", "Referral", "Email Marketing"]
    cust_rows = []
    for i in range(n_cust):
        chan = channels[i % len(channels)]
        orders = int(np.random.randint(1, 18))
        aov = round(float(45.0 + (i % 8) * 15.0), 2)
        total_spend = round(orders * aov, 2)
        days_ago = int(10 + (i * 3) % 180)
        churn = 1 if (days_ago > 90 and i % 2 == 0) else 0
        signup = f"2023-{(i % 12) + 1:02d}-{(i % 25) + 1:02d}"
        
        cust_rows.append({
            "customer_id": f"CUST-{i + 1:04d}",
            "signup_date": signup,
            "acquisition_channel": chan,
            "orders_count": orders,
            "total_spend": total_spend,
            "avg_order_value": aov,
            "last_order_days_ago": days_ago,
            "churn_flag": churn
        })
    df_cust = pd.DataFrame(cust_rows)
    df_cust.to_csv(BENCHMARK_DIR / "03_customer_ecommerce.csv", index=False)

    # -------------------------------------------------------------
    # 4. Inventory Supply Chain (04_inventory_supply_chain.csv)
    # -------------------------------------------------------------
    n_sku = 80
    warehouses = ["Central-Hub", "East-DC", "West-DC", "South-DC"]
    inv_categories = ["Industrial Components", "Safety Gear", "Raw Materials", "Packaging Supplies"]
    inv_rows = []
    for i in range(n_sku):
        wh = warehouses[i % len(warehouses)]
        cat = inv_categories[i % len(inv_categories)]
        soh = int(np.random.randint(20, 800))
        rop = int(np.random.randint(50, 300))
        unit_cost = round(float(15.0 + (i % 15) * 8.5), 2)
        holding_rate = 0.18
        tot_holding = round(soh * unit_cost * holding_rate, 2)
        lead_time = int(5 + (i % 20))
        stockouts = int(max(0, rop - soh) // 25) if soh < rop else 0
        lost_sales = round(stockouts * unit_cost * 1.4, 2)
        
        inv_rows.append({
            "sku": f"SKU-{10000 + i}",
            "product_name": f"Item-{cat[:3].upper()}-{i+1}",
            "category": cat,
            "warehouse": wh,
            "stock_on_hand": soh,
            "reorder_point": rop,
            "unit_cost": unit_cost,
            "holding_cost_rate": holding_rate,
            "total_holding_cost": tot_holding,
            "lead_time_days": lead_time,
            "stockout_events": stockouts,
            "lost_sales_estimate": lost_sales
        })
    df_inv = pd.DataFrame(inv_rows)
    df_inv.to_csv(BENCHMARK_DIR / "04_inventory_supply_chain.csv", index=False)

    # -------------------------------------------------------------
    # 5. Time-Series Monthly (05_timeseries_monthly.csv)
    # -------------------------------------------------------------
    ts_periods = pd.date_range("2023-01-01", periods=36, freq="MS").strftime("%Y-%m-%d")
    ts_rows = []
    for idx, per in enumerate(ts_periods):
        m_idx = idx + 1
        # deterministic linear trend + seasonal multiplier
        season = 1.25 if (m_idx % 12 in [11, 12]) else (0.90 if (m_idx % 12 in [1, 2]) else 1.0)
        rev = round((60000.0 + m_idx * 1800.0) * season, 2)
        units = int(round(rev / 75.0))
        mktg = round(rev * 0.12, 2)
        active_cust = int(500 + m_idx * 25 + (100 if season > 1.0 else 0))
        
        ts_rows.append({
            "date": per,
            "month_index": m_idx,
            "revenue": rev,
            "units_sold": units,
            "marketing_budget": mktg,
            "active_customers": active_cust
        })
    df_ts = pd.DataFrame(ts_rows)
    df_ts.to_csv(BENCHMARK_DIR / "05_timeseries_monthly.csv", index=False)

    # -------------------------------------------------------------
    # 6. Data Quality Challenge (06_data_quality_challenge.csv)
    # -------------------------------------------------------------
    base_rows = [
        {"transaction_id": f"TXN-{100 + i}", "transaction_date": f"2024-03-{(i % 28) + 1:02d}",
         "customer_name": f"Client {(i % 15) + 1}", "segment": "Corporate" if i % 2 == 0 else "SMB",
         "sales_amount": float(150.0 + (i * 25.0)), "cost_amount": float(100.0 + (i * 15.0)),
         "profit_amount": float(50.0 + (i * 10.0))}
        for i in range(50)
    ]
    df_dq = pd.DataFrame(base_rows)
    # Inject exact duplicates (5 duplicate rows)
    dup_rows = df_dq.iloc[:5].copy()
    df_dq = pd.concat([df_dq, dup_rows], ignore_index=True)
    
    # Inject exact missing values
    df_dq.loc[2:6, "customer_name"] = None      # 5 nulls
    df_dq.loc[10:13, "segment"] = None          # 4 nulls
    df_dq.loc[20:22, "sales_amount"] = None     # 3 nulls
    
    # Inject exact outliers in sales_amount
    df_dq.loc[45, "sales_amount"] = 850000.0
    df_dq.loc[46, "sales_amount"] = 1200000.0
    
    # Inconsistent category casing
    df_dq.loc[30, "segment"] = "corporate"
    df_dq.loc[31, "segment"] = "CORPORATE"
    df_dq.loc[32, "segment"] = "smb"
    
    df_dq.to_csv(BENCHMARK_DIR / "06_data_quality_challenge.csv", index=False)
    print("All 6 benchmark datasets generated successfully.")

if __name__ == "__main__":
    generate_all()
