from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Deposit Pricing Analytics",
    page_icon="🏦",
    layout="wide",
)

# Mart tables exported by the weekly GitHub Actions pipeline (dbt on DuckDB).
DATA_DIR = Path(__file__).resolve().parent / "data"


@st.cache_data(ttl=3600)
def run_query(sql: str) -> pd.DataFrame:
    conn = duckdb.connect()  # in-memory; reads the CSVs directly
    try:
        for table in ["fact_deposit_rates", "dim_bank", "dim_product", "fed_funds_history"]:
            conn.execute(
                f"CREATE VIEW {table} AS SELECT * FROM read_csv_auto('{DATA_DIR / (table + '.csv')}')"
            )
        return conn.execute(sql).df()
    finally:
        conn.close()


def load_fact_data() -> pd.DataFrame:
    # Latest snapshot only: the most recent scrape per source and product type.
    return run_query("""
        SELECT
            b.bank_name,
            b.bank_type,
            p.product_display_name,
            p.product_name,
            p.term_months,
            f.apy_pct,
            f.fed_funds_rate,
            f.spread_pct,
            f.passthrough_pct,
            f.scrape_date
        FROM fact_deposit_rates f
        JOIN dim_bank b    ON b.bank_key    = f.bank_key
        JOIN dim_product p ON p.product_key = f.product_key
        QUALIFY f.scrape_date = MAX(f.scrape_date) OVER (PARTITION BY f.source_name, p.product_name)
        ORDER BY f.apy_pct DESC
    """)


def load_fred_history() -> pd.DataFrame:
    return run_query("""
        SELECT date_day, rate_pct, series_name
        FROM fed_funds_history
        ORDER BY date_day
    """)


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🏦 Deposit Pricing Analytics")
st.markdown(
    "Deposit pricing analytics in a wealth management context. "
    "This tool tracks how major U.S. banks respond to Federal Reserve rate changes to support deposit placement decisions "
    "and help identify where client money should go."
)

df = load_fact_data()
fred = load_fred_history()
current_fed_rate = float(df["fed_funds_rate"].iloc[0]) if not df.empty else 0.0
fred_as_of = pd.to_datetime(fred["date_day"].iloc[-1]).strftime("%B %Y") if not fred.empty else ""

