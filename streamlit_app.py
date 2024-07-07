import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import requests
from io import StringIO
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title='KYC Lookup Tool', page_icon='🗝️')
st.title('🗝️ KYC Lookup Tool')

st.subheader('Project Status')
with st.expander('About the Results'):
    st.markdown('**Every project must complete KYC (or KYB for businesses) in order to receive tokens.**')
    st.info('This tool can be used to lookup project status for a specific grant round or workflow. If you do not see the expected grants round here, or you see other unexpected results, please reach out to the Grant Program Manager to correct this issue.')
    st.markdown('**What should I do if a project I\'m talking to is not in *\"cleared\"* status?**')
    st.warning('If you see a project is in *\"pending\"* status, this means that we are waiting on action from that team. Please direct them to check their emails: one or more responsible parties have been emailed with a link to complete further steps in the KYC process.')


## PERSONA-------------------------------------------------------------------

@st.cache_data(ttl=600)
def fetch_data(api_key, base_url):
    results = []
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"page[size]": 100}
    next_page_after = None

    while True:
        response = requests.get(base_url, headers=headers, params=params)
        response_data = response.json()
        results.extend(response_data.get('data', []))
        if 'data' in response_data:
            filtered_inquiries = [inquiry for inquiry in response_data['data'] if inquiry['attributes']['status'] not in ['created', 'open']]
            results.extend(filtered_inquiries)
        next_link = response_data.get('links', {}).get('next')
        if next_link:
            next_cursor = next_link.split('page%5Bafter%5D=')[-1].split('&')[0]
            params['page[after]'] = next_cursor
        else:
            break

    return results

def process_inquiries(results):
    records = []
    for item in results:
        inquiry_id = item['id']
        attributes = item.get('attributes', {})
        name_first = attributes.get('name-first', '') or ''
        name_middle = attributes.get('name-middle', '') or ''
        name_last = attributes.get('name-last', '') or ''
        name = f"{name_first} {name_middle} {name_last}".strip()
        email = attributes.get('email', '') or ''
        updated_at = attributes.get('updated-at')
        status = attributes.get('status')
        l2_address = attributes.get('fields', {}).get('l-2-address', {}).get('value', '')

        if status == 'approved':
            status = 'cleared'

        records.append({
            'inquiry_id': inquiry_id,
            'name': name,
            'email': email,
            'l2_address': l2_address,
            'updated_at': updated_at,
            'status': status
        })

    return pd.DataFrame(records)

def process_cases(results):
    records = []
    for item in results:
        case_id = item['id']
        attributes = item.get('attributes', {})
        status = attributes.get('status')
        fields = attributes.get('fields', {})
        business_name = fields.get('business-name', {}).get('value', '')
        updated_at = attributes.get('updated-at')
        
        if status == 'approved':
            status = 'cleared'

        records.append({
            'case_id': case_id,
            'name': business_name,
            'email': '',
            'l2_address': '',
            'updated_at': updated_at,
            'status': status
        })
            
    return pd.DataFrame(records)


## LEGACY DATA -------------------------------------------------------------------

def fetch_csv(owner, repo, path, access_token):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3.raw"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        csv_content = response.content.decode('utf-8')
        df = pd.read_csv(StringIO(csv_content))
        return df
    else:
        st.error(f"Failed to fetch the file from {path}: {response.status_code}")
        return None


