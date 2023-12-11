import regex as re
from bs4 import BeautifulSoup
from markdown import markdown
import json
import argparse
import requests
import html2text
import datetime
import time
import os


def devide_list(input_list, chunk_size):
    """
    将列表拆分为指定长度的子列表。

    参数：
    input_list: 要拆分的列表。
    chunk_size: 子列表的长度。

    返回值：
    包含子列表的列表。
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size必须大于0")

    return [input_list[i:i + chunk_size] for i in range(0, len(input_list), chunk_size)]


def get_json_data(json_data, search_pageid, search_source):
    # 遍历JSON数据并查找匹配的pageid及其索引
    for index, item in enumerate(json_data):
        if item["pageid"] == search_pageid and item["source"] == search_source:
            # 找到匹配的pageid，返回字典和索引
            return item, index

    # 如果没有找到匹配的pageid，返回None
    return None, -1


def request_error(message):
    global error_count
    if not isinstance(error_count, int):
        error_count = 0
    error_count += 1
    if error_count % 10 == 0:
        print(f"[error] {message}, 错误次数: {error_count}，等待10分钟后重试")
        time.sleep(600)  # 如果错误次数为10的倍数，等待10分钟（600秒）
    else:
        print(f"[error] {message}, 错误次数: {error_count}，等待10秒后重试")
        time.sleep(10)  # 否则等待10秒后重试

    print("重试")


def clear_text(text, cleaning_rule):
    for pattern in cleaning_rule:
        text = re.sub(pattern, "", text, count=0, flags=re.DOTALL)
    return text


def get_page(config: dict):
    '''
    获取页面内容
    :param config 配置
    :return:
    '''
    def isexclude_title(title: str, exclude_titles: list):
        for exclude_title in exclude_titles:
            if re.fullmatch(exclude_title, title):
                return True
        return False

    params = {'action': 'query', 'format': 'json', 'prop': 'info|revisions', 'curtimestamp': 1, 'indexpageids': 1}
    data = []

    # 检查是否有旧数据
    if os.path.exists(output_path):
        try:
            # 尝试解析JSON文件
            with open(output_path, 'r', encoding='UTF-8') as json_file:
                old_data = json.load(json_file)
            print(f'{output_path} 存在且是有效的JSON文件,读取')
            for item in old_data:
                if item["pageid"] in config["page_ids"] and item["source"] == config["source"] and not isexclude_title(item["title"], config["exclude_titles"]):
                    data.append(item)

        except json.JSONDecodeError as e:
            print(f'{output_path} 存在，但不是有效的JSON文件，删除。错误：P{e}')
            os.remove(output_path)

    request_times = 0
    for pageidlist_devide in devide_list(config["page_ids"], 50):

        # 请求页面基本信息
        param_pageids = '|'.join(map(str, pageidlist_devide))
        params1 = {**params, **{'pageids': param_pageids}}
        while True:
            try:
                # 发送GET请求获取页面内容
                requests_return = requests.get(config["api"], params=params1, timeout=(10, 30))
                request_times = request_times + 1
            except BaseException as e:
                request_error(f"请求获取页面信息失败。请求的api:{config['api']}，请求的参数{params1}，错误:{e}")
            else:
                if requests_return.ok:
                    requests_return: dict = requests_return.json()
                    if 'batchcomplete' in requests_return:
                        print(f"第{request_times}次请求，请求页面信息数量:{len(pageidlist_devide)}个。")
                        break
                    else:
                        print("[error]响应不完整，可能因请求页面数据量过大而导致。请尝试调整请求的数据量。")

        for pageid in pageidlist_devide:
            # 获取页面json
            rawpagejson = requests_return['query']['pages'][str(pageid)]
            # 获取页面标题
            title = rawpagejson['title']
            # 获取页面更新时间
            timestamp = rawpagejson['revisions'][0]['timestamp']
            # 获取页面版本
            version = rawpagejson['revisions'][0]['revid']

            if isexclude_title(title, config["exclude_titles"]):
                print(f"排除标题：{title}")
                continue  # 跳过获取排除标题页面

            if len(data) != 0:
                search_data, search_index = get_json_data(data, pageid, config["source"])
                if search_data is not None:
                    if title == search_data["title"] and \
                        pageid == search_data["pageid"] and \
                            version == search_data["version"] and \
                            timestamp == search_data["timestamp"] and \
                            config["source"] == search_data["source"]:  # 检查基本信息是否变化
                        for item in config["output_format"]:
                            if item not in search_data["text"]:
                                update = True  # 有更改的格式-更新
                            else:
                                update = False

                        if not update:  # 如果没有移动到json中的当前位置(末尾)
                            print(f"[标题]{title}\t[页面id]{pageid}\t[最后修改]{timestamp}\t[版本]{version}\t没有变化，重新清理文本后跳过请求&处理")
                            result = search_data["text"]
                            for i in result:
                                result[i] = clear_text(result[i], config["cleaning_rule"])
                            del data[search_index]
                            data.extend([{"title": title, "pageid": pageid, "version": version, "timestamp": timestamp, "source": config["source"], "text": result}])
                            # 以UTF-8编码格式，将data列表中的数据写入到output_path文件中
                            with open(output_path, 'w', encoding='UTF-8') as output_file:
                                json.dump(data, output_file, ensure_ascii=False, indent=4)
                            continue
                    else:
                        update = True  # update变量用于定义是否把数据更新到json中的当前位置
                else:
                    update = False  # 没有此页面的相关数据不更新直接添加
            else:
                update = False  # 没有已输出的数据

            params2 = {'curid': pageid}
            while True:
                try:
                    # 发送GET请求获取页面内容
                    response = requests.get(config["site_url"], params=params2, timeout=100)
                    request_times += 1
                except BaseException as e:
                    request_error(f"请求获取页面失败。请求的url:{config['site_url']}，请求的参数{params2}，错误:{e}")
                else:
                    print(f"当前请求&处理:[标题]{title}\t[页面id]{pageid}\t[最后修改]{timestamp}\t[版本]{version}\t[请求次数]{request_times}")
                    break
            if isinstance(config["output_format"], list):
                # 创建一个空字典，用于存储处理后的结果
                result = {}
                # 遍历output_format列表中的每一项
                for output_format_item in config["output_format"]:
                    # 调用process_html函数，处理response，并将结果存储到result字典中
                    result[output_format_item] = process_html(response.text, config, output_format_item)

            if update:  # 是否数据更新到json中的当前位置(末尾)
                del data[search_index]  # 删除原数据

            data.extend([{"title": title, "pageid": pageid, "version": version, "timestamp": timestamp, "source": config["source"], "text": result}])
            # 以UTF-8编码格式，将data列表中的数据写入到output_path文件中
            with open(output_path, 'w', encoding='UTF-8') as output_file:
                json.dump(data, output_file, ensure_ascii=False, indent=4)


def table_fix(input_text: str, cell_newline: str):
    return_text = input_text
    pattern = re.compile(r'\|[^\|\n]*\n+---\s*(?:(?:\n[^\|\n]*\|.*)+(?:(?:\n.+){1,10}\n{0,1}){0,1}(?:\n[^\|\n]*\|.*)+)+')
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


def format_conversion(html: str, output_format: str, config: dict):
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
            Markdown = h.handle(html)
            # 将Markdown格式转换为html格式
            html = markdown(Markdown)
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
    if output_format in ["markdown with links", "markdown"] and config["table_fix"]:
        text = table_fix(text, config["cell_newline"])
    return text


def process_html(text: str, config: dict, output_format: str):
    # 使用Beautiful Soup解析HTML内容
    soup = BeautifulSoup(text, 'html.parser')
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
    # 如果找到了<div>元素，则查找并删除所有<table>与<div>元素
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
    text = clear_text(text, config["cleaning_rule"])
    return text


def main():
    '''
    主函数
    '''

    def get_config():
        '''
        获取配置文件
        '''
        try:
            with open(config_path, 'r', encoding='UTF-8') as file:
                config = json.load(file)

        except FileNotFoundError:
            print(f"配置文件 '{config_path}' 未找到")
            exit(1)

        except json.JSONDecodeError:
            print(f"配置文件 '{config_path}' 解析失败")
            exit(1)

        except BaseException:
            print(f"读取配置文件 '{config_path}' 时出现未知错误")
            exit(1)

        for key in ["source", "site_url", "api", "cell_newline"]:
            if key not in config:
                print(f"配置文件 '{config_path}' 缺少 '{key}' 字段")
                exit(1)
            elif not isinstance(config[key], str):
                print(f"配置文件 '{config_path}' 的 '{key}' 字段类型错误(应为字符串)")
                exit(1)

        for key in ["output_format", "page_ids", "categories", "exclude_ids", "exclude_categories", "exclude_titles", "cleaning_rule"]:
            if key not in config:
                print(f"配置文件 '{config_path}' 缺少 '{key}' 字段")
                exit(1)
            elif not isinstance(config[key], list):
                print(f"配置文件 '{config_path}' 的 '{key}' 字段类型错误(应为列表)")
                exit(1)

        if "table_fix" not in config:
            print(f"配置文件 '{config_path}' 缺少 'table_fix' 字段")
            exit(1)
        elif not isinstance(config["table_fix"], bool):
            print(f"配置文件 '{config_path}' 的 'table_fix' 字段类型错误(应为布尔值)")
            exit(1)

        for item in config["output_format"]:
            if item.lower() not in ["plain", "markdown", "markdown with links"]:
                print("output_format的值无效")
                exit(1)

        return config

    def make_pageid_list(config):
        '''
        制作页面id列表
        '''

        def get_page_ids(api_url: str, category):
            # 设置请求参数
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'categorymembers',
                'cmtitle': f'Category:{category}',
                'cmlimit': 500
            }

            page_ids = []

            # 循环请求，直到获取全部页面
            while True:
                while True:
                    try:
                        # 发送get请求，获取响应
                        response = requests.get(api_url, params=params, timeout=100)
                        # 检查响应状态码是否正确
                        response.raise_for_status()
                        # 解析响应内容
                        data = response.json()

                    except requests.exceptions.RequestException as e:
                        # 打印错误信息
                        request_error(f"请求错误:{e}")
                    else:
                        break

                # 遍历查询结果
                for item in data['query']['categorymembers']:
                    # 将查询结果添加到page_ids列表中
                    page_ids.append(item['pageid'])

                # 如果查询结果中有continue字段，则获取continue字段的值
                if 'continue' in data:
                    # 获取continue字段的值
                    params['cmcontinue'] = data['continue']['cmcontinue']
                else:
                    # 否则，跳出循环
                    break

            # 返回page_ids列表
            return page_ids

        if config["categories"]:
            for category in config["categories"]:
                print(f"正在获取分类{category}中的所有页面id")
                # 获取指定Category的页面id
                # 调用get_page_ids函数，获取指定Category的页面id
                page_ids = get_page_ids(config["api"], category)
                # 将获取到的页面id添加到config["page_ids"]中
                config["page_ids"].extend(page_ids)
                time.sleep(1)  # 设置睡眠时间，防止被wikimedia服务器封禁IP
        else:
            print('未设置要获取的Category，跳过获取config["categories"]中的页面id')
        if config["exclude_categories"]:
            for exclude_category in config["exclude_categories"]:
                print(f"正在获取分类{exclude_category}中的所有页面id")
                # 调用get_page_ids函数，获取exclude_category中的页面id
                page_ids = get_page_ids(config["api"], exclude_category)
                # 将获取的页面id添加到config["exclude_ids"]中
                config["exclude_ids"].extend(page_ids)
                time.sleep(1)  # 设置睡眠时间，防止被wikimedia服务器封禁IP
        else:
            # 如果config["exclude_categories"]中没有元素，则输出提示信息
            print('未设置要排除的Category，跳过获取config["exclude_categories"]中的页面id')
        if config["exclude_ids"]:
            # 如果config["exclude_ids"]存在，则删除config["page_ids"]中存在于config["exclude_ids"]的元素
            config["page_ids"] = [x for x in config["page_ids"] if x not in config["exclude_ids"]]
        if not config["page_ids"]:
            # 如果config["page_ids"]为空，则打印提示信息并退出程序
            print("没有需要处理的页面id，程序结束")
            exit(1)
        # 将config["page_ids"]中的元素排序，并去重
        config["page_ids"] = sorted(list(set(config["page_ids"])))
        return config["page_ids"]

    current_time = datetime.datetime.now()
    print("mediawikiextractor\n运行开始于：", current_time)
    config = get_config()  # 获取配置
    config["page_ids"] = make_pageid_list(config)  # 制作页面id列表
    get_page(config)  # 获取页面


error_count = 0
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--config', required=True, help='Path to config file')
    parser.add_argument('--output', required=True, help='Path to output file')
    args = parser.parse_args()
    config_path = args.config
    output_path = args.output
    main()
