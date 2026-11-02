import json
import os
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import Error as BrowserError, sync_playwright


def main():
    base = os.getenv('DOCS_URL', 'http://docs:8080')
    for attempt in range(60):
        try:
            with urlopen(base + '/manifest.json', timeout=5) as response:
                manifest = json.load(response)
            break
        except Exception:
            if attempt == 59:
                raise
            time.sleep(2)
    key = 'model.fraud_analytics.mart_daily_state_metrics'
    if key not in manifest['nodes']:
        raise RuntimeError('В dbt Docs нет ожидаемой модели')
    url = base + '/#!/model/' + key
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/usr/bin/chromium',
                                             args=['--no-sandbox','--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width':1600,'height':1100}, device_scale_factor=1)
        page.goto(url, wait_until='networkidle', timeout=120000)
        page.wait_for_function("document.body.innerText.includes('p95_amount') && document.body.innerText.includes('mart_daily_state_metrics')", timeout=90000)
        page.screenshot(path='evidence/dbt-docs.png', full_page=True)
        title = page.title()
        page = browser.new_page(viewport={'width':1800,'height':1100}, device_scale_factor=1)
        page.goto(base + '/#!/overview?g_v=1', wait_until='networkidle', timeout=120000)
        page.locator('#cy').wait_for(state='visible', timeout=90000)
        page.wait_for_function("window.graph && window.graph.nodes().length >= 8", timeout=90000)
        nodes = page.evaluate("window.graph.nodes().map(node => node.id())")
        expected = [node for node in manifest['nodes'] if node.startswith('model.fraud_analytics.')]
        if not all(node in nodes for node in expected):
            raise RuntimeError('На графе документации отсутствует одна из моделей')
        page.evaluate('() => { window.graph.fit(35); }')
        page.wait_for_timeout(1500)
        page.screenshot(path='evidence/dbt-dag.png', full_page=True)
        browser.close()
    Path('evidence/screenshot.json').write_text(json.dumps({'url':url, 'title':title,
        'model':key, 'contains_p95_column':True, 'graph_nodes':nodes}, indent=2)+'\n')
    print('Скриншот dbt Docs: evidence/dbt-docs.png')


if __name__ == '__main__':
    for capture_attempt in range(3):
        try:
            main()
            break
        except BrowserError:
            if capture_attempt == 2:
                raise
            print('Повтор загрузки страницы документации.', flush=True)
            time.sleep(2)
