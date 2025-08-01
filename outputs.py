import csv
import datetime as dt
import logging
from pathlib import Path

from prettytable import PrettyTable

from constants import BASE_DIR, DATETIME_FORMAT


# Контроль вывода результатов парсинга.
def control_output(results, cli_args):
    output = cli_args.output
    if output == 'pretty':
        pretty_output(results)
    elif output == 'file':
        file_output(results, cli_args)
    else:
        default_output(results)


# Вывод данных в терминал построчно.
def default_output(results):
    for row in results:
        print(*row)


# Вывод данных в формате PrettyTable.
def pretty_output(results):
    table = PrettyTable()
    table.field_names = results[0]
    table.align = 'l'
    table.add_rows(results[1:])
    print(table)


# Создание директории и сохранение результатов парсинга в CSV-файл.
def file_output(results, cli_args):
    results_dir: Path = BASE_DIR / 'results'
    results_dir.mkdir(exist_ok=True)

    now_str = dt.datetime.now().strftime(DATETIME_FORMAT)
    file_path = results_dir / f'{cli_args.mode}_{now_str}.csv'

    with open(file_path, 'w', encoding='utf-8') as f:
        writer = csv.writer(f, dialect='unix')
        writer.writerows(results)

    logging.info('Файл с результатами был сохранён: %s', file_path)
