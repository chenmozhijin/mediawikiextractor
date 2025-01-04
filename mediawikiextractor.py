# SPDX-FileCopyrightText: Copyright (C) 2024 沉默の金 <cmzj@cmzj.org>
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from urllib.parse import urlparse

import regex as re
import requests
from bs4 import BeautifulSoup
from html2text import html2text
from markdown import markdown as markdown2html

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 "
           "Safari/537.36 Edg/120.0.0.0"}


def load_config(config_path: str) -> dict:
    """
    加载配置文件
    :param config_path: 配置文件路径
    :return: 配置文件内容
    """
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        logging.exception("配置文件不存在")
    except json.JSONDecodeError:
        logging.exception("配置文件格式错误")
    if not isinstance(config, dict):
        logging.exception("配置文件格式错误")

    for content_type, keys in {str: ["source", "index_url"],
                               bool: ["table_fix", "excludeExistingPages"],
                               list: ["output_format", "page_titles", "categories", "exclude_categories", "exclude_titles", "cleaning_rule"]}.items():
        for key in keys:
            if key not in config or not isinstance(config[key], content_type):
                logging.error(f"配置文件格式错误，关键字：{key}缺失或类型错误")

    if config["table_fix"] is True and ("cell_newline" not in config or not isinstance(config["cell_newline"], str)):
        logging.error("配置文件错误，table_fix启用时cell_newline必须为字符串")
    return config


def request_page(url: str, params: dict | None = None) -> str | int:
    if params is None:
        params = {}
    while True:
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 429:
                logging.warning("请求过于频繁，等待10秒后重试")
                time.sleep(10)
                continue
            if response.status_code == 404:
                return 404
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logging.warning("请求超时，等待5秒后重试")
            time.sleep(5)
        except requests.exceptions.RequestException:
            logging.warning("请求异常，等待5秒后重试")
            time.sleep(5)
        else:
            return response.text


def process_category(config: dict) -> list[str]:
    """
    处理分类
    :param categories: 分类列表
    :return: 处理后的页面url列表
    """
    page_titles: list[str] = []
    categories: list[str] = sorted(set(config["categories"]))
    index_url = config["index_url"]
    parsed_url = urlparse(index_url)
    site_domain = parsed_url.netloc
    i = 0
    while i < len(categories):
        category = categories[i]
        nextpage_url = None
        while True:
            if nextpage_url is None:
                page_html = request_page(index_url, {"title": f"Category:{category}"})
            else:
                page_html = request_page(nextpage_url)
            if page_html == 404:
                logging.error(f"未找到 {category} 分类")
                success = False
                break
            soup = BeautifulSoup(page_html, "lxml")
            nextpage_url = None
            mw_categories = soup.find_all("div", "mw-category")
            for mw_category in mw_categories:
                for li in mw_category.find_all("li"):
                    a = li.find("a")
                    if a and "title" in a.attrs:
                        if a.attrs["title"].startswith("Category:"):
                            if a.attrs["title"].replace("Category:", "") not in categories:
                                categories.append(a.attrs["title"].replace("Category:", ""))
                        else:
                            page_titles.append(a.attrs["title"])
            for a in soup.find_all("a"):
                if (a.attrs.get("title") == f"Category:{category}"
                        and "pagefrom" in a.attrs.get("href", "")):
                    nextpage_url = f"https://{site_domain}{a['href']}"
                    break
            if nextpage_url is None:
                success = True
                break
        if success:
            logging.info(f"[{i + 1}/{len(categories)}]获取 {category} 分类的页面列表成功")
        i += 1

    return page_titles


def get_info(html: str, index_url: str, title: str) -> dict:
    info = {"pageid": None, "revision_id": None}
    get_info_pattern = re.compile(r"<!-- Saved in parser cache with key .*?idhash:(\d+)-.*?revision id (\d+).*\n -->")
    find_results = re.findall(get_info_pattern, html)
    if find_results:
        info = {"pageid": int(find_results[0][0]), "revision_id": int(find_results[0][1])}

    soup = BeautifulSoup(html, "lxml")
    if info == {"pageid": None, "revision_id": None}:
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and '"wgArticleId":' in script.string and '"wgRevisionId":' in script.string:
                pageid = re.findall(r'"wgArticleId":(\d+),', script.string)
                revid = re.findall(r'"wgRevisionId":(\d+),', script.string)
                if pageid and revid:
                    info = {"pageid": int(pageid[0]), "revision_id": int(revid[0])}
                    break

    if info == {"pageid": None, "revision_id": None}:
        index_html = request_page(index_url, {"title": title, "action": 'info'})
        soup = BeautifulSoup(index_html, "lxml")
        mw_pageinfo_article_id = soup.find('tr', {'id': 'mw-pageinfo-article-id'})
        if mw_pageinfo_article_id:
            for td in mw_pageinfo_article_id.find_all('td'):
                if td.string and td.string.isdigit():
                    info.update({"pageid": int(td.string)})
                    break
        mw_pageinfo_lasttime = soup.find('tr', {'id': 'mw-pageinfo-lasttime'})
        if mw_pageinfo_lasttime:
            for a in mw_pageinfo_lasttime.find_all('a'):
                if "oldid=" in a.attrs.get('href', ""):
                    info.update({"revision_id": int(a.attrs['href'].split("oldid=")[1])})

    return info


