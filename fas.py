import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode
import streamlit as st

async def fetch_page(session, url):
    async with session.get(url) as response:
        return await response.text()

async def parse_page(html):
    soup = BeautifulSoup(html, 'lxml')
    results = []
    for item in soup.select('.b-product-list__item'):
        article = item.find('div', {'class': 'product-model'}).text.split('Артикул производителя:')[-1].strip()
        have_datasheet = item.find('div', {'title': 'Документация'})
        if not have_datasheet:
            results.append(article)
    return results

def get_next_page_url(html, base_url):
    soup = BeautifulSoup(html, 'lxml')
    pagination = soup.find('ul', {'class': 'pagination'})
    if pagination:
        next_page_link = pagination.find('a', string='>')
        if next_page_link and 'href' in next_page_link.attrs:
            next_page_url = next_page_link['href']
            full_url = urljoin(base_url, next_page_url)
            return full_url
    return None

async def main(search_query):
    base_url = 'https://ruelectronics.com/search/'
    params = {
        'search': search_query,
        'limit': 100,
        'showcase': 'true'
    }

    url = f"{base_url}?{urlencode(params)}"

    async with aiohttp.ClientSession() as session:
        all_results = []
        page_number = 1

        while url:
            html = await fetch_page(session, url)
            results = await parse_page(html)
            all_results.extend(results)
            url = get_next_page_url(html, base_url)
            page_number += 1

        return all_results

st.title('Product Article Scraper')

search_query = st.text_input('Enter search query:')

if st.button('Search'):
    if search_query:
        with st.spinner('Searching...'):
            articles = asyncio.run(main(search_query))
            st.success(f'Found {len(articles)} articles without datasheets')
            st.write("Артикулы производителя:")
            st.write('\n'.join(articles))
    else:
        st.error('Please enter a search query')