def main():
    st.title('KYC Database')

    api_key = st.secrets["persona"]["api_key"]
    access_token = st.secrets["github"]["access_token"]
    owner = "akathm"
    repo = "the-trojans"

    if 'inquiries_data' not in st.session_state:
        st.session_state.inquiries_data = None
    if 'cases_data' not in st.session_state:
        st.session_state.cases_data = None

    refresh_button = st.button("Refresh")

    if refresh_button:
        inquiries_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/inquiries?refresh=true")
        cases_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/cases?refresh=true")
        st.session_state.inquiries_data = inquiries_data
        st.session_state.cases_data = cases_data
    else:
        if st.session_state.inquiries_data is None:
            inquiries_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/inquiries")
            st.session_state.inquiries_data = inquiries_data
        else:
            inquiries_data = st.session_state.inquiries_data

        if st.session_state.cases_data is None:
            cases_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/cases")
            st.session_state.cases_data = cases_data
        else:
            cases_data = st.session_state.cases_data

    option = st.sidebar.selectbox('Select an Option', ['Contribution Path', 'Superchain', 'Vendor', 'Grants Round'])
    search_term = st.sidebar.text_input('Enter search term (name, l2_address, or email)')

    inquiries_df = process_inquiries(inquiries_data)
    cases_df = process_cases(cases_data)

    contributors_path = "grants.contributors.csv"
    projects_path = "grants.projects.csv"
    persons_path = "legacy.persons.csv"
    businesses_path = "legacy.businesses.csv"
    form_path = "legacy.form.csv"

    contributors_df = fetch_csv(owner, repo, contributors_path, access_token)
    projects_df = fetch_csv(owner, repo, projects_path, access_token)
    persons_df = fetch_csv(owner, repo, persons_path, access_token)
    businesses_df = fetch_csv(owner, repo, businesses_path, access_token)
    form_df = fetch_csv(owner, repo, form_path, access_token)
    form_df['updated_at'] = pd.to_datetime(form_df['updated_at'])
    form_df['updated_at'] = form_df['updated_at'].dt.tz_localize('UTC')

    if persons_df is not None and 'updated_at' in persons_df.columns:
        try:
            persons_df['updated_at'] = pd.to_datetime(persons_df['updated_at'], utc=True)
        except Exception as e:
            st.error(f"Error converting 'updated_at' to datetime: {e}")
            st.stop()

    if businesses_df is not None and 'updated_at' in businesses_df.columns:
        try:
            businesses_df['updated_at'] = pd.to_datetime(businesses_df['updated_at'], utc=True)
        except Exception as e:
            st.error(f"Error converting 'updated_at' to datetime: {e}")
            st.stop()

    if inquiries_df is not None and 'updated_at' in inquiries_df.columns:
        inquiries_df['updated_at'] = pd.to_datetime(inquiries_df['updated_at'], utc=True)

    if cases_df is not None and 'updated_at' in cases_df.columns:
        cases_df['updated_at'] = pd.to_datetime(cases_df['updated_at'], utc=True)

    if persons_df is not None and inquiries_df is not None:
        current_date_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        one_year_ago_utc = current_date_utc - timedelta(days=365)

    if businesses_df is not None and businesses_df is not None:
        current_date_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        one_year_ago_utc = current_date_utc - timedelta(days=365)

    def display_results(df, columns, message, status_column='status'):
        if df.empty:
            st.write("No matching results found.")
            return
        st.write(df[columns])
        if 'updated_at' in df.columns and not df.empty:
            most_recent_status = df.loc[df['updated_at'].idxmax(), 'status']
            st.write(f"### {message.format(status=most_recent_status)}")

    def merge_addresses(df1, df2, key):
        return pd.merge(df1, df2, on=key, how='outer')

    def search_and_display(df1, df2, search_term, columns_to_display, message, status_column='status'):
        merged_df = pd.concat([df1, df2], ignore_index=True)
        merged_df['updated_at'] = pd.to_datetime(merged_df['updated_at'], errors='coerce')
        merged_df['status'].fillna('not started', inplace=True)

        filtered_df = merged_df[
            merged_df['name'].str.contains(search_term, case=False, na=False) |
            merged_df['email'].str.contains(search_term, case=False, na=False) |
            merged_df['l2_address'].str.contains(search_term, case=False, na=False)
        ]

        display_results(filtered_df, columns_to_display, message, status_column)

    if option in ['Superchain', 'Vendor']:
        search_and_display(businesses_df, cases_df, search_term, ['name', 'email', 'l2_address', 'updated_at', 'status'], 
                       "This team is {status} for KYB.")
    elif option == 'Contribution Path':
        if 'avatar' not in persons_df.columns:
            persons_df['avatar'] = ''
        if search_term:
            search_and_display(persons_df, inquiries_df, search_term, ['avatar', 'email', 'l2_address', 'updated_at', 'status'], 
                       "This contributor is {status} for KYC.")
    elif option == 'Grants Round':
        form_df['grant_id'] = form_df['grant_id'].astype(str)
        projects_df['grant_id'] = projects_df['grant_id'].astype(str)
        
        ##merged_email = pd.merge(form_df, projects_df, on='email', how='outer', indicator=True, suffixes=('_form', '_proj'))
        ##merged_l2 = pd.merge(form_df, projects_df, on='l2_address', how='outer', indicator=True, suffixes=('_form', '_proj'))
        ##merged_all = pd.concat([merged_email, merged_l2], ignore_index=True).drop_duplicates()
        merged_email = pd.merge(form_df, projects_df, on='email', how='outer', suffixes=('_form', '_proj'))
        merged_l2 = pd.merge(form_df, projects_df, on='l2_address', how='outer', suffixes=('_form', '_proj'))
        merged_all = pd.concat([merged_email, merged_l2], ignore_index=True).drop_duplicates()

        merged_all['l2_address'] = merged_all['l2_address_form'].combine_first(merged_all['l2_address_proj'])
        merged_all.drop(columns=['l2_address_form', 'l2_address_proj'], inplace=True)
        merged_all['status'] = merged_all['status_form']
        ##merged_all['status'] = pd.to_numeric(merged_all['status'], errors='coerce')
        ##merged_all['status'] = merged_all['status_form'].combine_first(merged_all['status_proj'])
    
        required_columns = ['project_name', 'email', 'l2_address', 'round_id', 'grant_id', 'status']
        for col in required_columns:
            if col not in merged_all.columns:
                merged_all[col] = ''

        merged_all = merged_all[~(merged_all['email'].isnull() & merged_all['l2_address'].isnull())]
    
        if search_term:
            filtered_df = merged_all[
                merged_all['project_name'].str.contains(search_term, case=False, na=False) |
                merged_all['email'].str.contains(search_term, case=False, na=False) |
                merged_all['l2_address'].str.contains(search_term, case=False, na=False)
            ]
    
        else:
            filtered_df = pd.DataFrame()
            st.write('*Use the search tool on the left hand side to input an L2 address, project name, or admin email* 💬')
            

        display_results(filtered_df, ['project_name', 'email', 'l2_address', 'round_id', 'grant_id', 'status'], 
                "This project is {status} for KYC.")