def get_categories(html: str) -> list:
    normal_catlinks = []
    soup = BeautifulSoup(html, "lxml")
    mw_normal_catlinkss = soup.find_all("div", {"id": "mw-normal-catlinks", "class": "mw-normal-catlinks"})
    if mw_normal_catlinkss:
        for mw_normal_catlinks in mw_normal_catlinkss:
            normal_catlinks.extend([a.attrs["title"] for a in mw_normal_catlinks.find_all("a") if "title" in a.attrs and a.attrs["title"].startswith("Category:")])
    else:
        scripts = soup.find_all("script")
        catlinks = None
        for script in scripts:
            if script.string and '"catlinks":' in script.string:
                catlinks = re.findall(r'("catlinks":".*?",)', script.string)
                if catlinks:
                    try:  # noqa: SIM105
                        catlinks = json.loads("{" + catlinks[0][:-1] + "}")
                    except json.JSONDecodeError:
                        pass
                    break
        if not catlinks:
            return []
        catlinks_soup = BeautifulSoup(catlinks['catlinks'], "lxml")
        mw_normal_catlinks = catlinks_soup.find("div", {"class": "mw-normal-catlinks"})
        if mw_normal_catlinks:
            normal_catlinks = [a.attrs["title"] for a in mw_normal_catlinks.find_all("a") if "title" in a.attrs and a.attrs["title"].startswith("Category:")]

    pattern = re.compile(r'^Category:')
    if normal_catlinks:
        return [pattern.sub("", catlink) for catlink in normal_catlinks]
    return []


def table_fix(input_text: str, cell_newline: str) -> str:
    return_text = input_text
    pattern = re.compile(r'\|?[^\|\n]*\n+---\s*(?:(?:\n[^\|\n]*\|.*)*(?:(?:\n.+){1,10}\n{0,1}){0,1}(?:\n[^\|\n]*\|.*)+)+')
    tables_to_process = pattern.findall(input_text)
    for table_to_process in tables_to_process:
        original_table = table_to_process
        table_lines = table_to_process.split("\n")  # 将字符串拆分为行
        table_header = table_lines[:2]
        table_content = table_lines[2:]
        column_count = table_content[0].count('|') + 1
        table_header[0] += '|' * column_count
        table_header[1] = '|---' * column_count + '|'
        c_lines_wo_vertical_bar = 0
        for index, line in enumerate(table_content):
            if re.fullmatch(r'[-\|\s]+', line):
                table_content[index] = ""
            vertical_bar_count = line.count('|')
            if vertical_bar_count > column_count - 1:
                table_content[index] = line[::-1].replace("|", "", vertical_bar_count - column_count + 1).strip()[::-1]  # 删除最后一个"|"
            if vertical_bar_count == 0:
                c_lines_wo_vertical_bar += 1
                table_content[index - c_lines_wo_vertical_bar] = table_content[index - c_lines_wo_vertical_bar] + cell_newline + line
                table_content[index] = ""
            else:
                c_lines_wo_vertical_bar = 0
        table_content = [line for line in table_content if line.strip() != '']
        for index, line in enumerate(table_content):
            table_content[index] = "|" + line + "|"
        result_table = '\n'.join(table_header + table_content)
        return_text = return_text.replace(original_table, result_table)
    return return_text


def fix_md037(md: str) -> str:
    pattern = re.compile(r'([\~\*\_]{1,2})[ \t\f\v]*(.*?)[ \t\f\v]*?\1')
    return re.sub(pattern, r'\1\2\1', md)


def format_conversion(html: str, output_format: str, config: dict) -> str:
    # 创建一个HTML2Text对象
    h = html2text.HTML2Text()
    # 根据格式忽略转换部分内容
    match output_format:
        case "plain":
            # 忽略转换链接
            h.ignore_links = True
            # 忽略转换图片
            h.ignore_images = True
            # 忽略转换表格
            h.ignore_tables = True
            # 忽略转换强调符号
            h.ignore_emphasis = True
            # 将div_element转换为Markdown格式
            markdown = h.handle(html)
            # 将Markdown格式转换为html格式
            html = markdown2html(markdown)
            # 将html格式转换为文本格式
            text = ''.join(BeautifulSoup(html, features="lxml").findAll(string=True))
        case "markdown":
            # 忽略转换链接
            h.ignore_links = True
            # 忽略转换图片
            h.ignore_images = True
            # 将div_element转换为Markdown格式
            text = h.handle(html)
        case "markdown with links":
            # 不忽略转换链接
            h.ignore_links = False
            # 不忽略转换图片
            h.ignore_images = False
            # 将div_element转换为Markdown格式
            text = h.handle(html)
        case "html":
            text = html
        case _:
            msg = "Invalid output format"
            raise ValueError(msg)
    if output_format in ["markdown with links", "markdown"] and "table_fix" in config:
        text = table_fix(text, config["cell_newline"])
    return text


