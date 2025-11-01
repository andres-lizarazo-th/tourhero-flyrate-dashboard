import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime


# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="TourHero Fly Rate Analysis",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# Secure Data Loading from Google Sheets (WITH THE FINAL FIX)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
# FIX 1: Add a leading underscore to the 'secrets' argument.
def load_data_from_gsheet(sheet_name, _secrets):
    """Securely loads data from a private Google Sheet using Streamlit Secrets."""
    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        # FIX 2: Use the new '_secrets' variable here as well.
        creds = Credentials.from_service_account_info(
            _secrets["gcp_service_account"], scopes=scopes
        )
        client = gspread.authorize(creds)
        sheet = client.open(sheet_name).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)

        # Data Type Conversion
        df.columns = df.columns.str.replace(' ', '_').str.lower()
        if 'follower_count' in df.columns:
            df['follower_count'] = pd.to_numeric(df['follower_count'], errors='coerce').fillna(0)
        if 'published_date' in df.columns:
            df['published_date'] = pd.to_datetime(df['published_date'], errors='coerce')
        if 'shell' in df.columns:
            df['shell'] = df['shell'].astype(str).str.upper().map({'TRUE': True, 'FALSE': False})

        return df
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Error: The Google Sheet named '{sheet_name}' was not found. Please check the name and sharing permissions.")
        return None
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return None

# #############################################################################
# # IMPORTANT: CHANGE THIS LINE TO MATCH THE EXACT NAME OF YOUR GOOGLE SHEET   #
# #############################################################################
# The line where you call the function does NOT change.
df_original = load_data_from_gsheet("TourHero_Fly_Rate_Data", st.secrets)
# #############################################################################

# Stop the app if data loading failed
if df_original is None:
    st.stop()

# Drop rows where essential date data is missing
df_original.dropna(subset=['published_date'], inplace=True)

# (The rest of your script remains EXACTLY THE SAME)
# -----------------------------------------------------------------------------
# Sidebar Filters, Main Body, Charts, etc.
# ... all the rest of your code is correct ...
# -----------------------------------------------------------------------------
# Sidebar Filters
st.sidebar.header("Analysis Filters")
shell_filter = st.sidebar.radio("Select Trip Type:", ('All Trips', 'Only "Shell" Trips', 'Only "Non-Shell" Trips'), key='shell_filter')
markets = sorted(df_original['market_-_cleaned'].dropna().unique())
selected_markets = st.sidebar.multiselect('Select Market(s):', options=markets, default=markets)
min_date = df_original['published_date'].min().date()
max_date = df_original['published_date'].max().date()
selected_date_range = st.sidebar.date_input("Select Published Date Range:", value=(min_date, max_date), min_value=min_date, max_value=max_date)
min_followers = int(df_original['follower_count'].min())
max_followers = int(df_original['follower_count'].max())
selected_follower_range = st.sidebar.slider('Filter by Follower Count:', min_value=min_followers, max_value=max_followers, value=(min_followers, max_followers))
use_log_scale = st.sidebar.checkbox("Use Log Scale on Follower Count Graph", value=True)

# Apply All Filters to the Data
df_filtered = df_original.copy()
if shell_filter == 'Only "Shell" Trips':
    df_filtered = df_filtered[df_filtered['shell'] == True]
elif shell_filter == 'Only "Non-Shell" Trips':
    df_filtered = df_filtered[df_filtered['shell'] == False]
if selected_markets:
    df_filtered = df_filtered[df_filtered['market_-_cleaned'].isin(selected_markets)]
if len(selected_date_range) == 2:
    df_filtered = df_filtered[(df_filtered['published_date'].dt.date >= selected_date_range[0]) & (df_filtered['published_date'].dt.date <= selected_date_range[1])]
df_filtered = df_filtered[(df_filtered['follower_count'] >= selected_follower_range[0]) & (df_filtered['follower_count'] <= selected_follower_range[1])]

# Final Data Cleaning
df_cleaned = df_filtered[df_filtered['market_-_cleaned'] != 'mba'].copy()
allowed_statuses = ['cancelled', 'done', 'live', 'confirmed']
df_cleaned = df_cleaned[df_cleaned['fixed_active_status'].isin(allowed_statuses)]
def map_success(status):
    return 'Successful' if status in ['done', 'live', 'confirmed'] else 'Cancelled'
if df_cleaned.empty:
    st.warning("No data available for the current filter selection. Please widen your filter criteria.")
    st.stop()
df_cleaned['trip_success'] = df_cleaned['fixed_active_status'].apply(map_success)

