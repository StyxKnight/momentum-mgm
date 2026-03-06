import streamlit as st
import pandas as pd
import psycopg2
from psycopg2 import sql
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
from google import genai

# --- CONFIGURATION & STYLE ---
st.set_page_config(
    page_title="Momentum MGM — Civic Intelligence",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Palette complète des 10 catégories civiques
COLORS = {
    "infrastructure": "#3B82F6",    # Blue
    "environment": "#22C55E",       # Green
    "housing": "#F97316",           # Orange
    "public_safety": "#EF4444",      # Red
    "transportation": "#8B5CF6",    # Purple
    "health": "#EC4899",            # Pink
    "education": "#FACC15",         # Yellow
    "economy": "#10B981",           # Teal
    "parks_culture": "#D946EF",     # Fuchsia
    "governance": "#64748B",        # Slate
}

# --- DATABASE UTILS ---
def get_db_connection():
    return psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        dbname="momentum",
        user="nodebb",
        password="superSecret123"
    )

@st.cache_data(ttl=300)
def run_query(query, params=None):
    """Exécute une requête SQL de manière sécurisée avec paramètres."""
    conn = get_db_connection()
    try:
        df = pd.read_sql(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def get_embedding(query):
    """Génère un embedding via l'API Google Gemini."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        return None
    try:
        client = genai.Client(api_key=api_key)
        result = client.models.embed_content(model="models/gemini-embedding-001", contents=query)
        return result.embeddings[0].values
    except Exception as e:
        st.error(f"Embedding error: {e}")
        return None

# --- SIDEBAR & NAV ---
st.sidebar.markdown("# 🏙️ MGM")
st.sidebar.markdown("### Momentum Montgomery")
page = st.sidebar.radio(
    "Navigation", 
    [
        "1. Overview", 
        "2. Real Estate (Zillow)", 
        "3. Businesses (Yelp)", 
        "4. Neighborhood Comparison",
        "5. Civic Proposals (Decidim)",
        "6. Neighborhood Intelligence",
        "7. AI Query (Semantic)",
        "8. City Incidents"
    ]
)

# Indicateur de fraîcheur des données
freshness_df = run_query("SELECT MAX(collected_at) as last_update FROM civic_data.properties")
if not freshness_df.empty and freshness_df['last_update'].iloc[0]:
    last_ts = freshness_df['last_update'].iloc[0]
    st.sidebar.caption(f"Last data sync: {last_ts.strftime('%Y-%m-%d %H:%M')}")

# --- PAGE 1: OVERVIEW ---
if "1. Overview" in page:
    st.title("🏙️ Montgomery City Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    overview_stats = run_query("""
        WITH latest AS (SELECT MAX(year) as max_yr FROM civic_data.census)
        SELECT metric, AVG(value) as val
        FROM civic_data.census, latest
        WHERE year = max_yr AND metric IN ('median_income', 'poverty_below', 'poverty_total', 'housing_total', 'housing_vacant')
        GROUP BY metric
    """)
    
    incident_count_df = run_query("""
        SELECT COUNT(*) as count FROM civic_data.city_data 
        WHERE reported_at >= '2025-01-01' OR reported_at IS NULL
    """)
    incident_count = incident_count_df['count'].iloc[0] if not incident_count_df.empty else 0
    
    if not overview_stats.empty:
        inc = overview_stats[overview_stats['metric']=='median_income']['val'].mean()
        pov_b = overview_stats[overview_stats['metric']=='poverty_below']['val'].sum()
        pov_t = overview_stats[overview_stats['metric']=='poverty_total']['val'].sum()
        h_v = overview_stats[overview_stats['metric']=='housing_vacant']['val'].sum()
        h_t = overview_stats[overview_stats['metric']=='housing_total']['val'].sum()
        
        col1.metric("Avg Median Income", f"${inc:,.0f}")
        col2.metric("Poverty Rate", f"{(pov_b/pov_t*100):.1f}%")
        col3.metric("Housing Vacancy", f"{(h_v/h_t*100):.1f}%")
        col4.metric("City Incidents (2025)", f"{incident_count:,}")

    st.markdown("---")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Income Trend (2012-2024)")
        df_inc = run_query("SELECT year, AVG(value) as val FROM civic_data.census WHERE metric='median_income' GROUP BY year ORDER BY year")
        if not df_inc.empty:
            fig = px.line(df_inc, x='year', y='val', color_discrete_sequence=[COLORS['economy']])
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("City Data by Category")
        df_cat = run_query("SELECT category, COUNT(*) as count FROM civic_data.city_data GROUP BY category")
        if not df_cat.empty:
            fig = px.bar(df_cat, x='category', y='count', color='category', color_discrete_map=COLORS)
            st.plotly_chart(fig, use_container_width=True)

# --- PAGE 2: REAL ESTATE ---
elif "2. Real Estate" in page:
    st.title("🏠 Zillow Real Estate Market")
    df_prop = run_query("SELECT price, property_type, COALESCE(neighborhood, 'Montgomery County') as neighborhood FROM civic_data.properties WHERE price > 0")
    
    if df_prop.empty:
        st.warning("No property data available.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Price Distribution")
            st.plotly_chart(px.histogram(df_prop, x="price", nbins=50, color_discrete_sequence=[COLORS['housing']]), use_container_width=True)
        with c2:
            st.subheader("Avg Price by Type")
            df_type = df_prop.groupby('property_type')['price'].mean().reset_index()
            st.plotly_chart(px.bar(df_type, x='property_type', y='price', color_discrete_sequence=[COLORS['infrastructure']]), use_container_width=True)
        
        st.subheader("Top Neighborhoods by Average Listing Price")
        df_neigh = df_prop.groupby('neighborhood')['price'].mean().sort_values(ascending=False).head(10).reset_index()
        st.plotly_chart(px.bar(df_neigh, x='price', y='neighborhood', orientation='h', color_discrete_sequence=[COLORS['housing']]), use_container_width=True)

# --- PAGE 3: BUSINESSES ---
elif "3. Businesses" in page:
    st.title("💼 Yelp Business Health")
    df_biz = run_query("""
        SELECT category, rating, is_closed, COALESCE(neighborhood, 'Montgomery') as neighborhood 
        FROM civic_data.businesses
    """)
    
    if df_biz.empty:
        st.warning("No business data available.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Ratings by Category (Top 10)")
            df_cat = df_biz.groupby('category')['rating'].mean().sort_values(ascending=False).head(10).reset_index()
            st.plotly_chart(px.bar(df_cat, x='rating', y='category', orientation='h', color_discrete_sequence=[COLORS['economy']]), use_container_width=True)
        with c2:
            st.subheader("Closure Rate by Neighborhood")
            df_close = df_biz.groupby('neighborhood')['is_closed'].mean().reset_index()
            df_close['is_closed'] *= 100
            st.plotly_chart(px.bar(df_close.sort_values('is_closed', ascending=False).head(10), x='neighborhood', y='is_closed', color_discrete_sequence=[COLORS['public_safety']]), use_container_width=True)

# --- PAGE 4: COMPARISON ---
elif "4. Comparison" in page:
    st.title("👥 Neighborhood Comparison")
    neigh_list_df = run_query("SELECT DISTINCT neighborhood FROM civic_data.census WHERE neighborhood IS NOT NULL ORDER BY neighborhood")
    neigh_list = neigh_list_df['neighborhood'].tolist() if not neigh_list_df.empty else []
    
    selected_neighs = st.multiselect("Select neighborhoods to compare", neigh_list, default=neigh_list[:2] if len(neigh_list)>1 else None)
    
    if selected_neighs:
        df_comp = run_query("""
            SELECT neighborhood, year, value 
            FROM civic_data.census 
            WHERE metric = 'median_income' AND neighborhood IN %s
            ORDER BY year
        """, params=(tuple(selected_neighs),))
        
        if not df_comp.empty:
            st.plotly_chart(px.line(df_comp, x='year', y='value', color='neighborhood', title="Income Growth Comparison"), use_container_width=True)
        else:
            st.warning("No data found for selected neighborhoods.")

# --- PAGE 5: CIVIC PROPOSALS ---
elif "5. Civic Proposals" in page:
    st.title("🗳️ Decidim Civic Proposals")
    
    df_p = run_query("""
        SELECT
            c.name->>'en' as category,
            COUNT(p.id) as count,
            SUM(p.proposal_votes_count) as total_votes
        FROM decidim_proposals_proposals p
        JOIN decidim_categorizations cat ON cat.categorizable_id = p.id
            AND cat.categorizable_type = 'Decidim::Proposals::Proposal'
        JOIN decidim_categories c ON c.id = cat.decidim_category_id
        WHERE p.published_at IS NOT NULL
        GROUP BY c.name->>'en'
        ORDER BY count DESC
    """)
    
    if df_p.empty:
        st.info("No proposals available.")
    else:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Proposals by Category")
            # Mapping category names to COLORS dict keys if possible
            st.plotly_chart(px.bar(df_p, x='category', y='count', color='category'), use_container_width=True)
        
        with c2:
            st.subheader("🔥 Top Voted")
            top_voted = run_query("""
                SELECT title->>'en' as title, proposal_votes_count as votes
                FROM decidim_proposals_proposals
                WHERE published_at IS NOT NULL
                ORDER BY proposal_votes_count DESC
                LIMIT 10
            """)
            if not top_voted.empty:
                st.table(top_voted)

# --- PAGE 6: NEIGHBORHOOD INTELLIGENCE ---
elif "6. Neighborhood Intelligence" in page:
    st.title("🔬 Neighborhood Deep Dive")
    
    all_neighs = run_query("""
        SELECT DISTINCT neighborhood FROM (
            SELECT neighborhood FROM civic_data.properties WHERE neighborhood IS NOT NULL
            UNION SELECT neighborhood FROM civic_data.businesses WHERE neighborhood IS NOT NULL
        ) t ORDER BY neighborhood
    """)
    selected = st.selectbox("Analyze Neighborhood", all_neighs['neighborhood'].tolist() if not all_neighs.empty else [])

    if selected:
        # 1. Fetch data
        df_c = run_query("SELECT year, metric, value FROM civic_data.census WHERE neighborhood = %s", (selected,))
        df_p = run_query("SELECT price, latitude, longitude FROM civic_data.properties WHERE neighborhood = %s AND latitude IS NOT NULL", (selected,))
        df_b = run_query("SELECT rating, is_closed, latitude, longitude FROM civic_data.businesses WHERE neighborhood = %s AND latitude IS NOT NULL", (selected,))
        
        # 2. Layout
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("Location Mapping")
            if not df_p.empty or not df_b.empty:
                map_data = pd.concat([
                    df_p[['latitude', 'longitude']].assign(type='Property'),
                    df_b[['latitude', 'longitude']].assign(type='Business')
                ])
                st.map(map_data)
            else:
                st.warning("No geo-coordinates available for this area.")
                
        with c2:
            st.subheader("Civic Health Score")
            inc_data = df_c[df_c['metric']=='median_income'].sort_values('year')
            inc_score = 0.5
            if len(inc_data) >= 2:
                change = (inc_data.iloc[-1]['value'] - inc_data.iloc[0]['value']) / inc_data.iloc[0]['value']
                inc_score = min(1.0, max(0.0, 0.5 + change))
            
            vac_data = df_c[df_c['metric']=='housing_vacant']
            vac_score = 0.7
            if not vac_data.empty:
                vac_rate = vac_data['value'].iloc[-1] / 100 
                vac_score = max(0.0, 1.0 - vac_rate)

            biz_score = 0.8
            if not df_b.empty:
                biz_score = 1.0 - df_b['is_closed'].mean()

            final_score = (inc_score * 0.4) + (vac_score * 0.3) + (biz_score * 0.3)
            
            if final_score > 0.7: badge = "🟢 High Vitality"
            elif final_score > 0.4: badge = "🟡 Stable"
            else: badge = "🔴 Attention Required"
            
            st.metric("Composite Score", f"{final_score:.2f}", badge)
            st.progress(final_score)
            
            st.caption("Income Trend: {:.2f} | Housing: {:.2f} | Business: {:.2f}".format(inc_score, vac_score, biz_score))

        # City Activity Section
        st.markdown("---")
        st.subheader("🏙️ City Activity")
        df_activity = run_query("""
            SELECT source, COUNT(*) as count,
                   COUNT(*) FILTER (WHERE status IN ('open','Open','OPEN','active','Active')) as open_count
            FROM civic_data.city_data
            WHERE neighborhood = %s
            GROUP BY source
        """, (selected,))
        
        recent_incidents = run_query("""
            SELECT COUNT(*) as count FROM civic_data.city_data 
            WHERE neighborhood = %s AND reported_at >= %s
        """, (selected, datetime.now() - timedelta(days=30)))
        
        if not df_activity.empty:
            m1, m2, m3 = st.columns(3)
            violations = df_activity[df_activity['source'] == 'code_violations']['open_count'].sum()
            permits = df_activity[df_activity['source'] == 'building_permits']['open_count'].sum()
            recent = recent_incidents['count'].iloc[0] if not recent_incidents.empty else 0
            
            m1.metric("Active Violations", violations)
            m2.metric("Active Permits", permits)
            m3.metric("Recent Incidents (30j)", recent)
        else:
            st.info("No recent city activity recorded for this neighborhood.")

        # 3. Trend Chart
        st.markdown("---")
        if not df_c.empty:
            st.subheader("Historical Census Metrics")
            fig_trend = px.line(df_c[df_c['metric'].isin(['median_income', 'population_total'])], 
                               x='year', y='value', color='metric', markers=True)
            st.plotly_chart(fig_trend, use_container_width=True)

# --- PAGE 7: AI QUERY ---
elif "7. AI Query" in page:
    st.title("🧠 Semantic Intelligence")
    
    query = st.text_input("Ask a question about Montgomery neighborhoods...", placeholder="Which neighborhood has the best ratio of high-rated businesses to affordable housing?")
    
    if query:
        st.write(f"🔍 Searching for: *{query}*")
        vec = get_embedding(query)
        
        if vec:
            results = run_query("""
                SELECT source_table, source_id, neighborhood, category, content_text,
                       1 - (embedding <=> %s::vector) as similarity
                FROM civic_data.embeddings
                ORDER BY embedding <=> %s::vector
                LIMIT 10
            """, (vec, vec))
            
            if results.empty:
                st.info("No matching results found.")
            else:
                for idx, row in results.iterrows():
                    with st.container():
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"**{row['neighborhood']}** | {row['category'].title()} ({row['source_table']})")
                        c2.markdown(f"Score: `{row['similarity']:.3f}`")
                        st.write(row['content_text'])
                        st.divider()
        else:
            st.error("🔌 Connect your Google API Key to unlock AI features.")
            st.info("Example queries: 'Where are the new construction permits?', 'Find areas with low poverty but high housing vacancy'.")
        
    st.markdown("---")
    st.subheader("Embeddings Statistics")
    stats = run_query("SELECT source_type, COUNT(*) as count FROM civic_data.embeddings GROUP BY source_type")
    if not stats.empty:
        st.plotly_chart(px.pie(stats, names='source_type', values='count', title="Vectorized Content Breakdown", hole=0.4), use_container_width=True)

# --- PAGE 8: CITY INCIDENTS ---
elif "8. City Incidents" in page:
    st.title("🚨 City Incidents & Data")
    
    # Sidebar Filters
    st.sidebar.subheader("Incident Filters")
    all_sources = run_query("SELECT DISTINCT source FROM civic_data.city_data")['source'].tolist()
    selected_sources = st.sidebar.multiselect("Select Sources", all_sources, default=all_sources)
    
    # 1. Top Metrics
    metrics_df = run_query("""
        SELECT 
            COUNT(*) FILTER (WHERE source = 'code_violations') as violations,
            COUNT(*) FILTER (WHERE source = 'building_permits') as permits,
            COUNT(*) FILTER (WHERE source = 'fire_incidents') as fire
        FROM civic_data.city_data
        WHERE source IN %s
    """, (tuple(selected_sources),))
    
    if not metrics_df.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Code Violations", f"{metrics_df['violations'].iloc[0]:,}")
        m2.metric("Building Permits", f"{metrics_df['permits'].iloc[0]:,}")
        m3.metric("Fire Incidents", f"{metrics_df['fire'].iloc[0]:,}")
    
    st.divider()
    
    # 2. Charts
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("Incidents by Neighborhood (Top 15)")
        neigh_df = run_query("""
            SELECT neighborhood, source, COUNT(*) as count
            FROM civic_data.city_data
            WHERE neighborhood != 'Montgomery' AND source IN %s
            GROUP BY neighborhood, source
            ORDER BY count DESC
            LIMIT 50
        """, (tuple(selected_sources),))
        if not neigh_df.empty:
            # Aggregate to top 15 neighborhoods
            top_15_neighs = neigh_df.groupby('neighborhood')['count'].sum().sort_values(ascending=False).head(15).index
            neigh_df_filtered = neigh_df[neigh_df['neighborhood'].isin(top_15_neighs)]
            fig_neigh = px.bar(neigh_df_filtered, x='neighborhood', y='count', color='source', 
                               color_discrete_map={'code_violations': COLORS['housing'], 
                                                   'building_permits': COLORS['infrastructure'], 
                                                   'fire_incidents': COLORS['public_safety']})
            st.plotly_chart(fig_neigh, use_container_width=True)
            
    with c2:
        st.subheader("Timeline (Last 24 Months)")
        timeline_df = run_query("""
            SELECT date_trunc('month', reported_at) as month, source, COUNT(*) as count
            FROM civic_data.city_data
            WHERE reported_at >= %s AND source IN %s
            GROUP BY month, source
            ORDER BY month
        """, (datetime.now() - timedelta(days=730), tuple(selected_sources)))
        if not timeline_df.empty:
            fig_time = px.line(timeline_df, x='month', y='count', color='source')
            st.plotly_chart(fig_time, use_container_width=True)

    st.subheader("Recent Activity (Latest 50)")
    table_df = run_query("""
        SELECT source, neighborhood, address, status, reported_at
        FROM civic_data.city_data
        WHERE source IN %s
        ORDER BY reported_at DESC NULLS LAST
        LIMIT 50
    """, (tuple(selected_sources),))
    if not table_df.empty:
        st.dataframe(table_df, use_container_width=True)

# --- FOOTER ---
st.markdown("---")
st.markdown("<div style='text-align: center; color: #666;'>© 2026 Momentum MGM | Hackathon World Wide Vibes | Powered by Civic AI</div>", unsafe_allow_html=True)

# --- REQUIREMENTS ---
# streamlit
# pandas
# psycopg2-binary
# plotly
# google-genai