def process_html(text: str, config: dict, output_format: str) -> str:
    # 使用Beautiful Soup解析HTML内容
    soup = BeautifulSoup(text, "lxml")
    # 查找具有特定类名的<div>元素
    div_elements = soup.find_all('div', class_='mw-parser-output')
    max_div = None
    max_text_length = 0
    for div_element in div_elements:
        text = div_element.get_text()  # 获取<div>元素的文本内容
        text_length = len(text)
        if text_length >= max_text_length:
            max_div = div_element
            max_text_length = text_length
    div_element = max_div
    # 如果找到了<div>元素,则查找并删除所有<table>与<div>元素
    if div_element:
        elements_to_remove = []
        for i in ["navbox", "noprint"]:  # 去除导航模板
            elements_to_remove += div_element.find_all(['table', 'div'], class_=f"{i}")
        elements_to_remove += div_element.find_all('span', class_="textToggleDisplay hidden textToggleDisplay-off")
        if output_format != "markdown with links":
            elements_to_remove += div_element.find_all('li', class_="gallerybox")
            elements_to_remove += div_element.find_all(['td', 'tr'], class_="infobox-image-container")
            elements_to_remove += div_element.find_all('div', class_="thumbinner")
        for element in elements_to_remove:
            element.extract()  # 从DOM中移除<table>与<div>元素

    html = div_element.prettify()

    text = format_conversion(html, output_format, config)

    # 清理文本
    clear_pattern = re.compile("|".join(config["cleaning_rule"]), flags=re.DOTALL)
    return re.sub(clear_pattern, "", text, count=0)


def main(args: argparse.Namespace) -> int:
    """
    :param args: 参数
    :return: 返回值
    """
    start_run_time = time.time()
    try:
        config_path: str = args.config
        output_path: str = args.output
    except AttributeError:
        logging.exception("缺少必要参数")
        return 1
    if not isinstance(config_path, str) and not isinstance(output_path, str):
        logging.error("错误的参数类型")
        return 1
    config: dict = load_config(config_path)

    page_titles = process_category(config)
    page_titles = sorted(set(page_titles + config["page_titles"]))

    exclude_title_pattern = re.compile("|".join(config["exclude_titles"]))
    for page_title in page_titles:  # 移除排除的标题
        if re.fullmatch(exclude_title_pattern, page_title) or page_title.endswith("/style.css"):
            page_titles.remove(page_title)

    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as output_file:
            try:
                data: list[dict] = json.load(output_file)
            except Exception:
                data: list[dict] = []
    else:
        data: list[dict] = []

    start_process_page_time = time.time()

    def process_page(page_title: str) -> None:
        logging.info(f"[{i + 1}/{len(page_titles)}]正在处理页面：{page_title}  ({(time.time() - start_process_page_time) / 60:.2f}s/page)")

        page_dict = {"title": page_title, "source": config["source"]}

        same_title_item = [item for item in data if item["title"] == page_title and item["source"] == config["source"]]
        if config["excludeExistingPages"] and same_title_item:
            return

        page_html = request_page(config["index_url"], {"title": page_title})
        if page_html == 404:
            logging.warning(f"页面 {page_title} 不存在")
            return

        page_categories = get_categories(page_html)
        if page_categories == []:
            logging.warning(f"页面 {page_title} 没有获取到分类")
        for page_category in page_categories:
            if page_category in config["exclude_categories"]:
                logging.info(f"页面 {page_title} 位于排除的分类 {page_category} 下，跳过")
                continue

        page_dict.update(get_info(page_html, config["index_url"], page_title))

        page_dict["data"] = {}
        for output_format in config["output_format"]:
            page_dict["data"][output_format] = process_html(page_html, config, output_format)

        if same_title_item:
            data.remove(same_title_item[0])
        data.append(page_dict)
        with open(output_path, 'w', encoding="utf-8") as output_file:
            json.dump(data, output_file, ensure_ascii=False, indent=4)

    for i, page_title in enumerate(page_titles):
        try:
            process_page(page_title)
        except Exception:
            logging.exception(f"处理页面 {page_title} 时发生错误")
            continue

    logging.info(f"所有页面处理完毕,耗时: {time.time() - start_run_time}秒({(time.time() - start_process_page_time) / 60:.2f}s/page)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s]%(message)s")
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--config', required=True, help='Path to config file')
    parser.add_argument('--output', required=True, help='Path to output file')
    args = parser.parse_args()
    sys.exit(main(args))