# Main Dashboard Body
st.title("📊 Follower Count vs. Trip Fly Rate")
st.markdown("Use the filters on the left to drill down into the data.")
# KPIs
st.subheader("High-Level Metrics (for current selection)")
total_trips = len(df_cleaned)
successful_trips = len(df_cleaned[df_cleaned['trip_success'] == 'Successful'])
fly_rate = (successful_trips / total_trips * 100) if total_trips > 0 else 0
median_followers = df_cleaned['follower_count'].median()
col1, col2, col3 = st.columns(3)
col1.metric("Total Trips Analyzed", f"{total_trips:,}")
col2.metric("Overall Fly Rate (Success Rate)", f"{fly_rate:.1f}%")
col3.metric("Median Follower Count", f"{median_followers:,.0f}")
# EDA Section
# EDA Section
st.subheader("Exploratory Data Analysis")
col1_eda, col2_eda = st.columns(2)
with col1_eda:
    st.subheader("Distribution of Trips by Follower Bracket")
    bins = [0, 5000, 20000, 50000, 100000, 500000, float('inf')]
    labels = ['0-5k', '5k-20k', '20k-50k', '50k-100k', '100k-500k', '500k+']
    df_cleaned['follower_bin'] = pd.cut(df_cleaned['follower_count'], bins=bins, labels=labels, right=False)
    follower_dist = df_cleaned['follower_bin'].value_counts().reset_index()
    fig_pie = px.pie(follower_dist, values='count', names='follower_bin', title='Percentage of Trips per Bracket', color_discrete_sequence=px.colors.sequential.RdBu)
    st.plotly_chart(fig_pie, use_container_width=True)
with col2_eda:
    st.subheader("Fly Rate by Market Category")
    fly_rate_by_market = df_cleaned.groupby('market_-_cleaned', observed=False)['trip_success'].apply(lambda x: (x == 'Successful').sum() / len(x) * 100 if len(x) > 0 else 0).reset_index(name='fly_rate_percent').sort_values(by='fly_rate_percent', ascending=False)
    fig_market = px.bar(fly_rate_by_market, x='market_-_cleaned', y='fly_rate_percent', title='Fly Rate (%) by Market', labels={'market_-_cleaned': 'Market', 'fly_rate_percent': 'Fly Rate (%)'}, text=fly_rate_by_market['fly_rate_percent'].apply(lambda x: f'{x:.1f}%'))
    fig_market.update_layout(yaxis_range=[0,100])
    st.plotly_chart(fig_market, use_container_width=True)
st.markdown("---")
# Analysis 1: Correlation
st.subheader("1. Follower Count Distribution by Trip Outcome")

st.markdown("This chart shows if successful trips tend to be hosted by TourHeros with more followers.")
fig_box = px.box(df_cleaned, x='trip_success', y='follower_count', color='trip_success', points="all", title="Follower Count: Successful vs. Cancelled Trips", labels={"trip_success": "Trip Outcome", "follower_count": "Follower Count"}, color_discrete_map={"Successful": "green", "Cancelled": "red"})
if use_log_scale:
    fig_box.update_yaxes(type="log", title_text="Follower Count (Log Scale)")
else:
    fig_box.update_yaxes(title_text="Follower Count (Linear Scale)")
st.plotly_chart(fig_box, use_container_width=True)

# --- YOUR ANALYSIS FOR SECTION 1 ---
_ANALYSIS_TEXT_1 = """
#### ✒️ Analysis:
*   **1:** Median follower count between successful (7k) and cancelled trips (3.3k) clearly different.
*   **3:** Fly-rate 4% without shells and 2.7% including shells.
*   **3:** The presence of high-follower outliers in the 'Successful' category suggests that a large audience is a significant factor. Here, the Shells-trips increment the share of the 0-5k followers segment.
"""
st.info(_ANALYSIS_TEXT_1)
# ------------------------------------
# Analysis 2: Threshold
st.subheader("2. Identifying the Fly Rate Threshold")
st.markdown("This chart shows the success rate for different follower brackets. The dotted line represents the average fly rate for your current selection.")
fly_rate_by_bin = df_cleaned.groupby('follower_bin', observed=False)['trip_success'].apply(lambda x: (x == 'Successful').sum() / len(x) * 100 if len(x) > 0 else 0).reset_index(name='fly_rate_percent')
fig_bar = px.bar(fly_rate_by_bin, x='follower_bin', y='fly_rate_percent', title="Fly Rate (%) by TourHero Follower Bracket", labels={"follower_bin": "Follower Bracket", "fly_rate_percent": "Fly Rate (%)"}, text=fly_rate_by_bin['fly_rate_percent'].apply(lambda x: f'{x:.1f}%'))
fig_bar.add_hline(y=fly_rate, line_dash="dot", annotation_text=f"Average Fly Rate: {fly_rate:.1f}%", annotation_position="bottom right")
fig_bar.update_layout(yaxis_range=[0,100])
st.plotly_chart(fig_bar, use_container_width=True)

# --- NEW: Interactive Threshold Calculator (Corrected Logic) ---
st.markdown("---")
st.subheader("Calculate Follower Threshold for a Target Fly Rate")
st.markdown("Use the slider below to select a target fly rate. The app will calculate the minimum follower count suggested to achieve this rate for the group of all hosts **at or above** that follower count.")

target_fly_rate = st.slider("Select your target fly rate (%):", min_value=1, max_value=100, value=25, step=1)

