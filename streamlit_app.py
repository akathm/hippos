import streamlit as st
import numpy as np
import pandas as pd
import altair as alt
import requests

st.set_page_config(page_title='KYC Lookup Tool', page_icon='🗝️')
st.title('🗝️ KYC Lookup Tool')

def fetch_inquiries(api_key):
    inquiries = []
    base_url = "https://app.withpersona.com/api/v1/inquiries"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"page[limit]": 100}

    while True:
        response = requests.get(base_url, headers=headers, params=params)
        response_data = response.json()
        
        if 'data' in response_data:
            filtered_inquiries = [inquiry for inquiry in response_data['data'] if inquiry['attributes']['status'] != 'created']
            inquiries.extend(filtered_inquiries)
        if 'links' in response_data and 'next' in response_data['links']:
            next_page_url = response_data['links']['next']
            params = dict([param.split('=') for param in next_page_url.split('?')[1].split('&')])
        else:
            break

    return inquiries

def fetch_cases(api_key):
    cases = []
    base_url = "https://app.withpersona.com/api/v1/cases"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"page[limit]": 100}

    while True:
        response = requests.get(base_url, headers=headers, params=params)
        response_data = response.json()
        
        if 'data' in response_data:
            filtered_cases = [inquiry for inquiry in response_data['data'] if inquiry['attributes']['status'] != 'open']
            inquiries.extend(filtered_cases)
        if 'links' in response_data and 'next' in response_data['links']:
            next_page_url = response_data['links']['next']
            params = dict([param.split('=') for param in next_page_url.split('?')[1].split('&')])
        else:
            break

    return cases

def process_data(data):
    records = []
    for item in data['data']:
        inquiry_id = item['id']
        attributes = item['attributes']
        name_first = attributes.get('name-first', '') or ''
        name_middle = attributes.get('name-middle', '') or ''
        name_last = attributes.get('name-last', '') or ''
        name = f"{name_first} {name_middle} {name_last}".strip()
        email_address = attributes.get('email-address', '') or ''
        updated_at = attributes.get('updated-at')
        status = attributes.get('status')
        l2_address = attributes.get('fields', {}).get('l-2-address', {}).get('value', '')

        records.append({
            'inquiry_id': inquiry_id,
            'name': name,
            'email_address': email_address,
            'l2_address': l2_address,
            'updated_at': updated_at,
            'status': status
        })
    return pd.DataFrame(records)

def main():
    st.title('KYC Individuals Table')
    api_key = st.secrets["persona"]["api_key"]
    try:
        data = fetch_inquiries(api_key)
        data = fetch_cases(api_key)
        df = process_data(data)
        st.dataframe(df)
    except Exception as e:
        st.error(f"Error fetching data: {e}")

if __name__ == '__main__':
    main()



_ = """


def fetch_cases(api_key):
    cases = []
    base_url = "https://app.withpersona.com/api/v1/cases"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"page[limit]": 100}

    while True:
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code != 200:
            st.error(f"Error fetching cases: {response.status_code}")
            return []
        
        response_data = response.json()

        if 'data' in response_data:
            filtered_cases = [case for case in response_data['data'] if case['attributes']['status'] != 'open']
            cases.extend(filtered_cases)
        if 'links' in response_data and 'next' in response_data['links']:
            next_page_url = response_data['links']['next']
            params = dict([param.split('=') for param in next_page_url.split('?')[1].split('&')])
        else:
            break

    return cases


with st.expander('About this app'):
  st.markdown('**What can this app do?**')
  st.info('This app shows the use of Pandas for data wrangling, Altair for chart creation and editable dataframe for data interaction.')
  st.markdown('**How to use the app?**')
  st.warning('To engage with the app, 1. Select genres of your interest in the drop-down selection box and then 2. Select the year duration from the slider widget. As a result, this should generate an updated editable DataFrame and line plot.')
  
st.subheader('Which Movie Genre performs ($) best at the box office?')

# Load data
df = pd.read_csv('data/movies_genres_summary.csv')
df.year = df.year.astype('int')

# Input widgets
## Genres selection
genres_list = df.genre.unique()
genres_selection = st.multiselect('Select genres', genres_list, ['Action', 'Adventure', 'Biography', 'Comedy', 'Drama', 'Horror'])

## Year selection
year_list = df.year.unique()
year_selection = st.slider('Select year duration', 1986, 2006, (2000, 2016))
year_selection_list = list(np.arange(year_selection[0], year_selection[1]+1))

df_selection = df[df.genre.isin(genres_selection) & df['year'].isin(year_selection_list)]
reshaped_df = df_selection.pivot_table(index='year', columns='genre', values='gross', aggfunc='sum', fill_value=0)
reshaped_df = reshaped_df.sort_values(by='year', ascending=False)


# Display DataFrame

df_editor = st.data_editor(reshaped_df, height=212, use_container_width=True,
                            column_config={"year": st.column_config.TextColumn("Year")},
                            num_rows="dynamic")
df_chart = pd.melt(df_editor.reset_index(), id_vars='year', var_name='genre', value_name='gross')

# Display chart
chart = alt.Chart(df_chart).mark_line().encode(
            x=alt.X('year:N', title='Year'),
            y=alt.Y('gross:Q', title='Gross earnings ($)'),
            color='genre:N'
            ).properties(height=320)
st.altair_chart(chart, use_container_width=True)
"""
