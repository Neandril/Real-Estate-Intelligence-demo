"""
Streamlit presentation layer for the DVF Real Estate Intelligence Platform.

Three views:
  1. Market overview   - KPIs and price trends across the loaded warehouse
  2. Map explorer       - commune-level average price per sqm on an interactive map
  3. Price estimator     - live prediction using the trained ML pipeline

Run locally with:  streamlit run dashboard/app.py
(requires the warehouse to be populated and a model trained - see the README)
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.db_clients import get_postgres_engine  # noqa: E402

st.set_page_config(
    page_title="DVF Real Estate Intelligence",
    page_icon="🏠",
    layout="wide",
)


@st.cache_data(ttl=600)
def load_warehouse_data() -> pd.DataFrame:
    engine = get_postgres_engine()
    query = """
        SELECT
            f.sale_price,
            f.surface_real_bati,
            f.surface_terrain,
            f.nb_rooms,
            f.price_per_sqm,
            f.is_outlier,
            c.commune_name,
            c.department_code,
            c.latitude,
            c.longitude,
            pt.property_type_label,
            pt.property_type_code,
            d.full_date,
            d.year
        FROM dwh.fact_transactions f
        JOIN dwh.dim_commune c ON c.commune_key = f.commune_key
        JOIN dwh.dim_property_type pt ON pt.property_type_key = f.property_type_key
        JOIN dwh.dim_date d ON d.date_key = f.date_key
    """
    return pd.read_sql(query, engine)


def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    departments = sorted(df["department_code"].dropna().unique())
    selected_departments = st.sidebar.multiselect(
        "Department", departments, default=departments
    )

    property_types = sorted(df["property_type_label"].dropna().unique())
    selected_types = st.sidebar.multiselect(
        "Property type", property_types, default=property_types
    )

    exclude_outliers = st.sidebar.checkbox("Exclude flagged anomalies", value=True)

    filtered = df[
        df["department_code"].isin(selected_departments)
        & df["property_type_label"].isin(selected_types)
    ]
    if exclude_outliers:
        filtered = filtered[~filtered["is_outlier"]]

    return filtered


def render_overview(df: pd.DataFrame) -> None:
    st.subheader("Market overview")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Transactions", f"{len(df):,}")
    col2.metric("Median price", f"{df['sale_price'].median():,.0f} EUR")
    col3.metric("Median price / sqm", f"{df['price_per_sqm'].median():,.0f} EUR")
    col4.metric("Flagged anomalies", int(df["is_outlier"].sum()) if "is_outlier" in df else 0)

    trend = (
        df.groupby([df["full_date"].astype("datetime64[ns]").dt.to_period("M")])["price_per_sqm"]
        .median()
        .reset_index()
    )
    trend["full_date"] = trend["full_date"].astype(str)
    fig = px.line(
        trend, x="full_date", y="price_per_sqm",
        title="Median price per sqm over time", markers=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.box(
        df, x="property_type_label", y="price_per_sqm", color="department_code",
        title="Price per sqm distribution by property type and department",
    )
    st.plotly_chart(fig2, use_container_width=True)


def render_map(df: pd.DataFrame) -> None:
    st.subheader("Map explorer")

    commune_agg = (
        df.dropna(subset=["latitude", "longitude"])
        .groupby(["commune_name", "latitude", "longitude"])
        .agg(median_price_sqm=("price_per_sqm", "median"), n_transactions=("sale_price", "count"))
        .reset_index()
    )

    if commune_agg.empty:
        st.info("No geolocated transactions match the current filters.")
        return

    center_lat = commune_agg["latitude"].mean()
    center_lon = commune_agg["longitude"].mean()

    fig = px.scatter_map(
        commune_agg,
        lat="latitude",
        lon="longitude",
        size="n_transactions",
        size_max=35,
        color="median_price_sqm",
        hover_name="commune_name",
        hover_data={"median_price_sqm": ":.0f", "n_transactions": True},
        color_continuous_scale="RdYlGn_r",
        opacity=0.85,
        center={"lat": center_lat, "lon": center_lon},
        zoom=5,
        height=650,
        title="Median price per sqm by commune",
    )
    fig.update_traces(marker=dict(sizemin=6, allowoverlap=True))
    fig.update_layout(map_style="open-street-map", margin={"r": 0, "t": 40, "l": 0, "b": 0})
    st.plotly_chart(fig, use_container_width=True)


def render_estimator(df: pd.DataFrame) -> None:
    st.subheader("Price estimator")
    st.caption(
        "Live prediction from the trained RandomForest pipeline "
        "(src/ml/train_price_model.py)."
    )

    from src.ml.predict import predict_price

    col1, col2, col3 = st.columns(3)
    surface = col1.number_input("Living area (sqm)", min_value=10, max_value=1000, value=70)
    land = col2.number_input("Land area (sqm)", min_value=0, max_value=50000, value=200)
    rooms = col3.number_input("Number of rooms", min_value=1, max_value=15, value=3)

    col4, col5 = st.columns(2)
    department = col4.selectbox(
        "Department", sorted(df["department_code"].dropna().unique())
    )
    property_type = col5.selectbox(
        "Property type",
        options=df[["property_type_code", "property_type_label"]]
        .drop_duplicates()
        .set_index("property_type_code")["property_type_label"]
        .to_dict()
        .items(),
        format_func=lambda item: item[1],
    )

    if st.button("Estimate price", type="primary"):
        try:
            price = predict_price(
                surface_real_bati=surface,
                surface_terrain=land,
                nb_rooms=rooms,
                department_code=department,
                property_type_code=property_type[0],
            )
            st.success(f"Estimated sale price: **{price:,.0f} EUR**")
        except FileNotFoundError:
            st.error(
                "No trained model found. Run the `train_price_model` Airflow task "
                "(or `python -m src.ml.train_price_model`) first."
            )


def main() -> None:
    st.title("🏠 DVF Real Estate Intelligence Platform")
    st.caption(
        "MongoDB (raw landing zone) -> Airflow (ELT orchestration) -> "
        "PostgreSQL star schema -> scikit-learn -> this dashboard. "
        "Data: DVF open dataset, data.gouv.fr / Cerema."
    )

    try:
        df = load_warehouse_data()
    except Exception as exc:  # noqa: BLE001 - surfaced directly to the user
        st.error(
            "Could not read the warehouse. Make sure the docker-compose stack is "
            f"running and the ELT pipeline has been executed at least once.\n\n{exc}"
        )
        st.stop()

    if df.empty:
        st.warning("The warehouse is empty. Trigger the `dvf_pipeline` DAG in Airflow first.")
        st.stop()

    filtered_df = render_sidebar(df)

    tab1, tab2, tab3 = st.tabs(["Overview", "Map", "Price estimator"])
    with tab1:
        render_overview(filtered_df)
    with tab2:
        render_map(filtered_df)
    with tab3:
        render_estimator(df)


if __name__ == "__main__":
    main()
