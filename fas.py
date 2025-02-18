import aiohttp
import asyncio
import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from io import BytesIO

st.title("Поиск пропущенных и старых даташитов")

# Добавляем выбор между поисковым запросом и ссылкой на категорию
search_type = st.radio("Выберите тип поиска:", ("Поисковый запрос", "Ссылка на категорию"))

if search_type == "Поисковый запрос":
    search_query = st.text_input("Введите поисковый запрос:")
    base_url = 'https://ruelectronics.com/search/'
    params = {
        'search': search_query,
        'limit': 100,
        'showcase': 'true'
    }
else:
    category_url = st.text_input("Введите ссылку на категорию:")
    base_url = category_url
    params = {
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
            results.append({'артикул': article, 'статус даташита': 'отсутствует'})

    datasheet_results = await asyncio.gather(*[task[1] for task in tasks])
    for (article, datasheet_url) in zip([task[0] for task in tasks], datasheet_results):
        if datasheet_url:
            filename = str(urlparse(datasheet_url).path.split('/')[-1])
            if not filename.startswith("Datasheet-"):
                results.append({'артикул': article, 'статус даташита': 'устаревший'})
        else:
            results.append({'артикул': article, 'статус даташита': 'отсутствует'})

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
    if search_type == "Поисковый запрос" and search_query:
        initial_url = base_url + '?' + '&'.join([f'{k}={v}' for k, v in params.items()])
    elif search_type == "Ссылка на категорию" and category_url:
        initial_url = category_url
    else:
        return []

    async with aiohttp.ClientSession() as session:
        all_results = await fetch_all(session, initial_url)
        return all_results

def create_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
        workbook = writer.book
        worksheet = writer.sheets['Sheet1']

        # Автоматическая настройка ширины столбцов
        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
            worksheet.set_column(i, i, column_len)

    output.seek(0)
    return output

if st.button("Запустить поиск"):
    with st.spinner("Идет поиск..."):
        results = asyncio.run(main())
        if results:
            df = pd.DataFrame(results)
            st.dataframe(df)

            # Создаем Excel файл
            excel_file = create_excel(df)

            # Добавляем кнопку для скачивания Excel файла
            st.download_button(
                label="Скачать результаты в Excel",
                data=excel_file,
                file_name="результаты_поиска.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.write("Нет результатов или не удалось выполнить поиск.")