# --- Perform the Correct Calculation ---
# Sort the dataframe by follower count in DESCENDING order
df_threshold_calc = df_cleaned.sort_values('follower_count', ascending=False).copy()
# Create a column for successful trips (1 or 0)
df_threshold_calc['is_successful'] = (df_threshold_calc['trip_success'] == 'Successful').astype(int)
# Calculate the cumulative number of successful trips (from top down)
df_threshold_calc['cumulative_successes'] = df_threshold_calc['is_successful'].cumsum()
# Calculate the cumulative number of total trips (from top down)
df_threshold_calc['cumulative_trips'] = range(1, len(df_threshold_calc) + 1)
# Calculate the fly rate for the group at or above the current follower count
df_threshold_calc['fly_rate_at_or_above'] = (df_threshold_calc['cumulative_successes'] / df_threshold_calc['cumulative_trips']) * 100

# Find all rows that meet or exceed the target fly rate
result_df = df_threshold_calc[df_threshold_calc['fly_rate_at_or_above'] >= target_fly_rate]

# Display the result
if not result_df.empty:
    # The answer is the follower count of the LAST row in this filtered group
    # This represents the lowest follower count that still maintains the target rate for the group above it
    suggested_threshold = result_df['follower_count'].iloc[-1]
    st.metric(
        label=f"Suggested Minimum Follower Threshold to achieve ≥ {target_fly_rate}% Fly Rate",
        value=f"{int(suggested_threshold):,}"
    )
else:
    # Handle the case where the target is never reached
    max_possible_rate = df_threshold_calc['fly_rate_at_or_above'].max() if not df_threshold_calc.empty else 0
    st.warning(f"The target of {target_fly_rate}% was not reached with the current filters. The maximum achievable fly rate for any segment is {max_possible_rate:.1f}%.")
_ANALYSIS_TEXT_2 = """
#### ✒️ Analysis:
*   **1:** There appears to be a clear difference in the median follower count between successful and cancelled trips.
*   **2:** The presence of high-follower outliers in the 'Successful' category suggests that a large audience is a significant factor.
"""
st.info(_ANALYSIS_TEXT_2)
st.markdown("---")
# --- YOUR ANALYSIS FOR SECTION 1 ---

# ------------------------------------
# Analysis 3: Cohorts
st.subheader("3. Deeper Analysis of User Research Cohorts")
st.markdown(f"Based on the median follower count of **{median_followers:,.0f}** for the current selection, the four key cohorts are:")
df_cleaned['follower_level'] = df_cleaned['follower_count'].apply(lambda x: 'High Followers' if x >= median_followers else 'Low Followers')
df_cleaned['cohort'] = df_cleaned['follower_level'] + " | " + df_cleaned['trip_success']
cohort_summary = df_cleaned.groupby('cohort').agg(number_of_trips=('tour_id', 'count'), number_of_unique_tourheros=('tourhero_email', 'nunique'), avg_follower_count=('follower_count', 'mean')).round(0).reset_index().sort_values(by='cohort', ascending=False)
st.dataframe(cohort_summary, use_container_width=True)
st.subheader("Cohort Composition by Market")
st.markdown("This chart shows the market breakdown within each of the four cohorts.")
cohort_market_dist = df_cleaned.groupby(['cohort', 'market_-_cleaned'], observed=False).size().unstack(fill_value=0)
cohort_market_percent = cohort_market_dist.apply(lambda x: x / x.sum() * 100, axis=1).reset_index()
cohort_market_plot_df = cohort_market_percent.melt(id_vars='cohort', var_name='market', value_name='percentage')
fig_cohort_market = px.bar(cohort_market_plot_df, x='cohort', y='percentage', color='market', title='Market Distribution Within Each Cohort', labels={'cohort': 'User Research Cohort', 'percentage': 'Percentage of Trips (%)'}, text=cohort_market_plot_df['percentage'].apply(lambda x: f'{x:.0f}%' if x > 5 else ''))
st.plotly_chart(fig_cohort_market, use_container_width=True)
_ANALYSIS_TEXT_3 = """
#### ✒️ Analysis:
*   **1:** The threshold for getting a better chance of fly-rate over average is over 20k followers. 
*   **2:** However, to get closer to 20% with current business conditions, the followers should be higher than 300k.
*   **2:** The amount of data for the current trips is too low to perform a highly accurate analysis, as we have only a small number of trips created with heroes having more than 300k followers (17 in total, of which 15 were cancelled).


"""
st.info(_ANALYSIS_TEXT_3)
# Download Section
st.markdown("#### Download Cohort Data")
if not cohort_summary.empty:
    selected_cohort = st.selectbox("Choose a cohort to view and download its data:", cohort_summary['cohort'].unique())
    cohort_data_to_show = df_cleaned[df_cleaned['cohort'] == selected_cohort][['tourhero_email', 'tour_id', 'follower_count', 'trip_success']]
    st.dataframe(cohort_data_to_show, use_container_width=True)
    @st.cache_data
    def convert_df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    csv = convert_df_to_csv(cohort_data_to_show)
    st.download_button(label="Download list as CSV", data=csv, file_name=f"{selected_cohort.replace(' ', '_').replace('|', '')}.csv", mime='text/csv')
else:
    st.warning("No cohorts to display based on the current filters.")

