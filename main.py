import logging
import re
from pathlib import Path
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import MAIN_DOC_URL
from outputs import control_output
from utils import find_tag, get_response


def whats_new(session):
    # Вместо константы WHATS_NEW_URL, используйте переменную whats_new_url.
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    # Загрузка веб-страницы с кешированием через вспомогательную функцию.
    response = get_response(session, whats_new_url)
    if response is None:
        return
    # Создание «супа».
    soup = BeautifulSoup(response.text, features='lxml')

    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})

    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})

    # Нужны все теги, поэтому используется метод find_all().
    sections_by_python = div_with_ul.find_all(
        'li',
        attrs={'class': 'toctree-l1'},
    )

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    for section in tqdm(sections_by_python):
        version_a_tag = section.find('a')
        version_link = urljoin(whats_new_url, version_a_tag['href'])
        # Загрузка страницы версии через get_response().
        response = get_response(session, version_link)
        if response is None:
            # Если страница не загрузится, переходим к следующей ссылке.
            continue
        soup = BeautifulSoup(response.text, 'lxml')
        # Поиск заголовка и описания через find_tag().
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append((version_link, h1.text, dl_text))

    return results


def latest_versions(session):
    # Загрузка основной документации через get_response().
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')
    # Поиск боковой панели через find_tag().
    sidebar = find_tag(soup, 'div', attrs={'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Не найден список c версиями Python')

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append((link, version, status))

    return results


def download(session):
    # Вместо константы DOWNLOADS_URL, используйте переменную downloads_url.
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')

    response = get_response(session, downloads_url)
    if response is None:
        return
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'lxml')

    main_tag = find_tag(soup, 'div', attrs={'role': 'main'})
    table_tag = find_tag(main_tag, 'table', attrs={'class': 'docutils'})

    pdf_a4_tag = find_tag(
        table_tag,
        'a',
        attrs={'href': re.compile(r'.+pdf-a4\.zip$')},
    )

    archive_url = urljoin(downloads_url, pdf_a4_tag['href'])

    filename = archive_url.split('/')[-1]
    base_dir = Path(__file__).parent
    downloads_dir = base_dir / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename

    print(f'Скачиваю {archive_url} → {archive_path} …')
    resp = session.get(archive_url)
    resp.raise_for_status()

    with open(archive_path, 'wb') as file:
        file.write(resp.content)

    print('Документация успешно загружена!')
    logging.info('Архив был загружен и сохранён: %s', archive_path)


def pep(session):
    # 1. Стартовая страница со списком всех PEP.
    peps_url = 'https://peps.python.org/numerical/'
    response = get_response(session, peps_url)
    if response is None:
        return

    soup = BeautifulSoup(response.text, 'lxml')

    numerated_peps = find_tag(soup, 'section', attrs={'id': 'numerical-index'})
    pep_links = [
        a
        for a in numerated_peps.find_all('a', href=re.compile(r'pep-\d{4}/'))
        if a.text.isdigit()
    ]

    EXPECTED_STATUS = {
        'A': ('Active', 'Accepted'),
        'D': ('Deferred',),
        'F': ('Final', 'April Fool!'),
        'P': ('Provisional',),
        'R': ('Rejected', 'April Fool!'),
        'S': ('Superseded',),
        'W': ('Withdrawn',),
        '': ('Draft', 'Active'),
    }

    status_counter = {}
    mismatches = []

    for link_tag in tqdm(pep_links):
        if link_tag.text.strip() == '0':
            continue

        row_tr = link_tag.find_parent('tr')
        abbr_tag = row_tr.find('abbr')

        if abbr_tag:
            abbr = abbr_tag.text.strip()
            preview_status = abbr[1] if len(abbr) == 2 else ''
        else:
            preview_status = ''

        root_url = 'https://peps.python.org/'
        link = urljoin(root_url, link_tag['href'])

        card_response = get_response(session, link)
        if card_response is None:
            continue
        card_soup = BeautifulSoup(card_response.text, 'lxml')

        status_tag = None
        for tag in card_soup.find_all(['dt', 'th']):
            if 'Status' in tag.get_text():
                status_tag = tag
                break
        if status_tag is None:
            continue
        actual_status = (
            status_tag.find_next_sibling(['dd', 'td']).get_text(strip=True)
        )

        if actual_status not in EXPECTED_STATUS.get(preview_status, ()):
            mismatches.append(
                (link, actual_status, EXPECTED_STATUS.get(preview_status)),
            )

        status_counter[actual_status] = (
            status_counter.get(actual_status, 0) + 1
        )

    if mismatches:
        logging.info('Несовпадающие статусы:')
        for url, real, expected in mismatches:
            logging.info(
                '%s\nСтатус в карточке: %s\nОжидаемые статусы: %s',
                url,
                real,
                expected,
            )

    results = [('Статус', 'Количество')]
    for status, count in sorted(status_counter.items()):
        results.append((status, count))
    results.append(('Total', sum(status_counter.values())))

    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')

    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info('Аргументы командной строки: %s', args)

    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