## Contributors-------------------------------------------------------

    st.header('______________________________________')
    st.header('Individual Contributors')

    all_persons_df = pd.concat([persons_df, inquiries_df], ignore_index=True)
    all_persons_df['status'] = all_persons_df.sort_values('updated_at').groupby('email')['status'].transform('last')
    
    all_persons_df.loc[(all_persons_df['status'] == 'cleared') & (all_persons_df['updated_at'] < one_year_ago_utc), 'status'] = 'expired'
    merged_df = contributors_df.merge(all_persons_df[['email', 'status']], on='email', how='left')
    merged_df['status'] = merged_df['status'].fillna('not started')
    merged_df = merged_df[~(merged_df['email'].isnull() & merged_df['contributor_id'].isnull())]
    merged_df.drop_duplicates(subset=['email', 'round_id', 'op_amt'], inplace=True)

##    all_persons_df = pd.concat([persons_df, inquiries_df], ignore_index=True)
##    all_persons_df['status'] = all_persons_df.sort_values('updated_at').groupby('email')['status'].transform('last')

##    all_persons_df.loc[(all_persons_df['status'] == 'cleared') & (all_persons_df['updated_at'] < one_year_ago_utc), 'status'] = 'expired'

##    merged_df = contributors_df.merge(all_persons_df[['email', 'status']], on='email', how='left')
##    merged_df['status'].fillna('not started', inplace=True)
##    merged_df = merged_df[~(merged_df['email'].isnull() & merged_df['contributor_id'].isnull())]
##    merged_df.drop_duplicates(subset=['email', 'round_id', 'op_amt'], inplace=True)

    projects_list = ['Ambassadors', 'NumbaNERDs', 'SupportNERDs', 'Translators', 'Badgeholders', 'WLTA', 'WLTA Judge']
    projects_selection = st.multiselect('Select the Contributor Path', projects_list + ['Other'], ['Ambassadors', 'NumbaNERDs', 'SupportNERDs', 'Translators', 'Badgeholders', 'WLTA', 'WLTA Judge', 'Other'])

    if 'Other' in projects_selection:
        filtered_df = merged_df[~merged_df['project_name'].isin(projects_list)]
        if set(projects_selection) - {'Other'}:
            filtered_df = pd.concat([filtered_df, merged_df[merged_df['project_name'].isin(set(projects_selection) - {'Other'})]])
    else:
        filtered_df = merged_df[merged_df['project_name'].isin(projects_selection)] if projects_selection else merged_df
            
    st.write(filtered_df)
        
## Grants Rounds--------------------------------------------
        
    st.header('Active Grants Rounds')
    
    url = "https://api.github.com/repos/akathm/the-trojans/contents/grants.projects.csv"

    headers = {
        "Authorization": f"token {st.secrets['github']['access_token']}",
        "Accept": "application/vnd.github.v3.raw"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        csv_content = response.content.decode('utf-8')
        df = pd.read_csv(StringIO(csv_content))
        rounds_list = df.round_id.unique()
        rounds_selection = st.multiselect('Select the Grant Round', list(rounds_list), ['rpgf2', 'rpgf3', 'season5-builders-19', 'season5-growth-19'])
        
        if 'Other' in rounds_selection:
            filtered_df = df[~df['round_id'].isin(['rpgf2', 'rpgf3', 'season5-builders-19', 'season5-growth-19'])]
            if set(rounds_selection) - {'Other'}:
                filtered_df = pd.concat([filtered_df, df[df['round_id'].isin(set(rounds_selection) - {'Other'})]])
        else:
            filtered_df = df[df['round_id'].isin(rounds_selection)] if rounds_selection else df
            
        st.write(filtered_df)
    else:
        st.error(f"Failed to fetch the file: {response.status_code}")



if __name__ == '__main__':
    main()
