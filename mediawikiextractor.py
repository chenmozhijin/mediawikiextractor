import regex as re
from bs4 import BeautifulSoup
from markdown import markdown
import json
import argparse
import requests
import sys
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


def get_config():
    try:
        with open(config_path, 'r', encoding='UTF-8') as file:
            config_data = json.load(file)
        pageid_list = config_data.get("page_ids")
        api_url = config_data.get("api")
        source = config_data.get("source")
        categories = config_data.get("categories")
        exclude_ids = config_data.get("exclude_ids")
        exclude_categories = config_data.get("exclude_categories")
        cleaning_rule = config_data.get("cleaning_rule")
        exclude_titles = config_data.get("exclude_titles")
        site_url = config_data.get("site_url")
        output_format = config_data.get("output_format")
    except FileNotFoundError:
        print(f"配置文件 '{config_path}' 未找到")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"配置文件 '{config_path}' 解析失败")
        sys.exit(1)
    except BaseException:
        print(f"读取配置文件 '{config_path}' 时出现未知错误")
        sys.exit(1)
    if isinstance(output_format, str):
        if output_format.lower() not in ["plain", "markdown", "markdown with links"]:
            print("output_format的值无效")
            sys.exit(1)
    else:
        for item in output_format:
            if item.lower() not in ["plain", "markdown", "markdown with links"]:
                print("output_format的值无效")
                sys.exit(1)

    return pageid_list, api_url, source, categories, exclude_ids, exclude_categories, cleaning_rule, exclude_titles, site_url, output_format


def get_page_ids(api_url, category):
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
                print(f"请求错误:{e},十秒后重试")
                # 等待10秒
                time.sleep(10)
                print("重试")
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
        text = re.sub(pattern, r"", text, count=0, flags=re.DOTALL)
    return text


def get_page(pageid_list, api_url, source, cleaning_rule, exclude_titles, site_url, output_format):
    '''
    获取页面内容
    :param pageid_list: 页面id列表
    :param api_url: api请求地址
    :param site_url: mediawiki网站index.php地址
    :param source: 来源
    :param cleaning_rule: 清理规则
    :param exclude_titles: 不需要的页面的标题
    :output_format: 输出的格式
    :return:
    '''
    params = {'action': 'query', 'format': 'json', 'prop': 'info|revisions', 'curtimestamp': 1, 'indexpageids': 1}
    data = []
    if os.path.exists(output_path):
        try:
            # 尝试解析JSON文件
            with open(output_path, 'r', encoding='UTF-8') as json_file:
                data = json.load(json_file)
            print(f'{output_path} 存在且是有效的JSON文件,读取')
            new_data = []
            for item in data:
                if item["pageid"] in pageid_list and item["source"] == source:
                    new_data.append(item)

            data = new_data

        except json.JSONDecodeError as e:
            print(f'{output_path} 存在，但不是有效的JSON文件，删除。错误：P{e}')
            os.remove(output_path)

    request_times = 0
    for pageidlist_devide in devide_list(pageid_list, 50):
        param_pageids = '|'.join(map(str, pageidlist_devide))
        params1 = {**params, **{'pageids': param_pageids}}
        while True:
            try:
                # 发送GET请求获取页面内容
                requests_return = requests.get(api_url, params=params1, timeout=(10, 30))
                request_times = request_times + 1
            except BaseException as e:
                request_error(f"请求获取页面信息失败。请求的api:{api_url}，请求的参数{params1}，错误:{e}")
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
            found_match = False  # 初始化标志变量
            # 使用re模块的search函数来查找匹配
            for exclude_title in exclude_titles:
                match = re.search(exclude_title, title)  # 排除标题
                # 如果找到匹配，则match对象不为None
                if match:
                    found_match = True  # 设置标志为True
                    print(f"排除标题：{title}")
                    for index, item in enumerate(data):
                        if item["title"] == title and item["source"] == source:
                            # 搜索排除标题的字典并删除
                            del data[index]
            if found_match:
                continue  # 跳过获取排除标题页面

            if len(data) != 0:
                search_data, search_index = get_json_data(data, pageid, source)
                if search_data is not None:
                    if title == search_data["title"] and \
                        pageid == search_data["pageid"] and \
                            version == search_data["version"] and \
                            timestamp == search_data["timestamp"] and \
                            source == search_data["source"]:  # 检查基本信息是否变化
                        if isinstance(output_format, str):  # 检查格式是否为要求的格式
                            if isinstance(search_data["text"], str):
                                update = False
                            else:
                                update = True  # 无法判断格式-更新
                        else:
                            for item in output_format:
                                if item not in search_data["text"]:
                                    update = True  # 有更改的格式-更新
                                else:
                                    update = False

                        if not update:  # 如果没有移动到json中的当前位置(末尾)
                            print(f"[标题]{title}\t[页面id]{pageid}\t[最后修改]{timestamp}\t[版本]{version}\t没有变化，重新清理文本后跳过请求&处理")
                            result = search_data["text"]
                            for i in result:
                                result[i] = clear_text(result[i], cleaning_rule)
                            del data[search_index]
                            data.extend([{"title": title, "pageid": pageid, "version": version, "timestamp": timestamp, "source": source, "text": result}])
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
                    response = requests.get(site_url, params=params2, timeout=100)
                    request_times = request_times + 1
                except BaseException as e:
                    request_error(f"请求获取页面失败。请求的url:{api_url}，请求的参数{params2}，错误:{e}")
                else:
                    print(f"当前请求&处理:[标题]{title}\t[页面id]{pageid}\t[最后修改]{timestamp}\t[版本]{version}\t[请求次数]{request_times}")
                    break
            if isinstance(output_format, list):
                # 创建一个空字典，用于存储处理后的结果
                result = {}
                # 遍历output_format列表中的每一项
                for output_format_item in output_format:
                    # 调用process_html函数，处理response，并将结果存储到result字典中
                    result[output_format_item] = process_html(response.text, cleaning_rule, output_format_item)
            else:
                # 调用process_html函数，处理response，并将结果存储到result中
                result = process_html(response.text, cleaning_rule, output_format)
                # 将title、pageid、version、timestamp、source和result添加到data列表中

            if update:  # 是否数据更新到json中的当前位置(末尾)
                del data[search_index]

            data.extend([{"title": title, "pageid": pageid, "version": version, "timestamp": timestamp, "source": source, "text": result}])
            # 以UTF-8编码格式，将data列表中的数据写入到output_path文件中
            with open(output_path, 'w', encoding='UTF-8') as output_file:
                json.dump(data, output_file, ensure_ascii=False, indent=4)


