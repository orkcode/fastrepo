import aiohttp
import asyncio
import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time

st.title("Поиск пропущенных и старых даташитов")

# Запрос поискового запроса у пользователя
search_query = st.text_input("Введите поисковый запрос:")

base_url = 'https://ruelectronics.com/search/'
params = {
    'search': search_query,
    'limit': 100,
    'showcase': 'true'
}

# Глобальные переменные для отслеживания прогресса
total_pages = 0
current_page = 0
start_time = 0


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


async def get_datasheet_url(session, product_url):
    async with session.get(product_url) as response:
        html = await response.text()
        soup = BeautifulSoup(html, 'lxml')
        datasheet_link = soup.find('a', {'class': 'tab-link'})
        if datasheet_link and 'href' in datasheet_link.attrs:
            return urljoin(base_url, datasheet_link['href'])
    return None


async def parse_page(session, html):
    global current_page
    current_page += 1

    soup = BeautifulSoup(html, 'lxml')
    results = []
    tasks = []

    for item in soup.select('.b-product-list__item'):
        article = item.find('div', {'class': 'product-model'}).text.split('Артикул производителя:')[-1].strip()
        have_datasheet = item.find('div', {'title': 'Документация'})

        if have_datasheet:
            product_link = item.find('a', {'class': 'h4'})
            if product_link and 'href' in product_link.attrs:
                product_url = urljoin(base_url, product_link['href'])
                tasks.append((article, get_datasheet_url(session, product_url)))
        else:
            results.append({'article': article, 'datasheet_status': 'отсутствует'})

    datasheet_results = await asyncio.gather(*[task[1] for task in tasks])
    for (article, datasheet_url) in zip([task[0] for task in tasks], datasheet_results):
        if datasheet_url:
            if not datasheet_url.startswith("Datasheet-"):
                results.append({'article': article, 'datasheet_status': 'устаревший'})
        else:
            results.append({'article': article, 'datasheet_status': 'отсутствует'})

    return results


async def fetch_all(session, initial_url):
    global total_pages, current_page, start_time
    all_results = []
    next_url = initial_url

    # Сначала определим общее количество страниц
    async with session.get(next_url) as response:
        html = await response.text()
        soup = BeautifulSoup(html, 'lxml')
        pagination = soup.find('ul', {'class': 'pagination'})
        if pagination:
            total_pages = len(pagination.find_all('li')) - 2  # Вычитаем кнопки "вперед" и "назад"
        else:
            total_pages = 1

    start_time = time.time()
    current_page = 0
    progress_bar = st.progress(0)
    status_text = st.empty()

    while next_url:
        async with session.get(next_url) as response:
            html = await response.text()
            page_results = await parse_page(session, html)
            all_results.extend(page_results)
            next_url = get_next_page_url(html, base_url)

        # Обновляем прогресс
        progress = current_page / total_pages
        progress_bar.progress(progress)

        elapsed_time = time.time() - start_time
        estimated_total_time = elapsed_time / progress if progress > 0 else 0
        remaining_time = estimated_total_time - elapsed_time

        status_text.text(
            f"Обработано страниц: {current_page}/{total_pages}. Осталось примерно {remaining_time:.1f} секунд.")

    progress_bar.progress(1.0)
    status_text.text("Готово!")

    return all_results


async def main():
    if search_query:
        async with aiohttp.ClientSession() as session:
            initial_url = base_url + '?' + '&'.join([f'{k}={v}' for k, v in params.items()])
            all_results = await fetch_all(session, initial_url)
            return all_results
    return []


if st.button("Запустить поиск"):
    with st.spinner("Идет поиск..."):
        results = asyncio.run(main())
        if results:
            df = pd.DataFrame(results)
            st.dataframe(df)
        else:
            st.write("Нет результатов или не удалось выполнить поиск.")