st.markdown(
    f"""
    <div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 24px 32px;
        margin: 12px 0 4px 0;
        display: block;
        width: 100%;
    ">
        <p style="color: #a0aec0; font-size: 13px; margin: 0 0 4px 0; letter-spacing: 0.08em; text-transform: uppercase;">Current Fed Funds Rate</p>
        <p style="color: #ffffff; font-size: 48px; font-weight: 700; margin: 0; line-height: 1;">{current_fed_rate:.2f}%</p>
        <p style="color: #718096; font-size: 11px; margin: 8px 0 0 0;">As of {fred_as_of} &nbsp;·&nbsp; Source: FRED, Federal Reserve Bank of St. Louis</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.info(
    f"The Fed funds rate is the benchmark that sets the ceiling on what banks can earn. "
    f"At {current_fed_rate:.2f}%, a bank that fully passes this rate to depositors would offer a {current_fed_rate:.2f}% APY. "
    "In practice, most traditional banks pay a fraction of that and pocket the difference as profit margin. "
    "This dashboard measures exactly how much each bank shares with savers versus how much they keep."
)

# ── Terminology Glossary ──────────────────────────────────────────────────────
st.markdown("### 📖 Key Terms")
st.markdown("Familiarize yourself with these concepts before exploring the data.")

terms = [
    ("APY (Annual Percentage Yield)",
     "The annual interest rate a deposit earns. A 4.00% APY on $100,000 generates $4,000 per year."),
    ("Fed Funds Rate",
     "The Fed's benchmark rate. It directly affects the APY banks offer on deposits. The APY is what determines how much a deposit grows over any given number of years."),
    ("Pass-Through Rate (%)",
     "How much of the Fed's rate a bank shares with savers. 100% means full pass-through. Under 10% means the bank keeps almost everything."),
    ("Spread (%)",
     "The gap between the Fed rate and a bank's APY. A wider spread means more profit for the bank and less for the depositor."),
    ("Online vs. Traditional Bank",
     "Online banks like Marcus, Ally, and SoFi compete on rate. Traditional banks like Chase, BofA, and Wells Fargo compete on branch access and brand."),
    ("Fixed vs. Variable Rates",
     "Savings APYs are variable and move with the Fed. CD rates lock in at the time of deposit and hold for the full term."),
]

cards_html = "<div style='display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px;'>"
for term, definition in terms:
    cards_html += f"""
    <div style="
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 18px 20px;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
    ">
        <p style="font-weight: 600; font-size: 14px; margin: 0 0 6px 0;">{term}</p>
        <p style="font-size: 13px; color: #718096; margin: 0; line-height: 1.5;">{definition}</p>
    </div>"""
cards_html += "</div>"
st.markdown(cards_html, unsafe_allow_html=True)

st.divider()

terms_confirmed = st.checkbox("I have read and understood the key terms above.")

if not terms_confirmed:
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Descriptive: Which Bank Pays the Most?",
    "💰 Descriptive: How Much Will I Earn?",
    "⚡ Diagnostic: Why Do Some Banks Pay More?",
    "💡 Where Should I Deposit My Money?",
])


# ── Tab 1: Current Rates ──────────────────────────────────────────────────────
with tab1:
    st.subheader("Descriptive Analytics: Current Deposit Rates Across All Banks")
    st.caption(
        "Descriptive analytics answers: what does the data show right now? "
        "This is a ranked snapshot of every bank's current APY. "
        "Green = higher APY (better for savers). Red = lower APY (bank keeps more as profit)."
    )

    display_df = df[df["product_name"] == "savings"].copy()

    display_df = display_df[[
        "bank_name", "bank_type", "product_display_name",
        "apy_pct", "passthrough_pct"
    ]].copy()
    display_df["bank_type"] = display_df["bank_type"].str.capitalize()
    display_df["apy_pct"] = display_df["apy_pct"].astype(float).round(2)
    display_df["passthrough_pct"] = display_df["passthrough_pct"].astype(float).round(1)
    display_df = display_df.rename(columns={
        "bank_name": "Bank",
        "bank_type": "Type",
        "product_display_name": "Product",
        "apy_pct": "APY (%)",
        "passthrough_pct": "Pass-Through (%)",
    })

    def _color_apy(series):
        lo, hi = 0.0, 5.5
        out = []
        for v in series:
            ratio = max(0, min(1, (v - lo) / (hi - lo)))
            r = int(220 * (1 - ratio))
            g = int(160 * ratio + 60)
            out.append(f"background-color: rgba({r},{g},70,0.55); color: #111;")
        return out

    st.dataframe(
        display_df.style.apply(_color_apy, subset=["APY (%)"]).format({"APY (%)": "{:.2f}%", "Pass-Through (%)": "{:.1f}%"}),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Banks at the top are paying depositors the most. "
        "Pass-Through shows how much of the Fed's rate each bank shares with savers, higher is better."
    )

    st.subheader("APY Ranked: Best to Worst")
    chart_src = df[df["product_name"] == "savings"].drop_duplicates("bank_name").copy()
    chart_src["apy_pct"] = chart_src["apy_pct"].astype(float).round(2)
    chart_src = chart_src.sort_values("apy_pct", ascending=True)

    fig_rank = px.bar(
        chart_src,
        x="apy_pct",
        y="bank_name",
        orientation="h",
        color="bank_type",
        color_discrete_map={"online": "#3B82F6", "traditional": "#94A3B8"},
        text=chart_src["apy_pct"].apply(lambda v: f"{v:.2f}%"),
        labels={"apy_pct": "APY (%)", "bank_name": "Bank", "bank_type": "Type"},
    )
    fig_rank.add_vline(
        x=current_fed_rate, line_dash="dash", line_color="white", line_width=2,
        annotation_text=f"Fed Rate ({current_fed_rate:.2f}%)",
        annotation_position="top left",
        annotation_font_color="white",
        annotation_font_size=12,
    )
    fig_rank.update_traces(textposition="outside", textfont=dict(color="#111111", size=11))
    fig_rank.update_layout(
        height=max(400, len(chart_src) * 28),
        xaxis_range=[0, 5.5],
        xaxis_title="APY (%)",
        showlegend=True,
        margin=dict(r=20),
        yaxis=dict(categoryorder="total ascending"),
    )
    st.plotly_chart(fig_rank, width="stretch")


# ── Tab 2: What Your Money Earns ─────────────────────────────────────────────
with tab2:
    st.subheader("Descriptive Analytics: What Does $10,000 Actually Earn at Each Bank?")
    st.caption(
        "Descriptive analytics answers: what does the data show right now? "
        "This translates current APYs into real dollar earnings on the same deposit across every bank."
    )
    st.markdown(
        "Same deposit. Same year. Wildly different results depending on where you put it. "
        "These are real numbers based on each bank's current savings APY."
    )

    savings_df = df[df["product_name"] == "savings"].drop_duplicates("bank_name").copy()
    savings_df["apy_pct"] = savings_df["apy_pct"].astype(float)
    savings_df["annual_earnings"] = (savings_df["apy_pct"] / 100 * 10_000).round(2)
    savings_df = savings_df.sort_values("annual_earnings", ascending=True)

    fig = go.Figure()
    for _, row in savings_df.iterrows():
        color = "#3B82F6" if row["bank_type"] == "online" else "#94A3B8"
        fig.add_trace(go.Scatter(
            x=[0, row["annual_earnings"]],
            y=[row["bank_name"], row["bank_name"]],
            mode="lines",
            line=dict(color=color, width=2),
            showlegend=False,
            hoverinfo="skip",
        ))
    fig.add_trace(go.Scatter(
        x=savings_df["annual_earnings"],
        y=savings_df["bank_name"],
        mode="markers+text",
        marker=dict(
            color=savings_df["bank_type"].map({"online": "#3B82F6", "traditional": "#94A3B8"}),
            size=12,
        ),
        text=savings_df["annual_earnings"].apply(lambda v: f"  ${v:,.0f}/yr"),
        textposition="middle right",
        textfont=dict(size=11, color="#111111"),
        hovertemplate="%{y}: $%{x:,.0f}/yr<extra></extra>",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(color="#3B82F6", size=10),
        name="Online"
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(color="#94A3B8", size=10),
        name="Traditional"
    ))
    fig.update_layout(
        height=max(420, len(savings_df) * 28),
        xaxis_tickprefix="$",
        xaxis_title="Annual Earnings on $10,000 Deposit",
        xaxis_range=[0, savings_df["annual_earnings"].max() * 1.25],
        yaxis=dict(categoryorder="total ascending"),
        showlegend=True,
        margin=dict(r=120),
    )
    st.plotly_chart(fig, width="stretch")

    best = savings_df.iloc[-1]
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px;
            padding: 24px 32px;
            margin: 16px 0;
        ">
            <p style="color: #a0aec0; font-size: 13px; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.08em;">Key Takeaway</p>
            <p style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0; line-height: 1.4;">
                Given the current Fed rate of {current_fed_rate:.2f}%, clients who choose the highest-yielding bank
                ({best['bank_name']}) earn <span style="color: #68d391;">${best['annual_earnings']:,.0f} annually</span>
                on a $10,000 deposit.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Tab 3: Pass-Through Analysis ─────────────────────────────────────────────
with tab3:
    st.subheader("Diagnostic Analytics: Why Do Some Banks Pay So Much More Than Others?")

    st.markdown(
        "When the Fed raises rates, banks earn more on every loan they make. The question is whether they share any of that with depositors. "
        "Pass-through rate measures exactly that. It is the bank's current APY divided by the Fed funds rate, expressed as a percentage. "
        "This chart is not just historical trivia. It tells you which banks have a track record of rewarding savers and which ones treat your client's deposit as free money. "
        "A bank with 100 percent pass-through is giving savers the full Fed rate. A bank at 1 percent is keeping 99 percent of every rate hike as pure profit while your client earns almost nothing. "
        "Use this to back up your recommendation with a reason, not just a number."
    )

    st.markdown("""
    | Pass-Through | What it means |
    |---|---|
    | **80% or higher** | Bank consistently rewards savers. Strong choice for your client. |
    | **10% to 50%** | Bank shares some but keeps most. Mediocre. |
    | **Under 10%** | Bank is keeping almost everything as margin. Avoid for deposit accounts. |
    """)

    pt_df = df[df["product_name"] == "savings"].drop_duplicates(
        subset=["bank_name", "product_name"]
    ).sort_values("passthrough_pct", ascending=True)

    fig2 = go.Figure()

    # colored zone backgrounds
    fig2.add_shape(type="rect", x0=0, x1=10, y0=-0.5, y1=len(pt_df)-0.5,
                   fillcolor="rgba(231,76,60,0.12)", line_width=0)
    fig2.add_shape(type="rect", x0=10, x1=80, y0=-0.5, y1=len(pt_df)-0.5,
                   fillcolor="rgba(241,196,15,0.10)", line_width=0)
    fig2.add_shape(type="rect", x0=80, x1=130, y0=-0.5, y1=len(pt_df)-0.5,
                   fillcolor="rgba(59,130,246,0.12)", line_width=0)

    # zone labels
    for x, label in [(5, "Low"), (45, "Medium"), (115, "High")]:
        fig2.add_annotation(x=x, y=len(pt_df)-0.1, text=label,
                            showarrow=False, font=dict(size=11, color="#aaaaaa"),
                            xanchor="center")

    # lollipop lines
    for i, (_, row) in enumerate(pt_df.iterrows()):
        color = "#3B82F6" if row["bank_type"] == "online" else "#94A3B8"
        fig2.add_shape(type="line", x0=0, x1=float(row["passthrough_pct"]),
                       y0=i, y1=i, line=dict(color=color, width=2))

    # dots
    fig2.add_trace(go.Scatter(
        x=pt_df["passthrough_pct"].astype(float),
        y=pt_df["bank_name"],
        mode="markers+text",
        marker=dict(
            color=pt_df["bank_type"].map({"online": "#3B82F6", "traditional": "#94A3B8"}),
            size=14,
        ),
        text=pt_df["passthrough_pct"].astype(float).apply(lambda v: f"  {v:.0f}%"),
        textposition="middle right",
        textfont=dict(size=11, color="#111111"),
        hovertemplate="%{y}: %{x:.1f}% pass-through<extra></extra>",
        showlegend=False,
    ))

    # legend
    for name, color in [("Online", "#3B82F6"), ("Traditional", "#94A3B8")]:
        fig2.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(color=color, size=10), name=name
        ))

    fig2.add_vline(x=100, line_dash="dot", line_color="#555", line_width=1.5,
                   annotation_text="100% = full Fed rate",
                   annotation_position="bottom right",
                   annotation_font_size=11)

    fig2.update_layout(
        height=max(480, len(pt_df) * 32),
        xaxis=dict(title="Pass-Through (%)", range=[0, 130]),
        yaxis=dict(categoryorder="total ascending"),
        showlegend=True,
        margin=dict(r=60),
    )
    st.plotly_chart(fig2, width="stretch")

    st.subheader("Pass-Through Rate: All Banks")
    table_df = pt_df[["bank_name", "bank_type", "apy_pct", "passthrough_pct"]].copy()
    table_df["bank_type"] = table_df["bank_type"].str.capitalize()
    table_df["apy_pct"] = table_df["apy_pct"].astype(float).round(2)
    table_df["passthrough_pct"] = table_df["passthrough_pct"].astype(float).round(1)
    table_df["annual_earnings"] = (table_df["apy_pct"] / 100 * 10_000).round(0).astype(int)
    table_df = table_df.sort_values("passthrough_pct", ascending=False).rename(columns={
        "bank_name": "Bank",
        "bank_type": "Type",
        "apy_pct": "APY (%)",
        "passthrough_pct": "Pass-Through (%)",
        "annual_earnings": "Annual Earnings on $10K",
    })
    def _highlight_extremes(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        max_val = df["Pass-Through (%)"].max()
        min_val = df["Pass-Through (%)"].min()
        for col in ["Bank", "Pass-Through (%)", "Annual Earnings on $10K"]:
            styles.loc[df["Pass-Through (%)"] == max_val, col] = "background-color: rgba(34,197,94,0.3);"
            styles.loc[df["Pass-Through (%)"] == min_val, col] = "background-color: rgba(239,68,68,0.3);"
        return styles

    st.dataframe(
        table_df.style.apply(_highlight_extremes, axis=None).format({
            "APY (%)": "{:.2f}%",
            "Pass-Through (%)": "{:.1f}%",
            "Annual Earnings on $10K": "${:,.0f}",
        }),
        width="stretch",
        hide_index=True,
    )

    top_banks = pt_df[pt_df["passthrough_pct"] >= 80].sort_values("passthrough_pct", ascending=False)
    bottom_banks = pt_df[pt_df["passthrough_pct"] < 10].sort_values("passthrough_pct")

    col_good, col_bad = st.columns(2)

    if not top_banks.empty:
        top_names = ", ".join(top_banks["bank_name"].head(3).tolist())
        top_avg = top_banks["passthrough_pct"].mean()
        col_good.success(
            f"**High pass-through (80%+):** {top_names}\n\n"
            f"These banks average {top_avg:.0f}% pass-through, meaning they share most of the Fed rate with depositors. "
            "When the Fed raises rates, savers at these banks see their APY move too."
        )

    if not bottom_banks.empty:
        bot_names = ", ".join(bottom_banks["bank_name"].head(3).tolist())
        bot_avg = bottom_banks["passthrough_pct"].mean()
        col_bad.error(
            f"**Low pass-through (under 10%):** {bot_names}\n\n"
            f"These banks average {bot_avg:.1f}% pass-through. "
            "Nearly the entire Fed rate increase goes to the bank's bottom line, not the depositor."
        )

    if not top_banks.empty and not bottom_banks.empty:
        best = top_banks.iloc[0]
        worst = bottom_banks.iloc[0]
        best_apy = float(best["apy_pct"])
        worst_apy = float(worst["apy_pct"])
        best_earn = best_apy / 100 * 10_000
        worst_earn = worst_apy / 100 * 10_000
        gap = best_earn - worst_earn
        st.info(
            f"Dollar impact on \\$10,000: {best['bank_name']} ({best_apy:.2f}% APY) earns \\${best_earn:,.0f}/yr. "
            f"{worst['bank_name']} ({worst_apy:.2f}% APY) earns \\${worst_earn:,.0f}/yr. "
            f"That is a \\${gap:,.0f}/year difference on the same deposit."
        )


# ── Tab 4: Bank Recommender ───────────────────────────────────────────────────
with tab4:
    st.subheader("Bank Recommender")
    st.info(
        "The Fed funds rate directly affects the APY banks offer on deposits. "
        "The APY is what determines how much a deposit grows over any given number of years."
    )
    st.caption(
        "Select a deposit amount to see which savings accounts offer the highest returns "
        "and how much that deposit grows over time."
    )

    if "deposit_amount" not in st.session_state:
        st.session_state.deposit_amount = 50_000

    def _sync_slider():
        st.session_state.deposit_amount = st.session_state._dep_slider

    def _sync_input():
        val = st.session_state._dep_input
        st.session_state.deposit_amount = max(1_000, min(1_000_000, val))

    with st.container(border=True):
        st.slider(
            "How much are you depositing?",
            min_value=1_000,
            max_value=1_000_000,
            value=st.session_state.deposit_amount,
            step=1_000,
            format="$%d",
            key="_dep_slider",
            on_change=_sync_slider,
        )
        st.number_input(
            "Or type an amount",
            min_value=1_000,
            max_value=1_000_000,
            value=st.session_state.deposit_amount,
            step=1_000,
            key="_dep_input",
            on_change=_sync_input,
        )
    deposit_amount = st.session_state.deposit_amount

    rec_df = df[df["product_name"] == "savings"].copy()

    rec_df = rec_df.drop_duplicates("bank_name")
    rec_df = rec_df.sort_values("apy_pct", ascending=False).head(5)

    def future_value(principal, apy_pct, years):
        return round(principal * (1 + apy_pct / 100) ** years, 2)

    rec_df["rationale"] = rec_df.apply(
        lambda r: (
            f"Online bank with {float(r['passthrough_pct']):.0f}% Fed rate pass-through. FDIC insured."
            if r["bank_type"] == "online"
            else f"Traditional bank with {float(r['passthrough_pct']):.0f}% pass-through. Large branch network."
        ),
        axis=1,
    )

    BANK_COLORS = {
        "SoFi":                    "#6C37F4",
        "Marcus by Goldman Sachs": "#0066CC",
        "Ally Bank":               "#8B1A1A",
        "Vio Bank":                "#FF6B2B",
        "Bread Savings":           "#1B3B6F",
        "LendingClub Bank":        "#00B2A9",
        "Openbank":                "#E5002B",
        "Popular Direct":          "#EF3E23",
        "EverBank":                "#004990",
        "Limelight Bank":          "#F5A623",
        "Forbright Bank":          "#2E7D32",
        "Zynlo Bank":              "#7B1FA2",
        "Peak Bank":               "#1565C0",
        "Live Oak Bank":           "#2E86AB",
        "Colorado Federal Savings Bank": "#C62828",
        "JPMorgan Chase":          "#117ACA",
        "Bank of America":         "#E31837",
        "Wells Fargo":             "#D71E28",
        "Citibank":                "#003B70",
    }

    st.subheader(f"Top Banks for ${deposit_amount:,.0f} Deposit")

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    # ── Individual bank cards — left: info, right: growth chart ──────────────
    for idx, (_, row) in enumerate(rec_df.iterrows()):
        apy = float(row["apy_pct"])
        fv_1  = future_value(deposit_amount, apy, 1)
        fv_5  = future_value(deposit_amount, apy, 5)
        fv_10 = future_value(deposit_amount, apy, 10)
        color = BANK_COLORS.get(row["bank_name"], "#2ecc71")

        left, right = st.columns([1, 1])

        with left:
            st.markdown(f"### {medals[idx]} {row['bank_name']}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("APY", f"{apy:.2f}%")
            m2.metric("1 Year",  f"${fv_1:,.0f}")
            m3.metric("5 Years", f"${fv_5:,.0f}")
            m4.metric("10 Years", f"${fv_10:,.0f}")
            st.caption(row["rationale"])

        with right:
            fig_card = go.Figure(go.Bar(
                x=["1 Year", "5 Years", "10 Years"],
                y=[fv_1, fv_5, fv_10],
                marker_color=color,
                text=[f"${fv_1:,.0f}", f"${fv_5:,.0f}", f"${fv_10:,.0f}"],
                textposition="outside",
            ))
            fig_card.update_layout(
                height=220,
                margin=dict(t=10, b=10, l=10, r=10),
                yaxis_tickprefix="$",
                yaxis_tickformat=",",
                yaxis_range=[deposit_amount * 0.95, fv_10 * 1.08],
                showlegend=False,
            )
            st.plotly_chart(fig_card, width="stretch")

        st.divider()

    # ── APY comparison bar ────────────────────────────────────────────────────
    bank_colors_list = [BANK_COLORS.get(b, "#2ecc71") for b in rec_df.sort_values("apy_pct")["bank_name"]]
    fig_apy = go.Figure(go.Bar(
        x=rec_df.sort_values("apy_pct")["apy_pct"],
        y=rec_df.sort_values("apy_pct")["bank_name"],
        orientation="h",
        marker_color=bank_colors_list,
        text=rec_df.sort_values("apy_pct")["apy_pct"].apply(lambda v: f"{v:.2f}%"),
        textposition="outside",
    ))
    fig_apy.update_layout(
        title="APY Comparison — Top 5 Banks",
        xaxis_title="APY (%)",
        height=280,
        showlegend=False,
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig_apy, width="stretch")

    # ── Compound growth over 10 years ─────────────────────────────────────────
    years = list(range(0, 11))
    growth_rows = []
    for _, row in rec_df.iterrows():
        apy = float(row["apy_pct"])
        for y in years:
            growth_rows.append({
                "Year": y,
                "Balance": future_value(deposit_amount, apy, y),
                "Bank": row["bank_name"],
            })
    growth_df = pd.DataFrame(growth_rows)

    fig_growth = go.Figure()

    for _, row in rec_df.iterrows():
        bank = row["bank_name"]
        apy  = float(row["apy_pct"])
        balances = [future_value(deposit_amount, apy, y) for y in years]
        color = BANK_COLORS.get(bank, "#2ecc71")
        fig_growth.add_trace(go.Scatter(
            x=years, y=balances, name=bank,
            mode="lines",
            line=dict(color=color, width=3),
            hovertemplate=f"<b>{bank}</b><br>Year %{{x}}: $%{{y:,.0f}}<extra></extra>",
        ))
        fig_growth.add_annotation(
            x=10, y=balances[-1],
            text=f"  {bank.split()[0]}: ${balances[-1]:,.0f}",
            showarrow=False, xanchor="left",
            font=dict(color=color, size=11),
        )

    # Chase reference line
    chase_apy = float(df[(df["bank_name"] == "JPMorgan Chase") & (df["product_name"] == "savings")]["apy_pct"].iloc[0]) if not df[(df["bank_name"] == "JPMorgan Chase") & (df["product_name"] == "savings")].empty else 0.01
    chase_balances = [future_value(deposit_amount, chase_apy, y) for y in years]
    fig_growth.add_trace(go.Scatter(
        x=years, y=chase_balances, name="Chase (reference)",
        mode="lines",
        line=dict(color="#aaaaaa", width=2, dash="dot"),
        hovertemplate="<b>Chase</b><br>Year %{x}: $%{y:,.0f}<extra></extra>",
    ))
    fig_growth.add_annotation(
        x=10, y=chase_balances[-1],
        text=f"  Chase: ${chase_balances[-1]:,.0f}",
        showarrow=False, xanchor="left",
        font=dict(color="#aaaaaa", size=11),
    )

    fig_growth.update_layout(
        title=f"How ${deposit_amount:,.0f} Grows Over 10 Years",
        height=520,
        yaxis_tickprefix="$",
        yaxis_tickformat=",",
        yaxis_title="Account Balance ($)",
        xaxis_title="Years",
        hovermode="x unified",
        showlegend=True,
        margin=dict(r=180),
    )
    st.plotly_chart(fig_growth, width="stretch")