def process_html(text, cleaning_rule, output_format):
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
            Markdown = h.handle(div_element.prettify())
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
            text = h.handle(div_element.prettify())
        case "markdown with links":
            # 不忽略转换链接
            h.ignore_links = False
            # 不忽略转换图片
            h.ignore_images = False
            # 将div_element转换为Markdown格式
            text = h.handle(div_element.prettify())

    # 清理文本
    text = clear_text(text, cleaning_rule)
    return text


def main():
    '''
    主函数，用于获取页面id，并获取页面信息
    '''
    current_time = datetime.datetime.now()
    print("mediawikiextractor\n运行开始于：", current_time)
    pageid_list, api_url, source, categories, exclude_ids, exclude_categories, cleaning_rule, exclude_titles, site_url, output_format = get_config()
    if categories:
        for category in categories:
            print(f"正在获取分类{category}中的所有页面id")
            # 获取指定Category的页面id
            page_ids = get_page_ids(api_url, category)
            # 将获取到的页面id添加到pageid_list中
            pageid_list.extend(page_ids)
            time.sleep(1)  # 设置睡眠时间，防止被wikimedia服务器封禁IP
    else:
        print("未设置要获取的Category，跳过获取categories中的页面id")
    if exclude_categories:
        for exclude_category in exclude_categories:
            print(f"正在获取分类{exclude_category}中的所有页面id")
            # 调用get_page_ids函数，获取exclude_category中的页面id
            page_ids = get_page_ids(api_url, exclude_category)
            # 将获取的页面id添加到exclude_ids中
            exclude_ids.extend(page_ids)
            time.sleep(1)  # 设置睡眠时间，防止被wikimedia服务器封禁IP
    else:
        # 如果exclude_categories中没有元素，则输出提示信息
        print("未设置要排除的Category，跳过获取exclude_categories中的页面id")
    if exclude_ids:
        # 如果exclude_ids存在，则删除pageid_list中存在于exclude_ids的元素
        pageid_list = [x for x in pageid_list if x not in exclude_ids]
    if not pageid_list:
        # 如果pageid_list为空，则打印提示信息并退出程序
        print("没有需要处理的页面id，程序结束")
        sys.exit(1)
    pageid_list = sorted(list(set(pageid_list)))
    get_page(pageid_list, api_url, source, cleaning_rule, exclude_titles, site_url, output_format)


error_count = 0
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--config', required=True, help='Path to config file')
    parser.add_argument('--output', required=True, help='Path to output file')
    args = parser.parse_args()
    config_path = args.config
    output_path = args.output
    main()
